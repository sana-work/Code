from __future__ import annotations

import logging
from typing import Dict, List, Tuple
import json
import httpx
from anthropic import AsyncAnthropicVertex, APIConnectionError, APIStatusError, APITimeoutError
from anthropic.types import Message
from google.oauth2.credentials import Credentials
from query.config.environment import ClaudeEnvironment
from query.core.generator.generator import Generator
from query.models.confidence_score_response import ConfidenceScoreResponse
from query.models.generation_metadata import ModelConfig, ModelProvider, ModelRetryConfig
from query.models.llm_usage_metrics import LLMUsageMetrics
from query.models.observability import ObservabilityLogType, ObservabilityLogger
from query.models.part_holder import PartHolder
from query.util.error_codes import ErrorCodes
from query.util.exception_handler import GenaiCommonException
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

_ALLOWED_MODEL_PARAMS: frozenset[str] = frozenset({
    "temperature", "top_p", "stop_sequences", "top_k", "metadata",
})


# Parameters whose values must always be sent as float
_FLOAT_MODEL_PARAMS: frozenset[str] = frozenset({"temperature", "top_p"})

# Bare model IDs (Vertex "@<snapshot>" suffix stripped) that still take MANUAL
# extended thinking ({"type": "enabled", "budget_tokens": N}). This is a
# closed set: 4.6 deprecated budget_tokens and 4.7+ / Sonnet 5 reject it with
# a 400, so every newer model — and anything unrecognized, i.e. future models —
# defaults to {"type": "adaptive"} and works without touching this file.
_CLAUDE_MANUAL_THINKING_MODELS: frozenset[str] = frozenset({
    "claude-3-7-sonnet",
    "claude-opus-4",
    "claude-opus-4-1",
    "claude-opus-4-5",
    "claude-sonnet-4",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
})

# Bare model IDs that still accept sampling params (temperature / top_p /
# top_k). Sampling was removed from the API in 4.7, so on 4.7+ / Sonnet 5 —
# and by default on unrecognized future models — these params are dropped
# before the request. 4.6 kept sampling while deprecating manual thinking,
# hence the extra entries beyond the manual-thinking set. Also a closed set.
_CLAUDE_SAMPLING_PARAM_MODELS: frozenset[str] = _CLAUDE_MANUAL_THINKING_MODELS | frozenset({
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-3-5-sonnet",
    "claude-3-5-sonnet-v2",
    "claude-3-5-haiku",
    "claude-3-opus",
    "claude-3-sonnet",
    "claude-3-haiku",
})

_SAMPLING_PARAMS: frozenset[str] = frozenset({"temperature", "top_p", "top_k"})


def _bare_model_name(model_name: str) -> str:
    """Strip the Vertex "@<snapshot-date>" suffix (e.g. "claude-opus-4-5@20251101")."""
    return model_name.split("@", 1)[0]


