# `claude_generator.py` — Complete Code Walkthrough

Branch: `feature/ARCH-48132-claude-custom-file-support` · 456 lines · tests in `test_claude_generator.py` (44 passing)

A line-by-line explanation of `ClaudeGenerator`, organized top-to-bottom exactly as the file
reads. Each section covers **what** the code does and **why** it was written that way.
§17 is a prepared Q&A for the review; §18 lists the open items I'd raise before a reviewer
finds them.

---

## 1. The big picture (say this first)

`ClaudeGenerator` is our `Generator` implementation for Anthropic Claude models. It:

1. Accepts a system prompt, user prompt, optional file parts, and an optional JSON response schema.
2. **Normalizes every uploaded file into a content block Claude actually accepts** — converting Office documents to text and TIFF to PNG on the way (this branch's main feature).
3. Builds the request in **Anthropic Messages API** format.
4. Routes it through the **Citi R2D2 proxy** via the `AsyncAnthropicVertex` SDK client.
5. Maps API failures to our `GenaiCommonException` error codes, retries via the shared `retry_wrapper`, and emits usage/observability logs on both the success and failure paths.

It mirrors `VertexAiGenerator` in interface so callers can switch providers via config alone.

---

## 2. Imports (lines 1–21)

```python
from __future__ import annotations
```
Postpones evaluation of type annotations — lets us write `dict | None` in signatures and
avoids import-time cost of building annotation objects.

- `base64` — **new on this branch.** The file-conversion pipeline decodes inbound part data and re-encodes converted images.
- `logging`, `typing`, `json`, `httpx` — stdlib plus the HTTP layer under the SDK.
- `AsyncAnthropicVertex, APIConnectionError, APIStatusError, APITimeoutError` — the async Vertex-flavored client and the three exception types we translate into error codes.
- `google.oauth2.credentials.Credentials` — wraps our COIN token so the Vertex SDK accepts it as a GCP credential.
- **`query.util.document_utils`** — `word_to_text`, `xlsx_to_text`, `odt_to_text`, `tiff_to_png`. This import is the whole feature in one line: the generator delegates format conversion rather than owning it.
- The rest is framework: environment config, the `Generator` base class, response/metrics/observability models, `PartHolder`, error codes, `ProxyTokenRoller`, `retry_wrapper`.

---

## 3. The five MIME routing tables (lines 27–64)

This is the heart of the branch. Claude's API accepts a **small** set of content-block
shapes; users upload a much wider set of file types. These five tables encode which
strategy each MIME type takes.

| Table | Line | Strategy |
|---|---|---|
| `_CLAUDE_IMAGE_MIME_TYPES` | 27 | Pass base64 straight through as an `image` block |
| `_CLAUDE_TEXT_MIME_TYPES` | 38 | Decode base64 → send as a `document` block with `source.type: "text"` |
| `_CLAUDE_DOCUMENT_MIME_TYPES` | 50 | Pass base64 through as a `document` block — **PDF only** |
| `_CLAUDE_OTHER_MIME_TYPES` | 55 | Convert to plain text via `document_utils`, then send as a text document |
| `_CLAUDE_CONVERT_IMAGE_MIME_TYPES` | 62 | Convert to PNG, re-encode, send as an `image` block |

```python
TEXT_PLAIN: str = "text/plain"   # line 35
```
Deliberately a named constant, not a literal: `text/plain` is **the only `media_type` the
Anthropic SDK's `PlainTextSourceParam` accepts**. Every text-ish input — CSV, JSON, HTML,
a converted DOCX — is labeled `text/plain` on the wire regardless of what it started as.
Naming it makes that constraint visible instead of looking like copy-paste.

**Why is PDF alone in the document table (line 50)?** Because PDF is the only format
Claude parses natively as a document (it renders each page and reads the text). Everything
else that *looks* like a document — DOCX, XLSX, ODT — gets converted on our side.

**Why `frozenset`?** O(1) membership testing on every part of every request, plus
immutability signals these are constant lookup tables, not runtime state.

---

## 4. Model-parameter allowlist (lines 67–73)

```python
_ALLOWED_MODEL_PARAMS = frozenset({"temperature", "top_p", "stop_sequences", "top_k", "metadata"})
```
`llm_config.model_parameters` is free-form config. Only keys in this allowlist reach the
API. **Anything else is silently ignored — a deliberate safety property**: a config typo
(`temprature`) or a Gemini-only key (`response_mime_type`) can never cause an Anthropic
400. Keys built explicitly elsewhere (`model`, `max_tokens`, `system`, `messages`,
`thinking`) don't belong here.

```python
_FLOAT_MODEL_PARAMS = frozenset({"temperature", "top_p"})   # line 73
```
Config values arrive from YAML as ints or strings; these two must go out as floats.

---

## 5. Model-capability prefix tables (lines 76–90)

```python
_CLAUDE_ADAPTIVE_THINKING_PREFIXES = (opus-4-6/4-7/4-8, sonnet-4-6/4-7/4-8, sonnet-5)
_CLAUDE_NO_SAMPLING_PREFIXES       = (opus-4-7/4-8, sonnet-4-7/4-8, sonnet-5)
```
Two independent API changes across model generations:

- **From 4.6**, manual extended thinking (`{"type": "enabled", "budget_tokens": N}`) is deprecated, and from 4.7 it's a hard 400. Those models take `{"type": "adaptive"}` and pick their own thinking depth.
- **From 4.7**, sampling params (`temperature`/`top_p`/`top_k`) were removed from the API entirely.

The sets differ because 4.6 deprecated thinking budgets while still accepting sampling —
hence 4.6 appears in the first tuple but not the second.

**The important design point (and the thing to lead with in review):** these tuples are
**not the final word**. In `_build_create_args` they're concatenated with
`environment.claude_extra_adaptive_thinking_prefixes` and
`claude_extra_no_sampling_prefixes` (lines 396–401), so a new model tier can be onboarded
by **config change, not code release**. That matters in our deployment model — ops can add
`claude-opus-5` to the environment config the day it lands on R2D2, without waiting on a
build.

```python
_R2D2_TRACKED_HEADERS = ("x-r2d2-requestid", "ratelimit-limit", "ratelimit-remaining")   # line 90
```
Extracted so the capture hook (§7) and the observability writer (§16) agree on one list.

---

## 6. `_bare_model_name` and the request timeout (lines 92–99)

```python
def _bare_model_name(model_name: str) -> str:
    return model_name.split("@", 1)[0]
```
Vertex model IDs carry a snapshot suffix (`claude-opus-4-5@20251101`). All capability
checks are prefix matches on the bare name, so we strip from `@` on. `maxsplit=1` is safe
when there's no `@` — it returns the whole string.

```python
_CLAUDE_REQUEST_TIMEOUT = httpx.Timeout(timeout=1200.0, connect=30.0)   # line 99
```
Passed explicitly on every call. Without it the SDK derives a timeout from `max_tokens`;
supplying our own makes the bound deterministic and config-independent. 1200 s covers the
slowest generation we run (64K-token outputs); `connect=30.0` separately bounds TCP/TLS
setup. **A large timeout costs nothing on fast requests** — it bounds how long we'd wait,
it never makes a request slower.

---

## 7. `_make_r2d2_header_hook` (lines 102–108)

A **factory** returning an async httpx response hook:

```python
extra = {h: response.headers[h] for h in _R2D2_TRACKED_HEADERS if response.headers.get(h)}
if extra:
    headers_capture.update(extra)
```

The R2D2 proxy attaches the proxy-side request ID and our rate-limit state to responses.
The SDK hands back a parsed `Message`, not the raw `httpx.Response` — **the event hook is
the only supported way to see raw response headers**. The factory closes over a
per-request dict (created in `generate_multimodal`) so concurrent requests can't
cross-contaminate each other's captured headers. It captures only; the logging happens
once at the end in `_log_observability`.

---

## 8. `_build_content_block` — the conversion pipeline (lines 111–153)

The branch's centerpiece. One `PartHolder` in, one Claude content block out (or `None`).
Five checks in order:

**1. Native image (119–121)** — jpeg/png/gif/webp pass through untouched:
```python
source = {"type": "base64", "media_type": part.mime_type, "data": part.data}
return {"type": "image", "source": source}
```

**2. Text types (123–126)** — decode and hand Claude readable text:
```python
decoded_text = base64.b64decode(part.data).decode("utf-8")
source = {"type": "text", "media_type": TEXT_PLAIN, "data": decoded_text}
return {"type": "document", "source": source}
```
Note the shape: `type: "document"` with `source.type: "text"`. That's the Anthropic
"plain text document" block — it gets citation support and document framing, which a bare
text block wouldn't. `media_type` is always `TEXT_PLAIN` (§3).

**3. PDF (128–130)** — base64 through as a document; Claude parses it natively.

**4. Office formats (132–144)** — the conversion branch:
```python
raw_bytes = base64.b64decode(part.data)
if mime == DOCX:   converted_text = word_to_text(raw_bytes)
elif mime == XLSX: converted_text = xlsx_to_text(raw_bytes)
elif mime == ODT:  converted_text = odt_to_text(raw_bytes)
else:              return None
source = {"type": "text", "media_type": TEXT_PLAIN, "data": converted_text}
return {"type": "document", "source": source}
```
Claude has no native DOCX/XLSX/ODT support, so we extract text and send that. Conversion
logic lives in `document_utils` — this function only routes.

**5. TIFF (146–151)** — decode → `tiff_to_png` → re-encode → `image` block. TIFF isn't in
Claude's four accepted image formats, but PNG is, so we transcode. This is the only branch
that base64-**encodes** on the way out.

**Anything else → `None`** (line 153), and the caller logs and skips it.

**Why route here and convert in `document_utils`?** Separation of concerns: this function
answers "which strategy does this MIME type take?", and the utils answer "how do I read a
DOCX?" It also keeps this function testable without any Office parsing libraries — the
test suite stubs the four converters and asserts purely on routing.

---

## 9. `resolve_error_code` (lines 156–163)

```python
if status_code == 429: return ErrorCodes.GR008
if status_code == 400: return ErrorCodes.GR007
if 400 <= status_code < 500: return ErrorCodes.GR010
return ErrorCodes.GR009
```
Extracted to a module-level function so the status→code mapping is testable in isolation
and readable at a glance rather than buried in an except block. Order matters: 429 and 400
are checked before the general 4xx band because they're the two we act on differently
(rate limit vs. malformed request).

---

## 10. `ClaudeGenerator.__init__` (lines 166–186)

Stores four collaborators, no I/O in the constructor:

- `environment: ClaudeEnvironment` — region, API base URL, default project, **and the extra model-prefix lists** (§5).
- `token_roller: ProxyTokenRoller` — supplies a *current* COIN token on demand (tokens expire, hence "roller").
- `llm_config: ModelConfig` — model name, model_parameters, r2d2_coin, project override.
- `use_case: str` — the calling use case.

```python
self.project_id = self.llm_config.project_id or environment.claude_project_id
```
Mirrors `VertexAiGenerator`: explicit per-model override wins, else the environment
default. Resolved once so every later use reads one attribute.

---

## 11. Public interface (lines 188–270)

### `generate(...)` (188–200)
Text-only entry point required by the interface. Pure delegation to `generate_multimodal`
with `parts=[]` — text-only is just multimodal with zero parts, so there's one code path
and the two can't drift.

### `generate_multimodal(...)` (202–241)
The orchestrator:

1. `r2d2_headers = {}` — fresh capture dict for this request (§7).
2. Build the client (229–232), wrapped in `except httpx.ConnectError → ER010`.
3. `content = self._build_message_content(parts, prompt)` — runs the conversion pipeline over every part.
4. `create_args = self._build_create_args(...)` — full kwargs for the API call.
5. ```python
   try:
       generate_with_retry = retry_wrapper(self.__generate, retry_config)
       return await generate_with_retry(client, create_args, soeid, r2d2_headers)
   finally:
       await client.close()
   ```
   `retry_wrapper` is the shared framework retry/backoff mechanism — nothing bespoke.
   **The `finally` matters:** a fresh `httpx.AsyncClient` is created per request, and
   without `close()` every call leaks a connection pool. It sits outside the retry wrapper
   so the client survives across retries and closes exactly once, after the last attempt.

> ⚠️ Steps 2 and 3 are in the wrong order — see §18 item 1. Be ready for this one.

### `unwrap_llm_response(response)` (243–262)
Static — a pure function of the response.

```python
text_block = next((b for b in response.content if b.type == "text"), None)
```
Returns the first text block plus `ConfidenceScoreResponse(confidence_score=0,
token_wise_confidence_scores=[])`. Raises `ValueError` on empty content or no text block.

Two things to answer confidently:
- **Why confidence 0?** Claude doesn't expose log-probabilities, so there's nothing to compute. The interface requires the field; 0 is the "not available" value.
- **Why no dict-vs-str branch like Vertex?** Whether the schema was prompt-injected or natively enforced, the answer arrives as a *text block*. Parsing is the caller's concern.

### `default_prompt_id` / `get_platform()` (264–270)
Config passthrough, and the `ModelProvider.CLAUDE` identity used by the factory to route
configs to generators.

---

## 12. `__generate` — the API call (lines 272–307)

Name-mangled private (`__`) — it must only ever run inside the retry wrapper.

```python
response = await client.messages.create(
    extra_headers={"x-r2d2-user": soeid},
    timeout=_CLAUDE_REQUEST_TIMEOUT,
    **create_args,
)
```
- `x-r2d2-user: <soeid>` — R2D2 requires per-request user attribution.
- Explicit timeout — §6. Supplying it also suppresses the SDK's guard against long non-streaming requests at large `max_tokens`.
- Non-streaming `create()`, matching Citi's canonical R2D2 sample.

### Error handling (282–303)

On `APIStatusError` we pull the status and **response headers off the exception** —

```python
response_obj = getattr(e, "response", None)
hdrs = dict(getattr(response_obj, "headers", {}) or {})
```

— because the httpx event hook doesn't fire usefully on the error path, and the double
`getattr` guards against SDK versions where `e.response` is absent. Then a structured
**error-level** observability record is emitted with `status_code`, the R2D2 request ID,
rate-limit state, and `x-r2d2-response-source` (which tells us whether the failure came
from R2D2 itself or from Anthropic upstream — the first question in any proxy support
ticket). Finally:

```python
raise GenaiCommonException(resolve_error_code(e.status_code), e.message, e) from e
```

Note we pass **`e.message`**, the raw API message, rather than our own canned description.
That's deliberate: for a 400 the API tells you exactly which parameter it rejected, and
that string is far more useful in a log than "bad request".

| Condition | Code |
|---|---|
| 429 | `GR008` rate limited |
| 400 | `GR007` bad request |
| other 4xx | `GR010` client error |
| 5xx | `GR009` server error |
| `APITimeoutError` | `GR012` timed out |
| `APIConnectionError` | `ER012` connection failed mid-request |
| (client build, §11) | `ER010` |

**Ordering is load-bearing:** in the Anthropic SDK `APITimeoutError` subclasses
`APIConnectionError`, so the timeout branch **must** come first or timeouts would be
swallowed as ER012.

### Success path (305–307)
Extract usage metrics, emit the observability record, return `(response, usage_metrics)`.
There's deliberately **no full-response logging here** — at 64K max_tokens the response
can be hundreds of KB and may contain client data, which doesn't belong in routine logs.

---

## 13. `_build_client` (lines 309–323)

Fresh client **per request**. The reason is the credential: `token_roller.get_token()`
returns the currently-valid COIN token, and tokens expire — a long-lived client would
eventually hold a stale one. Per-request construction makes freshness automatic. The
trade-off (no connection reuse) is acceptable at our rates, and it's why
`generate_multimodal` must `close()`.

- `credentials=Credentials(token)` — wraps the COIN token as a GCP OAuth2 credential, which is what the Vertex-flavored SDK expects.
- `http_client=` with the response event hook — how R2D2 headers get captured (§7).
- `base_url=self.environment.claude_api_base` — **this is the line that routes traffic through R2D2** instead of Google's default Vertex endpoint.

---

## 14. `_build_message_content` (lines 325–347)

```python
for part in parts:
    block = _build_content_block(part)
    if block is not None:
        content.append(block)
    else:
        logger.warning("Unsupported MIME type '%s' for file '%s'; part skipped.", ...)

content.append({"type": "text", "text": prompt})
```

Two decisions:
- **Unsupported parts degrade gracefully** — warn with MIME type and filename, skip, carry on. One bad attachment shouldn't fail the whole request.
- **The prompt text goes last.** Anthropic's guidance is documents/images before the question; it measurably improves how the model uses the attached material.

---

## 15. `_build_create_args` and its two helpers (lines 349–441)

### max_tokens resolution (365–370)
```python
max_tokens or config["max_tokens"] or config["max_output_tokens"] or 64000
```
Call-site override → config → the Vertex/Gemini spelling (so a Gemini config ports over) →
64000. `max_tokens` is **required** by the API, hence a default. 64K is the output ceiling
across our deployed tiers, and unused output tokens cost nothing — so the default gives
full headroom instead of truncating long answers.

**No client-side clamping is deliberate.** If a configured value exceeds the model's real
limit, the API returns a clearly-worded 400 (→ GR007). We prefer that explicit failure over
silently clamping against a per-model table we'd have to maintain.

### response_schema — two modes (377–393)
**Native** (`native_json_schema` truthy) → `output_config.format` with the JSON schema.
Platform-enforced conformance, the exact analog of Vertex's `response_schema`. Opt-in per
model because it requires a model generation that supports it *and* schemas with
`additionalProperties: false` on every object.

**Fallback** → the schema is appended to the system prompt as an instruction. Highly
reliable but **not enforced**, so consumers should still parse defensively. The explicit
"no markdown code fences" line exists because fence-wrapping is the single most common
failure mode. The ternary handles an empty system prompt without leaving stray newlines.

### Capability resolution (395–403) — the config-extensible part
```python
adaptive_thinking_prefixes = _CLAUDE_ADAPTIVE_THINKING_PREFIXES + tuple(
    self.environment.claude_extra_adaptive_thinking_prefixes
)
no_sampling_prefixes = _CLAUDE_NO_SAMPLING_PREFIXES + tuple(
    self.environment.claude_extra_no_sampling_prefixes
)
adaptive_thinking_model = bare_model.startswith(adaptive_thinking_prefixes)
sampling_removed_model  = bare_model.startswith(no_sampling_prefixes)
```
Built-in defaults, extended at request time from environment config. `str.startswith()`
takes a tuple natively, so each check is one call. This is the mechanism that lets a new
model tier be onboarded without a code release (§5).

### `_apply_thinking_config` (410–422)
```python
thinking_config = self.llm_config.model_parameters.get("thinking_config")
if not isinstance(thinking_config, dict): return False
budget = thinking_config.get("thinking_budget")
if budget is None: return False
args["thinking"] = {"type": "adaptive"} if adaptive_thinking_model \
                   else {"type": "enabled", "budget_tokens": int(budget)}
return True
```
- The config shape (`thinking_config.thinking_budget`) matches the Gemini generator's, so one config vocabulary works across providers; translation to Anthropic's format happens here.
- `isinstance(..., dict)` guards against malformed config — a string or `None` would raise `AttributeError` on `.get()`; the guard makes malformed config mean "thinking off" rather than a crash.
- On adaptive-tier models the configured **budget number is intentionally ignored** — those models reject `budget_tokens`, so its presence in config just means "thinking on" and the model manages depth itself.
- `int(budget)` because config values may arrive as strings.
- The return value feeds the temperature rule below, which is why this is a `bool`-returning helper rather than a `void` mutator.

### `_apply_model_params` (424–441)
```python
for param, value in self.llm_config.model_parameters.items():
    if param not in _ALLOWED_MODEL_PARAMS:
        continue
    if sampling_removed_model and param in _SAMPLING_PARAMS:
        raise GenaiCommonException(ErrorCodes.GR007, f"Sampling parameter '{param}' is not supported by model {...}. Remove it from the model configuration.")
    coerced = float(value) if param in _FLOAT_MODEL_PARAMS else value
    if param == "temperature" and thinking_enabled:
        coerced = 1.0
    args[param] = coerced
```
Four rules in order:
1. **Allowlist filter** — non-allowlisted keys (including `thinking_config`, `max_tokens`, `native_json_schema` themselves) never reach the API.
2. **Sampling on a modern model → raise GR007, with a message naming the offending param and telling the operator exactly what to do.** This is a deliberate *fail-loud* choice over silently dropping: a dropped param means the model runs at settings nobody chose, and nobody finds out. The trade-off to state plainly in review — a config carrying `temperature` will hard-fail the moment someone points it at Sonnet 5, so model-config owners need to know.
3. **Float coercion** for `temperature`/`top_p` regardless of config type.
4. **Thinking constraint** — the API *requires* `temperature=1` when extended thinking is on, so we force it rather than let a configured 0.2 cause a 400.

---

## 16. `_log_observability` (lines 443–456)

One structured record per **successful** call: token usage, model, project, COIN, and —
when captured — the R2D2 request ID and rate-limit state. The request ID is the join key
with R2D2's own logs when raising proxy support tickets; the rate-limit numbers let
dashboards trend quota consumption. `.model_dump()` converts the Pydantic metrics model to
a plain dict; header keys are renamed dashes→underscores for the logging schema.

Pairs with the **error**-level record in `__generate` (§12) — together they give one
observability entry per call regardless of outcome.

---

## 17. Prepared answers for likely questions

**Q: Why convert DOCX/XLSX/ODT instead of sending them as documents?**
Claude natively parses PDF only. Everything else has to become text or an image before it
reaches the model. We convert on our side via `document_utils` rather than asking users to
pre-convert.

**Q: Why is TIFF handled separately from the other images?**
Claude accepts exactly four image formats — jpeg, png, gif, webp. TIFF is common in
scanned-document workflows here, so we transcode it to PNG rather than reject it.

**Q: Why `media_type: "text/plain"` on a CSV?**
`text/plain` is the only media type the SDK's plain-text document source accepts. The
`TEXT_PLAIN` constant makes that a stated constraint instead of a mystery literal.

**Q: How does a new Claude model get onboarded?**
Usually with no code change: add its prefix to `claude_extra_adaptive_thinking_prefixes`
and/or `claude_extra_no_sampling_prefixes` in the environment config. The hardcoded tuples
are the defaults, not the whole list.

**Q: Why raise on sampling params instead of dropping them?**
A dropped param means the model silently runs at settings nobody chose. The raise names
the parameter and the model and tells the operator what to remove. The cost is that a
config change (model swap) surfaces as a runtime failure rather than a degradation — which
we consider the correct direction for a controlled config.

**Q: What's the difference between ER010, ER012, and GR012?**
ER010 = client construction failed. ER012 = the connection failed during the request
(network-level, no HTTP status). GR012 = the request exceeded our 1200 s timeout. Ordering
in the except chain matters: `APITimeoutError` subclasses `APIConnectionError`.

**Q: Why not reuse one client / connection pool?**
Token freshness. The COIN token is baked into the client at construction and expires.
Per-request construction is the simplest correct design; the alternative is a shared client
with an auth-refresh hook — more machinery, no correctness gain today.

**Q: Is prompt-injected JSON schema guaranteed?**
No — it's highly reliable steering, not enforcement, which is why the instruction forbids
code fences and consumers parse defensively. For a guarantee we flip `native_json_schema`
per model, which uses platform-enforced structured outputs.

**Q: Why is `__generate` name-mangled?**
It must only run inside the retry wrapper, and its error mapping assumes that context.
Double-underscore makes accidental external calls effectively impossible.

**Q: What if a part is a type we don't support?**
Skipped with a warning naming the MIME type and filename; the request proceeds with the
remaining parts. The prompt text is always appended, so the message is never empty.

**Q: How is this tested?**
`test_claude_generator.py` — 44 tests, all passing, no network and no framework install.
The `query` framework, `anthropic` SDK, and `document_utils` are stubbed via `sys.modules`,
so the four converters return sentinels and the tests assert purely on *routing*. Coverage:
all five MIME branches (including TIFF transcode and per-format converter dispatch),
`resolve_error_code`'s full status matrix, max_tokens resolution order, both schema modes,
thinking translation for legacy/modern/env-extended models, the GR007 sampling raise,
float coercion, the temperature-1 rule, allowlist filtering, part-skipping, and
`unwrap_llm_response`. Run: `python3 -m unittest test_claude_generator -v`.

---

## 18. Open items — raise these before the reviewer does

Walking in with these already identified is a much stronger position than being surprised
by them.

**1. Client-leak ordering (lines 229–241) — the one real bug.** The client is built at 230,
but `_build_message_content` runs at 233 and the `try/finally: client.close()` doesn't
start until 237. On the old branch the code in between was pure dict-building; now it runs
`b64decode`, `.decode()`, `word_to_text`, `xlsx_to_text`, `odt_to_text`, and `tiff_to_png`
— all of which can throw on a malformed upload. Any of those raises and the
`httpx.AsyncClient` never closes, leaking a connection pool per bad file. **Fix: move lines
233–234 above line 229.** No other change needed.

**2. `.decode("utf-8")` (line 124) crashes on non-UTF-8 text.** A CSV exported from Excel
in Windows-1252, or most real-world RTF, raises `UnicodeDecodeError` — uncaught, so it
surfaces as an unhandled 500 instead of a clean error code. There's a test documenting this
(`test_non_utf8_text_raises_unicodedecodeerror`). Options: `errors="replace"`, or a
try/except returning `None` so the part is skipped via the existing warning path.

**3. RTF is routed as plain text (lines 45–46).** `application/rtf` and `text/rtf` sit in
`_CLAUDE_TEXT_MIME_TYPES`, so Claude receives raw `{\rtf1\ansi\deff0...` control words
rather than prose. If RTF matters to the use case it belongs in `_CLAUDE_OTHER_MIME_TYPES`
with a converter; if it's rare, this is acceptable — just know that's what the model sees.

**4. `except httpx.ConnectError` (line 231) is unreachable.** Constructing
`AsyncAnthropicVertex`/`httpx.AsyncClient` performs no network I/O — no connection is
attempted until the request is sent. Real connection failures surface inside `__generate`
as `APIConnectionError` → ER012. If the intent is "token fetch failed", the exception to
catch is whatever `token_roller.get_token()` raises.

**5. Smaller items.** The `else: return None` at line 141 is unreachable (the `if/elif`
chain covers exactly the three members of the frozenset); `retry_config:
ModelRetryConfig = ModelRetryConfig()` in both signatures is the classic mutable-default
trap (one instance shared across every call — resolve to `None` and default inside);
`use_case` is stored in `__init__` but never used, so either log it in
`_log_observability` for per-team attribution or drop the parameter.
