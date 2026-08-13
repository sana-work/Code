from __future__ import annotations
import base64
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
from query.util.document_utils import word_to_text, xlsx_to_text, odt_to_text, tiff_to_png
from query.util.error_codes import ErrorCodes
from query.util.exception_handler import GenaiCommonException
from query.util.proxy_token_roller import ProxyTokenRoller
from query.util.retry_utils import retry_wrapper


logger = logging.getLogger(__name__)

#Sent to Claude as "type": "image" blocks with source type "base64"
_CLAUDE_IMAGE_MIME_TYPES: frozenset[str] = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
})

# Constant for the only media_type accepted by Anthropic's PlainTextSourceParam
TEXT_PLAIN: str = "text/plain"

#Sent to Claude as "type": "text" blocks with source type "base64"
_CLAUDE_TEXT_MIME_TYPES: frozenset[str] = frozenset({
    TEXT_PLAIN,
    "text/html",
    "text/htm",
    "text/csv",
    "text/tab-separated-values",
    "application/json",
    "application/rtf",
    "text/rtf",
})

# Sent to Claude as "type": "document" blocks with source type "base64"
_CLAUDE_DOCUMENT_MIME_TYPES: frozenset[str] = frozenset({
    "application/pdf",
})

#Sent to Claude as "type": "text" blocks converted to plain text
_CLAUDE_OTHER_MIME_TYPES: frozenset[str] = frozenset({
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.oasis.opendocument.text",
})

# Sent to Claude as "type": "image" blocks after converting to PNG
_CLAUDE_CONVERT_IMAGE_MIME_TYPES: frozenset[str] = frozenset({
    "image/tiff",
})


_ALLOWED_MODEL_PARAMS: frozenset[str] = frozenset({
    "temperature", "top_p", "stop_sequences", "top_k", "metadata",
})


# Parameters whose values must always be sent as float
_FLOAT_MODEL_PARAMS: frozenset[str] = frozenset({"temperature", "top_p"})

# Model-ID prefixes (4.6+) where manual extended thinking is deprecated — these models use {"type": "adaptive"}.
_CLAUDE_ADAPTIVE_THINKING_PREFIXES: Tuple[str, ...] = (
    "claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8",
    "claude-sonnet-4-6", "claude-sonnet-4-7", "claude-sonnet-4-8", "claude-sonnet-5",
)

# Model-ID prefixes (4.7+) where sampling params are removed from the API — sending them returns a 400.
_CLAUDE_NO_SAMPLING_PREFIXES: Tuple[str, ...] = (
    "claude-opus-4-7", "claude-opus-4-8",
    "claude-sonnet-4-7", "claude-sonnet-4-8", "claude-sonnet-5",
)

_SAMPLING_PARAMS: frozenset[str] = frozenset({"temperature", "top_p", "top_k"})

# R2D2 rate-limit response headers to capture and forward to observability logs
_R2D2_TRACKED_HEADERS: Tuple[str, ...] = ("x-r2d2-requestid", "ratelimit-limit", "ratelimit-remaining")

def _bare_model_name(model_name: str) -> str:
    """Strip the Vertex "@<snapshot-date>" suffix (e.g. "claude-opus-4-5@20251101")."""
    return model_name.split("@", 1)[0]


# Explicit request timeout (seconds) passed to client.messages.create() to ensure
# the SDK uses this value instead of calculating one from max_tokens.
_CLAUDE_REQUEST_TIMEOUT: httpx.Timeout = httpx.Timeout(timeout=1200.0, connect=30.0)


def _make_r2d2_header_hook(headers_capture: dict):
    """Factory: returns a per-request httpx event-hook that captures and logs R2D2 rate-limit headers."""
    async def _hook(response: httpx.Response) -> None:
        extra = {h: response.headers[h] for h in _R2D2_TRACKED_HEADERS if response.headers.get(h)}
        if extra:
            headers_capture.update(extra)
    return _hook


def _build_content_block(part: PartHolder) -> dict | None:
    """
    Convert a PartHolder into the appropriate Claude API content block.

    Returns None when the MIME type is unsupported (caller logs and skips it).
    """

    #Check the type
    if part.mime_type in _CLAUDE_IMAGE_MIME_TYPES:
        source = {"type": "base64", "media_type": part.mime_type, "data": part.data}
        return {"type": "image", "source": source}

    if part.mime_type in _CLAUDE_TEXT_MIME_TYPES:
        decoded_text = base64.b64decode(part.data).decode("utf-8")
        source = {"type": "text", "media_type": TEXT_PLAIN, "data": decoded_text}
        return {"type": "document", "source": source}

    if part.mime_type in _CLAUDE_DOCUMENT_MIME_TYPES:
        source = {"type": "base64", "media_type": part.mime_type, "data": part.data}
        return {"type": "document", "source": source}

    if part.mime_type in _CLAUDE_OTHER_MIME_TYPES:
        raw_bytes = base64.b64decode(part.data)
        mime = part.mime_type
        if mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            converted_text = word_to_text(raw_bytes)
        elif mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            converted_text = xlsx_to_text(raw_bytes)
        elif mime == "application/vnd.oasis.opendocument.text":
            converted_text = odt_to_text(raw_bytes)
        else:
            return None
        source = {"type": "text", "media_type": TEXT_PLAIN, "data": converted_text}
        return {"type": "document", "source": source}

    if part.mime_type in _CLAUDE_CONVERT_IMAGE_MIME_TYPES:
        raw_bytes = base64.b64decode(part.data)
        png_bytes = tiff_to_png(raw_bytes)
        png_b64 = base64.b64encode(png_bytes).decode("utf-8")
        source = {"type": "base64", "media_type": "image/png", "data": png_b64}
        return {"type": "image", "source": source}

    return None


