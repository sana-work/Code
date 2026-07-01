from __future__ import annotations

import inspect
import logging
from typing import Dict, List, Tuple
import json
import httpx
from anthropic import AsyncAnthropicVertex, APIStatusError, APITimeoutError
from anthropic.types import Message
from google.oauth2.credentials import Credentials
from anthropic.resources.messages.messages import AsyncMessages
from query.config.environment import ClaudeEnvironment
from query.core.generator.generator import Generator
from query.models.confidence_score_response import ConfidenceScoreResponse
from query.models.generation_metadata import ModelConfig, ModelProvider, ModelRetryConfig
from query.models.llm_usage_metrics import LLMUsageMetrics
from query.models.observability import ObservabilityLogType, ObservabilityLogger
from query.models.part_holder import PartHolder
from query.util.error_codes import ErrorCodes
from query.util.exception_handler import GenaiCommonException
from query.util.logging_utils import is_debug_logging_enabled
from query.util.proxy_token_roller import ProxyTokenRoller
from query.util.retry_utils import retry_wrapper

logger = logging.getLogger(__name__)


_CLAUDE_IMAGE_MIME_TYPES: frozenset[str] = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
})

# Sent to Claude as "type": "document" blocks
_CLAUDE_DOCUMENT_MIME_TYPES: frozenset[str] = frozenset({
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "application/epub+zip",
    "text/plain",
    "text/html",
    "text/csv",
    "text/tab-separated-values",
    "application/json",
    "application/rtf",
    "text/rtf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
})

# Params already handled explicitly in _build_create_args — never forwarded from model_parameters.
_CLAUDE_HANDLED_PARAMS: frozenset[str] = frozenset({
    "model", "max_tokens", "max_output_tokens",  # resolved separately
    "messages", "system",                        # built from prompts
    "thinking", "thinking_config",                # thinking built from thinking_config
})

# SDK / transport keys that appear in the method signature but are not API body params.
_SDK_INTERNAL_PARAMS: frozenset[str] = frozenset({
    "self", "extra_headers", "extra_query", "extra_body", "timeout", "stream",
})

# Static fallback used when SDK introspection fails.
_FALLBACK_ALLOWED_PARAMS: frozenset[str] = frozenset({
    "temperature", "top_p", "stop_sequences", "top_k", "metadata",
})


def _derive_claude_api_params() -> frozenset[str]:
    """
    Derive forwardable Anthropic API parameters from the SDK's AsyncMessages.create
    signature. Called exactly once, at import time (see _CLAUDE_API_PARAMS below) —
    the signature can't change during the process lifetime, so there is nothing to
    cache or recompute on later calls. Falls back to a static safe set if
    introspection fails (e.g. SDK internal refactor changes the import path).
    """
    try:
        sig = inspect.signature(AsyncMessages.create)
        params = frozenset(
            name for name in sig.parameters
            if name not in _SDK_INTERNAL_PARAMS
            and name not in _CLAUDE_HANDLED_PARAMS
        )
        if params:
            logger.debug("Claude API params derived from SDK signature: %s", sorted(params))
            return params
    except Exception as exc:
        logger.warning(
            "Could not introspect Anthropic SDK signature; using fallback params. Error: %s", exc
        )
    return _FALLBACK_ALLOWED_PARAMS


# Computed once at import time — every call site reads this constant directly,
# no decorator/cache lookup involved.
_CLAUDE_API_PARAMS: frozenset[str] = _derive_claude_api_params()


# Parameters whose values must always be sent as float
_FLOAT_MODEL_PARAMS: frozenset[str] = frozenset({"temperature", "top_p"})

# Conservative output-token ceiling used when a model isn't in the 128K set below.
_CLAUDE_MAX_OUTPUT_TOKENS: int = 64000

# Model-ID prefixes whose Anthropic-hosted output ceiling is 128K tokens
# (Opus 4.6+, Sonnet 4.6+, Fable 5 / Mythos 5). Everything else — Haiku,
# Sonnet <= 4.5, Opus <= 4.5, and any model ID we don't recognize yet — falls
# back to the conservative 64K ceiling in _CLAUDE_MAX_OUTPUT_TOKENS. Update
# this tuple as new model tiers launch.
_CLAUDE_128K_MODEL_PREFIXES: Tuple[str, ...] = (
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos-5",
)

# Model-ID prefixes (4.6+) where manual extended thinking
# ({"type": "enabled", "budget_tokens": N}) is deprecated (4.6) or returns a
# 400 (4.7+ / Sonnet 5 / Fable 5) — these models take {"type": "adaptive"}.
_CLAUDE_ADAPTIVE_THINKING_PREFIXES: Tuple[str, ...] = _CLAUDE_128K_MODEL_PREFIXES

