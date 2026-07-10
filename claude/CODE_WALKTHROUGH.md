# `claude_generator.py` — Complete Code Walkthrough

A line-by-line explanation of the `ClaudeGenerator`, organized top-to-bottom exactly as the
file reads (451 lines). Each section covers **what** the code does and **why** it was
written that way, plus likely reviewer questions at the end. §18 summarizes the hardening
pass applied in this revision. Unit tests live in `test_claude_generator.py`.

---

## 1. The big picture (say this first)

`ClaudeGenerator` is our `Generator` implementation for Anthropic Claude models. It:

1. Accepts a system prompt, user prompt, optional multimodal parts (images/documents), and an optional JSON response schema.
2. Builds a request in the **Anthropic Messages API** format.
3. Sends it through the **Citi R2D2 proxy** using the `AsyncAnthropicVertex` SDK client (Claude is hosted on GCP Vertex behind R2D2).
4. Maps API failures to our internal `GenaiCommonException` error codes, retries via the shared `retry_wrapper`, and emits usage/observability metrics.

It mirrors `VertexAiGenerator` (the Gemini generator) in interface and behavior so callers
can switch providers via config alone.

---

## 2. Imports (lines 1–22)

```python
from __future__ import annotations
```
Postpones evaluation of type annotations — lets us write modern union syntax like
`dict | None` in signatures regardless of subtle runtime-typing edge cases, and avoids
import-time cost of building annotation objects.

- `logging`, `typing (Dict, List, Tuple)`, `json` — stdlib basics. `json` is used to serialize the response schema into the system prompt.
- `httpx` — the HTTP layer under the Anthropic SDK. Imported directly to construct an explicit `httpx.Timeout` and to build a custom `httpx.AsyncClient` with a response event hook (R2D2 header capture).
- `AsyncAnthropicVertex, APIConnectionError, APIStatusError, APITimeoutError` — the async Vertex-flavored Anthropic client and the **three** exception types we translate into our error codes. `APIConnectionError` covers network/connection failures during the API call itself (distinct from HTTP-status errors and timeouts).
- `anthropic.types.Message` — the response type; used in type hints and by `unwrap_llm_response`.
- `google.oauth2.credentials.Credentials` — wraps our COIN token so the Vertex SDK accepts it as a GCP credential.
- The `query.*` imports are our framework: environment config, the `Generator` base class, response/metrics/observability models, `PartHolder` (multimodal part wrapper), error codes + `GenaiCommonException`, `ProxyTokenRoller` (rolling COIN token supplier), and `retry_wrapper`.

`logger = logging.getLogger(__name__)` — standard per-module logger.

---

## 3. MIME-type routing tables (lines 25–46)

```python
_CLAUDE_IMAGE_MIME_TYPES = frozenset({ "image/jpeg", "image/png", "image/gif", "image/webp" })
```
These are exactly the four image formats the Claude API accepts as `"type": "image"`
content blocks. Nothing more — sending an unsupported type is a 400.

```python
_CLAUDE_DOCUMENT_MIME_TYPES = frozenset({ "application/pdf", DOCX, ODT, EPUB, text/plain, html, csv, tsv, json, rtf (both registrations), XLSX })
```
Everything Claude accepts as a `"type": "document"` block. Note `application/rtf` **and**
`text/rtf` — RTF has two MIME registrations in the wild, so we accept both.

**Why `frozenset`?** O(1) membership tests, and immutability signals "this is a constant
lookup table, don't mutate it."

---

## 4. Model-parameter allowlist (lines 48–54)

```python
_ALLOWED_MODEL_PARAMS = frozenset({"temperature", "top_p", "stop_sequences", "top_k", "metadata"})
```
`llm_config.model_parameters` is free-form config (per-model, per-use-case). Only keys in
this allowlist are forwarded to the API. **Anything else is silently ignored — that is a
deliberate safety property**: a config typo (`temprature`) or a provider-specific key meant
for Gemini (`response_mime_type`) can never reach the Anthropic API and cause a 400.
When a new API parameter should become configurable, we extend this list consciously.

Keys that are *built explicitly* elsewhere (`model`, `max_tokens`, `system`, `messages`,
`thinking`) don't belong in the allowlist — they'd conflict with the explicit construction.