def resolve_error_code(status_code: int) -> ErrorCodes:
    if status_code == 429:
        return ErrorCodes.GR008
    if status_code == 400:
        return ErrorCodes.GR007
    if 400 <= status_code < 500:
        return ErrorCodes.GR010
    return ErrorCodes.GR009


class ClaudeGenerator(Generator):
    """
    Generator implementation for Anthropic Claude models.

    Builds requests in the Anthropic Messages API format and routes them
    through the Citi R2D2 proxy via AnthropicVertex SDK.

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
        try:
            client = self._build_client(r2d2_headers)
        except httpx.ConnectError as e:
            raise GenaiCommonException(ErrorCodes.ER010, ErrorCodes.ER010.get_description(), e) from e
        content = self._build_message_content(parts, prompt)
        create_args = self._build_create_args(system_prompt, content, max_tokens, response_schema)


        try:
            generate_with_retry = retry_wrapper(self.__generate, retry_config)
            return await generate_with_retry(client, create_args, soeid, r2d2_headers)
        finally:
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

        text_block = next((b for b in response.content if b.type == "text"), None)
        if not text_block:
            raise ValueError("No text content block in Claude completion response")
        return text_block.text, ConfidenceScoreResponse(confidence_score=0, token_wise_confidence_scores=[])

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
            response = await client.messages.create(
                extra_headers={"x-r2d2-user": soeid},
                timeout=_CLAUDE_REQUEST_TIMEOUT,
                **create_args,
            )
        except APIStatusError as e:
            status = e.status_code
            response_obj = getattr(e, "response", None)
            hdrs = dict(getattr(response_obj, "headers", {}) or {})

            ObservabilityLogger.get_logger().error({
                "observability_type": ObservabilityLogType.ERROR.value,
                "model": self.llm_config.name,
                "r2d2_coin": self.llm_config.r2d2_coin,
                "status_code": status,
                "x_r2d2_requestid": hdrs.get("x-r2d2-requestid"),
                "ratelimit_limit": hdrs.get("ratelimit-limit"),
                "ratelimit_remaining": hdrs.get("ratelimit-remaining"),
                "x_r2d2_response_source": hdrs.get("x-r2d2-response-source")
            })
            raise GenaiCommonException(resolve_error_code(e.status_code), e.message, e) from e
        except APITimeoutError as e:
            msg = ErrorCodes.GR012.get_description()
            raise GenaiCommonException(ErrorCodes.GR012, msg, e) from e
        except APIConnectionError as e:
            msg = ErrorCodes.ER012.get_description()
            raise GenaiCommonException(ErrorCodes.ER012, msg, e) from e

        usage_metrics = LLMUsageMetrics.from_claude_response(response)
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
        Assemble the keyword arguments for client.messages.create().

        Forwards only the model parameters listed in _ALLOWED_MODEL_PARAMS.
        Numeric float parameters (temperature, top_p) are coerced to float.
        When response_schema is provided it is injected into the system prompt
        as a JSON schema instruction (Claude has no native schema parameter).
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
        adaptive_thinking_prefixes = _CLAUDE_ADAPTIVE_THINKING_PREFIXES + tuple(
            self.environment.claude_extra_adaptive_thinking_prefixes
        )
        no_sampling_prefixes = _CLAUDE_NO_SAMPLING_PREFIXES + tuple(
            self.environment.claude_extra_no_sampling_prefixes
        )
        adaptive_thinking_model = bare_model.startswith(adaptive_thinking_prefixes)
        sampling_removed_model = bare_model.startswith(no_sampling_prefixes)

        thinking_enabled = self._apply_thinking_config(args, adaptive_thinking_model)
        self._apply_model_params(args, sampling_removed_model, thinking_enabled)

        return args

    def _apply_thinking_config(self, args: dict, adaptive_thinking_model: bool) -> bool:
        """Mutate *args* with thinking config if present; return whether thinking is enabled."""
        thinking_config = self.llm_config.model_parameters.get("thinking_config")
        if not isinstance(thinking_config, dict):
            return False
        budget = thinking_config.get("thinking_budget")
        if budget is None:
            return False
        if adaptive_thinking_model:
            args["thinking"] = {"type": "adaptive"}
        else:
            args["thinking"] = {"type": "enabled", "budget_tokens": int(budget)}
        return True

    def _apply_model_params(
        self, args: dict, sampling_removed_model: bool, thinking_enabled: bool
    ) -> None:
        """Forward allowed model parameters into *args*, coercing types where needed."""
        for param, value in self.llm_config.model_parameters.items():
            if param not in _ALLOWED_MODEL_PARAMS:
                continue
            if sampling_removed_model and param in _SAMPLING_PARAMS:
                raise GenaiCommonException(
                    ErrorCodes.GR007,
                    f"Sampling parameter '{param}' is not supported by model {self.llm_config.name}. "
                    "Remove it from the model configuration.",
                )
            coerced = float(value) if param in _FLOAT_MODEL_PARAMS else value
            # Anthropic requires temperature=1 when extended thinking is enabled
            if param == "temperature" and thinking_enabled:
                coerced = 1.0
            args[param] = coerced

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