# Model-ID prefixes (4.7+) where sampling params (temperature / top_p / top_k)
# were removed from the API — sending them returns a 400.
_CLAUDE_NO_SAMPLING_PREFIXES: Tuple[str, ...] = (
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos-5",
)

_SAMPLING_PARAMS: frozenset[str] = frozenset({"temperature", "top_p", "top_k"})


def _bare_model_name(model_name: str) -> str:
    """Strip the Vertex "@<snapshot-date>" suffix (e.g. "claude-opus-4-5@20251101")."""
    return model_name.split("@", 1)[0]


def _resolve_model_max_output_tokens(model_name: str) -> int:
    """Return the real output-token ceiling for a Claude model ID."""
    if _bare_model_name(model_name).startswith(_CLAUDE_128K_MODEL_PREFIXES):
        return 128000
    return _CLAUDE_MAX_OUTPUT_TOKENS


# Explicit request timeout (seconds) passed to client.messages.stream() to ensure
# the SDK uses this value instead of calculating one from max_tokens.
_CLAUDE_REQUEST_TIMEOUT: httpx.Timeout = httpx.Timeout(timeout=600.0, connect=30.0)


# ------------------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------------------

def _make_r2d2_header_hook(headers_capture: dict):
    """Factory: returns a per-request httpx event-hook that captures and logs R2D2 rate-limit headers."""
    async def _hook(response: httpx.Response) -> None:
        header_keys = {
            "x-r2d2-requestid":   "x-r2d2-requestid",
            "ratelimit-limit":    "ratelimit-limit",
            "ratelimit-remaining": "ratelimit-remaining",
        }
        extra = {
            field: response.headers[header]
            for header, field in header_keys.items()
            if response.headers.get(header)
        }
        if extra:
            headers_capture.update(extra)
            logger.info("R2D2 response headers", extra=extra)
    return _hook


def _build_content_block(part: PartHolder) -> dict | None:
    """
    Convert a PartHolder into the appropriate Claude API content block.

    Returns None when the MIME type is unsupported (caller logs and skips it).
    """
    source = {"type": "base64", "media_type": part.mime_type, "data": part.data}

    if part.mime_type in _CLAUDE_IMAGE_MIME_TYPES:
        return {"type": "image", "source": source}

    if part.mime_type in _CLAUDE_DOCUMENT_MIME_TYPES:
        return {"type": "document", "source": source}

    return None


# ------------------------------------------------------------------------------
# ClaudeGenerator
# ------------------------------------------------------------------------------