> Design history worth knowing: an earlier version derived this list by introspecting the
> SDK's `AsyncMessages.create` signature at import time. We replaced it with the explicit
> allowlist — introspection was clever but fragile (breaks on SDK refactors) and made the
> forwarded set change silently on SDK upgrades. Explicit is safer and reviewable.

```python
_FLOAT_MODEL_PARAMS = frozenset({"temperature", "top_p"})
```
Values coming from config/YAML can arrive as ints or strings ("0" vs 0.0). These two must
be sent as floats, so `_build_create_args` coerces them.

---

## 5. Model-capability tables — legacy allowlists (lines 56–87)

Claude model generations differ in what the API accepts. The key design decision here:
**the tables list *legacy* models (closed sets that can never grow), and everything
unrecognized gets the modern behavior.** New model launches therefore work on day one
with zero code changes — the failure mode for a genuinely old, unlisted model is a
harmlessly dropped param, not a 400.

```python
_CLAUDE_MANUAL_THINKING_MODELS = frozenset({ 3-7-sonnet, opus-4/-4-1/-4-5, sonnet-4/-4-5, haiku-4-5 })
```
Bare model IDs (snapshot suffix stripped) that still take **manual** extended thinking
(`{"type": "enabled", "budget_tokens": N}`). From 4.6 `budget_tokens` is deprecated and
from 4.7+ / Sonnet 5 it's a 400 — those models (and any future model) get
`{"type": "adaptive"}`, where the model decides its own thinking depth.

```python
_CLAUDE_SAMPLING_PARAM_MODELS = _CLAUDE_MANUAL_THINKING_MODELS | frozenset({ opus-4-6, sonnet-4-6, 3.x family })
```
Bare model IDs that still accept sampling params (`temperature` / `top_p` / `top_k`).
Sampling was removed from the API in 4.7. Note the set is a **superset** of the
manual-thinking set: 4.6 deprecated manual thinking but *kept* sampling, hence the two
extra 4.6 entries; the 3.x models never had extended thinking but do take sampling.

**Why exact-match frozensets instead of prefix tuples?** Two reasons. (1) Prefixes are
ambiguous in the legacy direction — `"claude-opus-4"` would prefix-match
`claude-opus-4-7`, silently misclassifying a modern model. Exact bare-ID matching can't
collide. (2) Legacy models are a **closed set** — no new legacy model will ever be
released — so exact enumeration is the structurally correct shape: the set never needs
maintenance, while the old modern-prefix tables needed an edit for every model launch.

```python
_SAMPLING_PARAMS = frozenset({"temperature", "top_p", "top_k"})
```
The set of params that the sampling rule applies to.

---

## 6. `_bare_model_name` (lines 90–92)

```python
def _bare_model_name(model_name: str) -> str:
    return model_name.split("@", 1)[0]
```
Vertex model IDs carry a snapshot suffix: `claude-opus-4-5@20251101`. Capability checks
match on the bare name, so we strip everything from `@` on. `split("@", 1)` with
`maxsplit=1` is cheap and safe when there's no `@` (returns the whole string).

---

## 7. Request timeout constant (lines 95–99)

```python
_CLAUDE_REQUEST_TIMEOUT = httpx.Timeout(timeout=1200.0, connect=30.0)
```
Passed explicitly on every request. Two purposes:

1. **Overrides the SDK's computed timeout.** Without an explicit value the SDK derives a
   timeout from `max_tokens`; supplying our own makes the bound deterministic and
   config-independent.
2. **Bounds the wait.** 1200 s (20 min) covers the slowest generation we realistically
   run — e.g. 64K-token outputs. `connect=30.0` separately bounds TCP/TLS connection
   establishment.

Key point for the reviewer: **a large timeout costs nothing on small requests** — it only
bounds how long the SDK will wait, it never makes a fast request slower.

---

## 8. Module-level helpers (lines 102–135)

### `_make_r2d2_header_hook(headers_capture)` (lines 102–118)

A **factory** returning an async httpx response hook. The R2D2 proxy attaches useful
headers to responses:

- `x-r2d2-requestid` — proxy-side request ID for support tickets,
- `ratelimit-limit` / `ratelimit-remaining` — our quota state.