# Explicit request timeout (seconds) passed on every request so the SDK uses
# this value instead of deriving one from max_tokens. Must cover the slowest
# generation we run (e.g. 64K-token outputs); a large ceiling costs nothing on
# fast requests — it only bounds how long the SDK will wait.
_CLAUDE_REQUEST_TIMEOUT: httpx.Timeout = httpx.Timeout(timeout=1200.0, connect=30.0)


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
        self.project_id = self.llm_config.project_id or environment.claude_project_id

    async def generate(
        self,
        system_prompt: str,
        prompt: str,
        soeid: str,
        response_schema: Dict = None,
        max_tokens: int = None,
        retry_config: ModelRetryConfig = None,
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
        retry_config: ModelRetryConfig = None,
    ) -> Tuple[Message, LLMUsageMetrics]:
        """
        Multimodal generation supporting images and documents alongside text.

        Args:
            system_prompt: System instruction for the model.
            prompt:        User text prompt (always appended last in the message).
            parts:         Optional list of image / document parts.
            soeid:         SOEID of the requesting user (forwarded as x-r2d2-user).
            response_schema: Optional JSON schema (native or prompt-injected,
                           depending on the model's native_json_schema flag).
            max_tokens:    Override for maximum output tokens.
            retry_config:  Retry configuration (defaults to ModelRetryConfig()).

        Returns:
            Tuple of (Anthropic Message, LLMUsageMetrics).
        """

        # Not a signature default: a mutable default instance would be shared
        # across every call and could leak retry state between requests.
        retry_config = retry_config or ModelRetryConfig()

        # Build the request payload BEFORE the client: these can raise on bad
        # config, and no client exists yet to leak.
        content = self._build_message_content(parts, prompt)
        create_args = self._build_create_args(system_prompt, content, max_tokens, response_schema)

        logger.info(
            "Calling Claude LLM with R2D2 - %s - using model - %s",
            self.llm_config.r2d2_coin, self.llm_config.name,
        )

        r2d2_headers: dict = {}
        try:
            client = self._build_client(r2d2_headers)
        except Exception as e:
            # Client construction does no network I/O, but the COIN token fetch
            # via ProxyTokenRoller can fail (expired session, IAM hiccup).
            # Surface any setup failure as ER010 — deliberately outside the
            # retry loop, since retrying with broken setup cannot succeed.
            raise GenaiCommonException(ErrorCodes.ER010, ErrorCodes.ER010.get_description(), e) from e

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
        branch here — whether response_schema was prompt-injected or natively
        enforced via output_config, the answer arrives as a text block, so
        block.text is always a plain string.)

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

    async def __generate(
        self, client: AsyncAnthropicVertex, create_args: dict, soeid: str, r2d2_headers: dict = None
    ) -> Tuple[Message, LLMUsageMetrics]:

        try:
            async with client.messages.stream(
                extra_headers={"x-r2d2-user": soeid},
                timeout=_CLAUDE_REQUEST_TIMEOUT,
                **create_args,
            ) as stream:
                response = await stream.get_final_message()
        except APIStatusError as e:
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
            # Must precede APIConnectionError: APITimeoutError subclasses it.
            raise GenaiCommonException(ErrorCodes.GR012, ErrorCodes.GR012.get_description(), e) from e
        except APIConnectionError as e:
            raise GenaiCommonException(ErrorCodes.ER012, ErrorCodes.ER012.get_description(), e) from e

        usage_metrics = LLMUsageMetrics.from_claude_response(response)
        logger.info("Claude usage metrics: %s", usage_metrics)
        # Full model output only at DEBUG: at 64K max_tokens this can be huge
        # and may contain client data — keep it out of routine INFO logs.
        logger.debug("Claude raw response: %s", response)
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
        Assemble the keyword arguments for the Messages API call.

        Forwards only the model parameters listed in _ALLOWED_MODEL_PARAMS.
        Numeric float parameters (temperature, top_p) are coerced to float.

        response_schema handling (two modes):
          - model_parameters["native_json_schema"] truthy -> platform-enforced
            structured outputs via output_config.format.
          - otherwise -> schema injected into the system prompt as an
            instruction (reliable, but not enforced).
        """

        resolved_max_tokens = (
            max_tokens
            or self.llm_config.model_parameters.get("max_tokens")
            or self.llm_config.model_parameters.get("max_output_tokens")
            or 64000
        )
        args: dict = {
            "model": self.llm_config.name,
            "max_tokens": resolved_max_tokens,
            "messages": [{"role": "user", "content": content}],
        }

        if response_schema:
            if self.llm_config.model_parameters.get("native_json_schema"):
                args["output_config"] = {
                    "format": {"type": "json_schema", "schema": response_schema}
                }
            else:
                schema_instruction = (
                    "You must respond with valid JSON only, strictly conforming to this JSON schema:\n"
                    f"{json.dumps(response_schema)}\n"
                    "Output raw JSON only - do not wrap it in markdown code fences, "
                    "and do not include any text before or after the JSON."
                )
                system_prompt = (
                    f"{system_prompt}\n\n{schema_instruction}" if system_prompt else schema_instruction
                )
        if system_prompt:
            args["system"] = system_prompt

        bare_model = _bare_model_name(self.llm_config.name)
        manual_thinking_model = bare_model in _CLAUDE_MANUAL_THINKING_MODELS
        sampling_param_model = bare_model in _CLAUDE_SAMPLING_PARAM_MODELS

        thinking_enabled = False
        thinking_config = self.llm_config.model_parameters.get("thinking_config")
        if isinstance(thinking_config, dict):
            budget = thinking_config.get("thinking_budget")
            if budget is not None:
                if manual_thinking_model:
                    args["thinking"] = {"type": "enabled", "budget_tokens": int(budget)}
                else:
                    # 4.6+ and anything unrecognized (i.e. future models):
                    # budget_tokens is deprecated/rejected — the model manages
                    # its own thinking depth in adaptive mode.
                    args["thinking"] = {"type": "adaptive"}
                thinking_enabled = True

        for param, value in self.llm_config.model_parameters.items():
            if param not in _ALLOWED_MODEL_PARAMS:
                continue
            if param in _SAMPLING_PARAMS and not sampling_param_model:
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
            "use_case": self.use_case,
            "r2d2_coin": self.llm_config.r2d2_coin,
            "usage_metrics": usage_metrics_dict,
        })