class ClaudeGenerator(Generator):
    """
    Generator implementation for Anthropic Claude models.

    Builds requests in the Anthropic Messages API format and routes them
    through the Citi R2D2 proxy via AnthropicVertex SDK.

    Part routing:
      - image/jpeg, image/png, image/gif, image/webp  ->  type: image
      - PDF, DOCX, TXT, HTML, RTF, ODT, EPUB,
        CSV, XLSX, JSON, TSV                           ->  type: document
    """

    def __init__(
        self,
        environment: ClaudeEnvironment,
        token_roller: ProxyTokenRoller,
        llm_config: ModelConfig,
        use_case: str,
    ) -> None:
        self.environment = environment
        self.token_roller = token_roller
        self.llm_config = llm_config
        self.use_case = use_case
        # Mirrors VertexAiGenerator's resolution order: explicit model_config
        # override wins, otherwise fall back to the environment default.
        self.project_id = self.llm_config.project_id or environment.claude_project_id

    # ------------------------------------------------------------------
    # Generator interface
    # ------------------------------------------------------------------

    async def generate(
        self,
        system_prompt: str,
        prompt: str,
        soeid: str,
        response_schema: Dict = None,
        max_tokens: int = None,
        retry_config: ModelRetryConfig = ModelRetryConfig(),
    ) -> Tuple[Message, LLMUsageMetrics]:
        """Text-only generation - delegates to generate_multimodal with no parts."""
        return await self.generate_multimodal(
            system_prompt, prompt, [], soeid, response_schema, max_tokens, retry_config
        )

    async def generate_multimodal(
        self,
        system_prompt: str,
        prompt: str,
        parts: List[PartHolder],
        soeid: str,
        response_schema: Dict = None,
        max_tokens: int = None,
        retry_config: ModelRetryConfig = ModelRetryConfig(),
    ) -> Tuple[Message, LLMUsageMetrics]:
        """
        Multimodal generation supporting images and documents alongside text.

        Args:
            system_prompt: System instruction for the model.
            prompt:        User text prompt (always appended last in the message).
            parts:         Optional list of image / document parts.
            soeid:         SOEID of the requesting user (forwarded as x-r2d2-user).
            response_schema: Optional JSON schema injected into the system prompt.
            max_tokens:    Override for maximum output tokens.
            retry_config:  Retry configuration.

        Returns:
            Tuple of (Anthropic Message, LLMUsageMetrics).
        """

        r2d2_headers: dict = {}
        client = self._build_client(r2d2_headers)
        content = self._build_message_content(parts, prompt)
        create_args = self._build_create_args(system_prompt, content, max_tokens, response_schema)

        logger.info(
            "Calling Claude LLM with R2D2 - %s - using model - %s",
            self.llm_config.r2d2_coin, self.llm_config.name,
        )

        try:
            generate_with_retry = retry_wrapper(self.__generate, retry_config)
            return await generate_with_retry(client, create_args, soeid, r2d2_headers)
        finally:
            # A fresh httpx.AsyncClient is created per request in _build_client;
            # close it (after all retries) or each request leaks a connection pool.
            await client.close()

    @staticmethod
    def unwrap_llm_response(response: Message) -> Tuple[str, ConfidenceScoreResponse]:
        """
        Extract the first text block from a Claude Message response.

        Claude does not expose log-probabilities, so confidence_score is always 0.
        (Unlike VertexAiGenerator.unwrap_llm_response, there is no dict-vs-str
        branch here — Claude has no native JSON mode; response_schema is injected
        into the system prompt, so block.text is always a plain string.)

        Raises:
            ValueError: If the response contains no content or no text block.
        """
        if not response.content:
            raise ValueError("No content in Claude completion response")

        for block in response.content:
            if block.type == "text":
                return block.text, ConfidenceScoreResponse(
                    confidence_score=0,
                    token_wise_confidence_scores=[],
                )

        raise ValueError("No text content block in Claude completion response")

    @property
    def default_prompt_id(self) -> str:
        return self.llm_config.default_prompt_id

    @staticmethod
    def get_platform() -> ModelProvider:
        return ModelProvider.CLAUDE

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    async def __generate(
        self, client: AsyncAnthropicVertex, create_args: dict, soeid: str, r2d2_headers: dict = None
    ) -> Tuple[Message, LLMUsageMetrics]:

        try:
            # Streamed rather than a single non-streaming create() call: at
            # this model's max_tokens (up to 128K), generation can run well
            # past the point where an idle non-streaming connection gets
            # dropped by an intermediate proxy/load balancer. Streaming keeps
            # bytes flowing continuously so the connection is never idle, and
            # get_final_message() still hands back the same Message object
            # create() would have — callers of __generate are unaffected.
            async with client.messages.stream(
                extra_headers={"x-r2d2-user": soeid},
                timeout=_CLAUDE_REQUEST_TIMEOUT,
                **create_args,
            ) as stream:
                response = await stream.get_final_message()
        except APIStatusError as e:
            # Always log the raw API error body so we can diagnose 400s
            logger.error(
                "Claude API error %s: %s | request_id=%s | body=%s",
                e.status_code,
                e.message,
                getattr(e, 'request_id', 'n/a'),
                e.body if hasattr(e, 'body') else str(e),
            )
            if e.status_code == 429:
                raise GenaiCommonException(ErrorCodes.GR008, ErrorCodes.GR008.get_description(), e) from e
            elif e.status_code == 400:
                raise GenaiCommonException(ErrorCodes.GR007, ErrorCodes.GR007.get_description(), e) from e
            elif 400 <= e.status_code < 500:
                raise GenaiCommonException(ErrorCodes.GR010, ErrorCodes.GR010.get_description(), e) from e
            else:
                raise GenaiCommonException(ErrorCodes.GR009, ErrorCodes.GR009.get_description(), e) from e
        except APITimeoutError as e:
            raise GenaiCommonException(ErrorCodes.GR012, ErrorCodes.GR012.get_description(), e) from e

        usage_metrics = LLMUsageMetrics.from_claude_response(response)
        logger.info("Logging for usage_metrics = %s , response = %s", usage_metrics, response)
        self._log_observability(usage_metrics, r2d2_headers or {})
        return response, usage_metrics

    def _build_client(self, headers_capture: dict) -> AsyncAnthropicVertex:
        """
        Construct a fresh AsyncAnthropicVertex client per request so the
        COIN token is always current.
        """

        return AsyncAnthropicVertex(
            region=self.environment.claude_region,
            project_id=self.project_id,
            credentials=Credentials(self.token_roller.get_token()),
            http_client=httpx.AsyncClient(
                event_hooks={"response": [_make_r2d2_header_hook(headers_capture)]}
            ),
            base_url=self.environment.claude_api_base,
        )

    def _build_message_content(
        self, parts: List[PartHolder], prompt: str
    ) -> List[dict]:
        """
        Build the ordered content list for a single user message: one block
        per image/document part, followed by the text prompt.

        Unsupported MIME types are skipped with a warning.
        """
        content: List[dict] = []

        for part in parts:
            block = _build_content_block(part)
            if block is not None:
                content.append(block)
            else:
                logger.warning(
                    "Unsupported MIME type '%s' for file '%s'; part skipped.",
                    part.mime_type, part.filename,
                )

        content.append({"type": "text", "text": prompt})
        return content

    def _build_create_args(
        self,
        system_prompt: str,
        content: List[dict],
        max_tokens: int | None,
        response_schema: dict | None = None,
    ) -> dict:
        """
        Assemble the keyword arguments for client.messages.stream().

        Forwards only the model parameters listed in _CLAUDE_API_PARAMS.
        Numeric float parameters (temperature, top_p) are coerced to float.
        When response_schema is provided it is injected into the system prompt
        as a JSON schema instruction (Claude has no native schema parameter).
        """

        resolved_max_tokens = min(
            max_tokens
            or self.llm_config.model_parameters.get("max_tokens")
            or self.llm_config.model_parameters.get("max_output_tokens")
            or 8192,
            # Per-model ceiling (64K or 128K) instead of a single global
            # constant — a flat 64K cap silently halves the real ceiling on
            # every 4.6+ model (Opus 4.6/4.7/4.8, Sonnet 4.6/5, Fable 5).
            _resolve_model_max_output_tokens(self.llm_config.name),
        )
        args: dict = {
            "model": self.llm_config.name,
            "max_tokens": resolved_max_tokens,
            "messages": [{"role": "user", "content": content}],
        }

        if response_schema:
            schema_instruction = (
                f"You must respond with valid JSON only, strictly conforming to this JSON schema:\n"
                f"{json.dumps(response_schema)}"
            )
            system_prompt = f"{system_prompt}\n\n{schema_instruction}" if system_prompt else schema_instruction

        if system_prompt:
            args["system"] = system_prompt

        bare_model = _bare_model_name(self.llm_config.name)
        adaptive_thinking_model = bare_model.startswith(_CLAUDE_ADAPTIVE_THINKING_PREFIXES)
        sampling_removed_model = bare_model.startswith(_CLAUDE_NO_SAMPLING_PREFIXES)

        thinking_enabled = False
        thinking_config = self.llm_config.model_parameters.get("thinking_config")
        if isinstance(thinking_config, dict):
            budget = thinking_config.get("thinking_budget")
            if budget is not None:
                if adaptive_thinking_model:
                    # budget_tokens is deprecated on 4.6 and returns a 400 on
                    # 4.7+ / Sonnet 5 / Fable 5 — these models decide their own
                    # thinking depth via adaptive mode.
                    args["thinking"] = {"type": "adaptive"}
                else:
                    args["thinking"] = {"type": "enabled", "budget_tokens": int(budget)}
                thinking_enabled = True

        for param, value in self.llm_config.model_parameters.items():
            if param not in _CLAUDE_API_PARAMS:
                continue
            if sampling_removed_model and param in _SAMPLING_PARAMS:
                # temperature/top_p/top_k were removed on 4.7+ models —
                # forwarding them returns a 400, so drop them from the request.
                logger.warning(
                    "Dropping sampling param '%s' — not supported by model %s",
                    param, self.llm_config.name,
                )
                continue
            coerced = float(value) if param in _FLOAT_MODEL_PARAMS else value
            # Anthropic requires temperature=1 when extended thinking is enabled
            if param == "temperature" and thinking_enabled:
                coerced = 1.0
            args[param] = coerced

        return args

    def _log_observability(self, usage_metrics: LLMUsageMetrics, r2d2_headers: dict = None) -> None:
        """Emit a structured observability log entry after a successful call."""
        usage_metrics_dict = usage_metrics.model_dump() if usage_metrics else {}
        if r2d2_headers:
            usage_metrics_dict["x_r2d2_requestid"] = r2d2_headers.get("x-r2d2-requestid")
            usage_metrics_dict["ratelimit_limit"] = r2d2_headers.get("ratelimit-limit")
            usage_metrics_dict["ratelimit_remaining"] = r2d2_headers.get("ratelimit-remaining")
        ObservabilityLogger.get_logger().info({
            "observability_type": ObservabilityLogType.OTHER.value,
            "model": self.llm_config.name,
            "project_id": self.project_id,
            "r2d2_coin": self.llm_config.r2d2_coin,
            "usage_metrics": usage_metrics_dict,
        })