The hook copies whichever of these are present into the `headers_capture` dict (owned by
the caller — `generate_multimodal` creates one per request) and logs them via
`logger.info(..., extra=...)` so they land as structured log fields.

**Why a factory + capture dict instead of reading headers off the response later?** The
SDK returns a parsed `Message`, not the raw `httpx.Response` — the event hook is the
supported way to see raw response headers. The factory closes over a per-request dict so
concurrent requests can't cross-contaminate each other's headers.

### `_build_content_block(part)` (lines 121–135)

Converts one `PartHolder` into a Claude content block:

```python
source = {"type": "base64", "media_type": part.mime_type, "data": part.data}
```
Everything ships base64-inline (no file-upload API through R2D2). Then:

- MIME in the image set → `{"type": "image", "source": ...}`
- MIME in the document set → `{"type": "document", "source": ...}`
- otherwise → `None`, and the **caller** logs and skips it (keeps this function pure —
  decision here, side effect at the call site).

---

## 9. `ClaudeGenerator` class (lines 138–162)

Class docstring documents the two responsibilities (Messages-API format, R2D2 routing via
AnthropicVertex) and the part-routing table for quick reference.

### `__init__` (lines 151–162)

Stores four collaborators, no I/O in the constructor:

- `environment: ClaudeEnvironment` — region, API base URL, default project ID.
- `token_roller: ProxyTokenRoller` — supplies a **current** COIN token on demand (tokens expire, hence "roller").
- `llm_config: ModelConfig` — model name, model_parameters, r2d2_coin, project override.
- `use_case: str` — the calling use case (observability attribution — see §15).

```python
self.project_id = self.llm_config.project_id or environment.claude_project_id
```
Resolution order mirrors `VertexAiGenerator`: an explicit per-model project override wins;
otherwise fall back to the environment default. Resolved once here so every later use
reads one attribute.

---

## 10. Public interface (lines 164–268)

### `generate(...)` (lines 164–176)

Text-only entry point required by the `Generator` interface. Pure delegation:

```python
return await self.generate_multimodal(system_prompt, prompt, [], soeid, ...)
```
Text-only is just multimodal with zero parts — one code path to maintain, impossible for
the two to drift apart.

### `generate_multimodal(...)` (lines 178–235)

The orchestrator. Note the deliberate ordering — cheap, fallible, client-free steps first:

1. ```python
   retry_config = retry_config or ModelRetryConfig()
   ```
   The signature default is `None`, **not** `ModelRetryConfig()` — a default instance
   would be created once at import time and shared by every call (the classic Python
   mutable-default trap). Resolving inside the method gives each request its own config.
2. ```python
   content = self._build_message_content(parts, prompt)
   create_args = self._build_create_args(system_prompt, content, max_tokens, response_schema)
   ```
   **Built before the client exists.** Both can raise on malformed config (e.g. a
   non-numeric `temperature` failing `float()`); doing them first means there is no
   half-open client to leak when they do.
3. Log which R2D2 COIN and model we're calling (support/debugging breadcrumb).
4. ```python
   r2d2_headers: dict = {}
   try:
       client = self._build_client(r2d2_headers)
   except Exception as e:
       raise GenaiCommonException(ErrorCodes.ER010, ErrorCodes.ER010.get_description(), e) from e
   ```
   Client construction does no network I/O, but `token_roller.get_token()` can fail
   (expired COIN session, IAM hiccup). Any setup failure surfaces as **ER010** —
   deliberately raised *before* the retry loop, because retrying with broken setup
   cannot succeed.
5. ```python
   try:
       generate_with_retry = retry_wrapper(self.__generate, retry_config)
       return await generate_with_retry(client, create_args, soeid, r2d2_headers)
   finally:
       await client.close()
   ```
   The shared framework `retry_wrapper` handles backoff/retry policy — same mechanism
   every generator uses. **The `finally` is important:** we construct a fresh
   `httpx.AsyncClient` per request; without `close()` every call leaks a connection pool.
   The `try` starts immediately after client construction so *nothing* can raise between
   acquiring the client and entering the block that guarantees its cleanup — and it sits
   outside the retry wrapper so the client survives across retries and is closed exactly
   once, after the last attempt.

### `unwrap_llm_response(response)` (lines 237–261)

Static — pure function of the response, needs no instance state.

- Raises `ValueError` if `response.content` is empty.
- Returns the **first `text` block** with a `ConfidenceScoreResponse(confidence_score=0, token_wise_confidence_scores=[])`.
- Raises `ValueError` if no text block exists (e.g. response was all thinking blocks).

Two things to explain confidently:

1. **Why confidence 0?** Claude does not expose log-probabilities, so there is nothing to
   compute. The interface requires the field; 0 is the documented "not available" value
   (same shape callers get from providers that do supply it).
2. **Why always a string (no dict branch like Vertex)?** Whether the schema is
   prompt-injected or natively enforced via `output_config`, the answer arrives as a
   *text block* — native mode guarantees the text parses as schema-valid JSON, but it is
   still text. Parsing is the caller's concern.

### `default_prompt_id` property / `get_platform()` (lines 263–268)

- `default_prompt_id` — passthrough to config; part of the `Generator` interface.
- `get_platform()` — returns `ModelProvider.CLAUDE`; static because it's a class-level fact used by the factory/registry to route configs to generators.

---

## 11. `__generate` — the actual API call (lines 271–310)

Name-mangled private (`__`) — this must only ever be invoked through the retry wrapper,
never directly.

```python
async with client.messages.stream(
    extra_headers={"x-r2d2-user": soeid},
    timeout=_CLAUDE_REQUEST_TIMEOUT,
    **create_args,
) as stream:
    response = await stream.get_final_message()
```
- `x-r2d2-user: <soeid>` — R2D2 requires per-request user attribution.
- Explicit timeout — see §7.
- **Streaming rather than a single non-streaming `create()` call.** At large `max_tokens`
  (our default resolution is 64K — §14), a non-streaming request sits idle for minutes
  while the model generates; idle connections are exactly what intermediate
  proxies/load-balancers (R2D2 sits in the path) drop. SSE streaming keeps bytes flowing
  continuously so the connection is never idle. `stream.get_final_message()` then hands
  back the **same fully-assembled `Message` object** `create()` would have returned — so
  callers are completely unaffected; streaming here is a transport decision, not an API
  change.

### Error mapping (lines 278–301)

On `APIStatusError` we **first log the raw error body** — status, message, request ID,
body. This one log line is what makes 400s diagnosable (the API's error body says exactly
which parameter it rejected). Then map to framework error codes:

| Condition | Error code | Meaning |
|---|---|---|
| 429 | `GR008` | Rate limited (checked first — it's the most common and most actionable) |
| 400 | `GR007` | Bad request (invalid params/schema) |
| other 4xx | `GR010` | Client-side error (401/403 auth, etc.) |
| 5xx / anything else | `GR009` | Server-side error |
| `APITimeoutError` | `GR012` | Request timed out |
| `APIConnectionError` | `ER012` | Connection dropped/failed mid-request (network-level, no HTTP status) |

Order matters in the except chain: `APIStatusError` (has an HTTP status) is handled first,
then `APITimeoutError`, then `APIConnectionError` as the network-level catch. In the
Anthropic SDK **`APITimeoutError` is a subclass of `APIConnectionError`** (there's an
inline comment marking this), so the timeout branch must come before the connection branch
or timeouts would be swallowed as ER012.

All raised as `GenaiCommonException(...) from e` — `from e` preserves the original
exception chain for debugging, while callers/handlers see our uniform error type. The
retry wrapper's policy decides which of these codes are retryable.

Together with ER010 (client setup, §10) the connection-failure story is: **ER010** =
setup failed before any request; **ER012** = transport failed during the request;
**GR012** = request exceeded the explicit timeout.

### Success path (lines 303–310)

```python
usage_metrics = LLMUsageMetrics.from_claude_response(response)
logger.info("Claude usage metrics: %s", usage_metrics)
logger.debug("Claude raw response: %s", response)
self._log_observability(usage_metrics, r2d2_headers or {})
return response, usage_metrics
```
Usage metrics are logged at INFO; the **full model response only at DEBUG**. At 64K
max_tokens the response can be hundreds of KB and may contain client data — routine INFO
logs are not the place for it (log volume + data-handling). Metrics then flow to the
observability pipeline with the captured R2D2 headers, and the raw `Message` is returned
to the caller.

---

## 12. `_build_client` (lines 312–326)

```python
return AsyncAnthropicVertex(
    region=self.environment.claude_region,
    project_id=self.project_id,
    credentials=Credentials(self.token_roller.get_token()),
    http_client=httpx.AsyncClient(event_hooks={"response": [_make_r2d2_header_hook(headers_capture)]}),
    base_url=self.environment.claude_api_base,
)
```

Fresh client **per request** — the single most important reason is the credential:
`token_roller.get_token()` returns the currently-valid COIN token, and tokens expire. A
long-lived client would eventually hold a stale token. Building per-request makes token
freshness automatic. The trade-off (no connection reuse across requests) is acceptable at
our request rates, and it's why `generate_multimodal` must `close()` the client.

- `credentials=Credentials(token)` — wraps the COIN token as a GCP OAuth2 credential, which is what the Vertex-flavored SDK expects.
- `http_client=` with the response event hook — this is how R2D2 headers get captured (§8).
- `base_url=self.environment.claude_api_base` — points the SDK at the R2D2 proxy endpoint instead of Google's default Vertex URL. **This is the line that routes traffic through R2D2.**

---

## 13. `_build_message_content` (lines 328–350)

Builds the content list for the single user message:

1. For each `PartHolder`: convert via `_build_content_block`; append if supported,
   otherwise `logger.warning` with MIME type and filename and **skip** (degrade
   gracefully — one bad attachment shouldn't fail the whole request).
2. Append the text prompt **last**:
   ```python
   content.append({"type": "text", "text": prompt})
   ```
   Ordering is intentional: Anthropic's guidance is documents/images before the question —
   it measurably improves the model's use of the attached material.

Result: `[image/document blocks..., text block]` inside one `{"role": "user"}` message.

---

## 14. `_build_create_args` — request assembly (lines 352–435)

The heart of the file — and deliberately **pure** (config + args in, dict out), which is
what makes the unit-test matrix in `test_claude_generator.py` possible.

### max_tokens resolution (lines 372–377)

```python
resolved_max_tokens = (
    max_tokens
    or self.llm_config.model_parameters.get("max_tokens")
    or self.llm_config.model_parameters.get("max_output_tokens")
    or 64000
)
```
Priority: explicit call-site override → config `max_tokens` → config `max_output_tokens`
(the Vertex/Gemini spelling, accepted so a config written for Gemini ports over) → default
**64000**. `max_tokens` is **required** by the Anthropic API, hence a default. 64K is the
output ceiling shared by every model tier we run through R2D2, so an unconfigured model
gets full output headroom rather than an artificially small cap — with Claude you pay only
for tokens actually generated, so a high `max_tokens` on short answers costs nothing.

**Deliberately no client-side ceiling/clamping.** `model_parameters` is trusted per-model
config; if a value ever exceeds the model's true output limit, the API rejects it with a
clearly-worded 400 → surfaced as `GR007`. We prefer that explicit failure over silently
clamping against a per-model limits table we'd have to maintain forever.

### Base args (lines 378–382)

```python
args = {"model": ..., "max_tokens": resolved_max_tokens, "messages": [{"role": "user", "content": content}]}
```
Single-turn: exactly one user message. The system prompt goes in the top-level `system`
param (Anthropic's API design — system is not a message role), added below.

### response_schema — two modes (lines 384–400)

**Mode 1 — native structured outputs** (config flag `native_json_schema` truthy):

```python
args["output_config"] = {"format": {"type": "json_schema", "schema": response_schema}}
```
Platform-enforced JSON conformance — the exact analog of Vertex's
`response_schema` + `response_mime_type`. Output is guaranteed valid and
schema-conformant (barring `max_tokens` truncation). It is **opt-in per model via config**
because it has requirements: a model generation that supports `output_config.format`, and
schemas with `additionalProperties: false` on every object. Rollout process: smoke-test a
model on R2D2 before enabling its flag.

**Mode 2 — prompt injection (default fallback):**

```python
schema_instruction = ("You must respond with valid JSON only, strictly conforming to this JSON schema:\n"
                      f"{json.dumps(response_schema)}\n"
                      "Output raw JSON only - do not wrap it in markdown code fences, "
                      "and do not include any text before or after the JSON.")
system_prompt = f"{system_prompt}\n\n{schema_instruction}" if system_prompt else schema_instruction
```
The schema is appended to the system prompt as an instruction. Highly reliable with modern
Claude models but **not enforced** — downstream consumers should still parse defensively.
The explicit "no markdown fences" line exists because the single most common failure mode
is the model wrapping JSON in ` ```json ` fences. Note the ternary handles the
empty-system-prompt case (no stray leading newlines).

### system prompt (lines 399–400)

```python
if system_prompt:
    args["system"] = system_prompt
```
Only set when non-empty — the API treats an empty string differently from an absent param.

### Capability flags (lines 402–404)

```python
bare_model = _bare_model_name(self.llm_config.name)
manual_thinking_model = bare_model in _CLAUDE_MANUAL_THINKING_MODELS
sampling_param_model = bare_model in _CLAUDE_SAMPLING_PARAM_MODELS
```
Computed once, used by the two branches below. Exact membership tests against the legacy
sets (§5) — anything unrecognized is treated as modern.

### Extended thinking (lines 406–418)

```python
thinking_config = self.llm_config.model_parameters.get("thinking_config")
if isinstance(thinking_config, dict):
    budget = thinking_config.get("thinking_budget")
    if budget is not None:
        if manual_thinking_model:
            args["thinking"] = {"type": "enabled", "budget_tokens": int(budget)}
        else:
            args["thinking"] = {"type": "adaptive"}
        thinking_enabled = True
```
- Config shape (`thinking_config.thinking_budget`) matches the Gemini generator's config, so one config vocabulary works across providers; we translate to Anthropic's format here.
- `isinstance(... dict)` guards against malformed config (a string/None doesn't crash us).
- Only the closed legacy set gets the classic `enabled` + `budget_tokens` form (with `int()` coercion, since config values may arrive as strings). On everything else — 4.6+, Sonnet 5, and any future model — the configured budget number is intentionally **ignored**: those models reject `budget_tokens`; a budget in config simply means "thinking on", and the model manages depth itself in adaptive mode.
- `thinking_enabled` is remembered for the temperature rule below.

### Forwarding allowlisted params (lines 420–433)

```python
for param, value in self.llm_config.model_parameters.items():
    if param not in _ALLOWED_MODEL_PARAMS:
        continue
    if param in _SAMPLING_PARAMS and not sampling_param_model:
        logger.warning("Dropping sampling param '%s' — not supported by model %s", ...)
        continue
    coerced = float(value) if param in _FLOAT_MODEL_PARAMS else value
    # Anthropic requires temperature=1 when extended thinking is enabled
    if param == "temperature" and thinking_enabled:
        coerced = 1.0
    args[param] = coerced
```
Four rules, in order:

1. **Allowlist filter** — non-allowlisted keys (including `thinking_config`, `max_tokens`, `native_json_schema` themselves) never reach the API.
2. **Sampling removal** — on non-legacy models, `temperature`/`top_p`/`top_k` are dropped **with a warning log** (visible, not silent — an operator can see their config value isn't taking effect and clean it up).
3. **Float coercion** — `temperature`/`top_p` sent as floats regardless of config type.
4. **Thinking constraint** — the Anthropic API **requires `temperature=1` when extended thinking is enabled**; we force it rather than let a configured 0.2 cause a 400.

Then `return args`.

---

## 15. `_log_observability` (lines 437–451)

```python
usage_metrics_dict = usage_metrics.model_dump() if usage_metrics else {}
if r2d2_headers:
    usage_metrics_dict["x_r2d2_requestid"] = ...
    usage_metrics_dict["ratelimit_limit"] = ...
    usage_metrics_dict["ratelimit_remaining"] = ...
ObservabilityLogger.get_logger().info({
    "observability_type": ObservabilityLogType.OTHER.value,
    "model": ..., "project_id": ..., "use_case": self.use_case,
    "r2d2_coin": ..., "usage_metrics": usage_metrics_dict,
})
```
Emits one structured record per successful call to the observability pipeline: token
usage, model, project, **use case** (this is why `__init__` takes `use_case` — per-team
attribution of token spend and rate-limit consumption), COIN, and — when captured — the
R2D2 request ID and rate-limit state. The request ID is the join key with R2D2's own logs
when raising proxy support tickets; the rate-limit numbers let dashboards trend quota
consumption per model/COIN/use-case. `.model_dump()` converts the Pydantic metrics model
to a plain dict; header keys are renamed dashes→underscores for the logging schema.

---

## 16. Design decisions cheat-sheet (30-second answers)

| Decision | One-line justification |
|---|---|
| Fresh client per request | COIN tokens expire; per-request build guarantees a current token. Cost: must `close()` in `finally` or we leak connection pools. |
| Build payload before client | `_build_create_args` can raise on bad config; building it first means no client exists yet to leak. |
| Streaming (`messages.stream()`) | At 64K max_tokens a non-streaming call sits idle for minutes and gets dropped by intermediate proxies; streaming keeps bytes flowing, and `get_final_message()` returns the identical `Message` object. |
| 1200 s explicit timeout | Must cover 64K-token generations; overrides the SDK's max_tokens-derived timeout; costs nothing on fast requests. |
| Explicit param allowlist | Config typos / other providers' keys can never cause API 400s; introspection-based derivation was fragile. |
| max_tokens default 64000, no clamping | 64K is the output ceiling across our deployed tiers; unconfigured models get full headroom (unused tokens cost nothing). Anything invalid gets the API's explicit 400 (→ GR007) instead of silent clamping. |
| Legacy allowlists, modern by default | Legacy models are a closed set — exact-match them and give everything unrecognized (i.e. every future model) adaptive thinking + no sampling. New launches work with zero code changes; prefix tables would need an edit per launch and can collide. |
| Schema: native vs prompt-injected | Native (`output_config`) is platform-enforced but opt-in per model (needs support + `additionalProperties: false`); prompt injection is the safe default. |
| temperature=1 when thinking | Hard API requirement — forced, not configurable. |
| confidence_score always 0 | Claude exposes no log-probs; 0 is the interface's "not available" value. |
| Skip unsupported parts, don't fail | One bad attachment shouldn't kill the request; warning logged with MIME + filename. |
| Response at DEBUG, metrics at INFO | Full outputs can be huge and may contain client data — they don't belong in routine INFO logs. |
| `retry_config` defaults to `None` | A `ModelRetryConfig()` signature default would be one shared instance across all calls (mutable-default trap); resolved per-call inside the method. |
| Error mapping | 429→GR008, 400→GR007, 4xx→GR010, 5xx→GR009, timeout→GR012, mid-request connection failure→ER012, client-setup failure→ER010; raw body always logged first for diagnosability. |

---

## 17. Likely reviewer questions — prepared answers

**Q: Why streaming when we only return the final message?**
Transport robustness, not partial delivery. A non-streaming request at large `max_tokens`
leaves the connection idle for minutes while the model generates — idle connections are
what proxies and load balancers kill. SSE keeps the connection active the whole time.
`get_final_message()` reassembles the stream into exactly the `Message` a `create()` call
would return, so nothing above this method changes.

**Q: Why not reuse one client / connection pool?**
Token freshness. `ProxyTokenRoller` hands out the current COIN token, and the token is
baked into the client at construction. Per-request construction is the simplest correct
design; if profiling ever shows connection setup matters, the alternative is a shared
`httpx` client with an auth-refresh hook — more machinery, no correctness gain today.

**Q: What's the difference between ER010, ER012, and GR012?**
ER010 = client *setup* failed (e.g. the COIN token fetch) — raised before the retry loop,
because retrying broken setup is pointless. ER012 = the connection failed *during* the API
request (network-level, no HTTP status). GR012 = the request ran past our explicit 1200 s
timeout. Ordering in the except chain matters: `APITimeoutError` subclasses
`APIConnectionError` in the SDK, so the timeout branch comes first.

**Q: Why `except Exception` around `_build_client` — isn't that broad?**
Deliberately: it's a narrow scope (client construction + token fetch, no business logic)
and the semantics we want are "anything that prevents setup is ER010, don't retry."
`from e` preserves the real cause for debugging. The alternative — enumerating every
exception the token roller might raise — couples us to its internals.

**Q: How do new Claude models get onboarded?**
Usually zero code changes: unrecognized model IDs default to modern behavior (adaptive
thinking, sampling params dropped). The legacy sets are closed and never grow. Only a new
*API capability* (like `output_config` was) needs code.

**Q: Why default max_tokens to 64000?**
It's the output ceiling shared by all tiers we deploy, and unused output tokens are free —
so the default gives full headroom instead of truncating long answers with an arbitrary
small cap. Explicit config still wins when set.

**Q: What happens if config contains a param the model doesn't support?**
Three layers: not in the allowlist → never sent; in the allowlist but a sampling param on
a modern model → dropped with a warning; anything that still slips through and the API
rejects → 400 logged with the raw body and surfaced as GR007.

**Q: Is prompt-injected JSON schema guaranteed?**
No — it's highly reliable steering, not enforcement, which is why the instruction
explicitly forbids code fences and why consumers should parse defensively. For guaranteed
conformance we flip `native_json_schema` on per model, which uses the platform's
structured-outputs (`output_config.format`) — the same guarantee Vertex gives via
`response_schema`.

**Q: Why is `__generate` name-mangled?**
It must only run inside the retry wrapper (and its error mapping assumes that context).
Double-underscore makes accidental external calls effectively impossible.

**Q: Multi-turn conversations?**
Out of scope by design — the `Generator` interface is single-shot (system + one user
message). Conversation state lives above this layer.

**Q: What if `parts` contains only unsupported MIME types?**
Every part is skipped with a warning and the request degrades to text-only — the prompt
text block is always appended, so the message is never empty.

**Q: Why check `isinstance(thinking_config, dict)` instead of just truthiness?**
Config is external input. A malformed value (string, list) would raise `AttributeError`
on `.get()`; the isinstance guard makes malformed thinking config mean "thinking off"
instead of a crash.

**Q: How is this tested?**
`test_claude_generator.py` — 26 unit tests covering the pure logic: the full
`_build_create_args` matrix (max_tokens resolution order, both schema modes, thinking
translation for legacy/modern/unknown models, sampling drop, float coercion, temperature
forcing, allowlist filtering), plus `_bare_model_name`, `_build_content_block` routing,
and `unwrap_llm_response` (first-text-block, empty-content, no-text-block). External deps
(`query` framework, `anthropic` SDK) are stubbed via `sys.modules`, so the suite runs
anywhere with `python3 -m unittest test_claude_generator`.

---

## 18. Hardening pass applied in this revision

If the reviewer asks "what changed recently and why", these were deliberate fixes:

1. **Client-leak fix** — `content`/`create_args` are now built *before* the client, and
   the `try/finally: client.close()` starts immediately after client construction, so no
   failure path can leak an `httpx.AsyncClient`.
2. **ER010 made real** — the previous `except httpx.ConnectError` around `_build_client`
   was dead code (construction does no I/O, so `ConnectError` could never fire there).
   Now it catches `Exception`, which actually covers the realistic failure (COIN token
   fetch), keeping the intended "setup failure → ER010, no retry" semantics.
3. **Response logging demoted to DEBUG** — full model outputs (potentially huge, possibly
   containing client data) no longer land in routine INFO logs; usage metrics stay at INFO.
4. **Capability tables inverted to legacy allowlists** — exact-match frozensets of the
   closed legacy set replace grow-forever modern-prefix tuples; future models work with
   zero code changes, and the string-concatenation footgun of a missing trailing comma in
   a tuple is gone.
5. **`use_case` now emitted in observability** — it was stored but never logged; per-use-
   case attribution was the whole point of the constructor param.
6. **Mutable-default fix** — `retry_config` defaults to `None` and is resolved per call,
   instead of one shared `ModelRetryConfig()` instance created at import time.
7. **Docstrings/comments re-synced** — the timeout comment no longer references
   `create()`, and `_build_create_args` / `unwrap_llm_response` docstrings now describe
   both schema modes (native + prompt-injected).
8. **Unit tests added** — `test_claude_generator.py`, 26 tests, all passing (see the
   testing Q&A in §17).
