"""
Unit tests for ClaudeGenerator's pure logic: MIME routing / file conversion,
request assembly, model-capability gating, and response unwrapping.

The production module imports the `query` framework, the `anthropic` SDK and
`google` auth — none of which are needed to exercise the pure functions.
Lightweight stubs are injected into sys.modules before the module is loaded
from its file path, so the suite runs anywhere with a bare Python install.

Run from this directory:
    python3 -m unittest test_claude_generator -v
"""

import base64
import importlib.util
import pathlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock


# ---------------------------------------------------------------------------
# Stub external dependencies so claude_generator.py imports cleanly
# ---------------------------------------------------------------------------

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ODT = "application/vnd.oasis.opendocument.text"


def _module(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


class _ErrorCode:
    def __init__(self, name):
        self._name = name

    def get_description(self):
        return f"{self._name} description"

    def __repr__(self):
        return f"<ErrorCode {self._name}>"


class _GenaiCommonException(Exception):
    def __init__(self, code, description, cause=None):
        super().__init__(description)
        self.code, self.description, self.cause = code, description, cause


def _install_stub_modules():
    # --- httpx ---------------------------------------------------------
    class _Timeout:
        def __init__(self, timeout=None, connect=None):
            self.timeout, self.connect = timeout, connect

    class _ConnectError(Exception):
        pass

    _module(
        "httpx",
        Timeout=_Timeout,
        ConnectError=_ConnectError,
        AsyncClient=mock.MagicMock,
        Response=object,
    )

    # --- anthropic -------------------------------------------------------
    class _APIConnectionError(Exception):
        pass

    class _APITimeoutError(_APIConnectionError):  # mirrors the real SDK hierarchy
        pass

    class _APIStatusError(Exception):
        pass

    _module(
        "anthropic",
        AsyncAnthropicVertex=mock.MagicMock,
        APIConnectionError=_APIConnectionError,
        APIStatusError=_APIStatusError,
        APITimeoutError=_APITimeoutError,
    )
    _module("anthropic.types", Message=object)

    # --- google auth -------------------------------------------------------
    _module("google")
    _module("google.oauth2")
    _module(
        "google.oauth2.credentials",
        Credentials=lambda token: SimpleNamespace(token=token),
    )

    # --- query framework -----------------------------------------------------
    class _ConfidenceScoreResponse:
        def __init__(self, confidence_score, token_wise_confidence_scores):
            self.confidence_score = confidence_score
            self.token_wise_confidence_scores = token_wise_confidence_scores

    class _ModelRetryConfig:
        pass

    _module("query")
    _module("query.config")
    _module("query.config.environment", ClaudeEnvironment=object)
    _module("query.core")
    _module("query.core.generator")
    _module("query.core.generator.generator", Generator=object)
    _module("query.models")
    _module(
        "query.models.confidence_score_response",
        ConfidenceScoreResponse=_ConfidenceScoreResponse,
    )
    _module(
        "query.models.generation_metadata",
        ModelConfig=object,
        ModelProvider=SimpleNamespace(CLAUDE="claude"),
        ModelRetryConfig=_ModelRetryConfig,
    )
    _module("query.models.llm_usage_metrics", LLMUsageMetrics=mock.MagicMock())
    _module(
        "query.models.observability",
        ObservabilityLogType=SimpleNamespace(
            OTHER=SimpleNamespace(value="other"),
            ERROR=SimpleNamespace(value="error"),
        ),
        ObservabilityLogger=mock.MagicMock(),
    )
    _module("query.models.part_holder", PartHolder=object)
    _module("query.util")
    # Document converters return recognizable sentinels so routing is assertable.
    _module(
        "query.util.document_utils",
        word_to_text=lambda b: f"WORD::{b.decode('utf-8')}",
        xlsx_to_text=lambda b: f"XLSX::{b.decode('utf-8')}",
        odt_to_text=lambda b: f"ODT::{b.decode('utf-8')}",
        tiff_to_png=lambda b: b"PNGBYTES:" + b,
    )
    _module(
        "query.util.error_codes",
        ErrorCodes=SimpleNamespace(**{
            code: _ErrorCode(code)
            for code in ("GR007", "GR008", "GR009", "GR010", "GR012", "ER010", "ER012")
        }),
    )
    _module("query.util.exception_handler", GenaiCommonException=_GenaiCommonException)
    _module("query.util.proxy_token_roller", ProxyTokenRoller=object)
    _module("query.util.retry_utils", retry_wrapper=lambda fn, cfg: fn)


def _load_module():
    _install_stub_modules()
    path = pathlib.Path(__file__).with_name("claude_generator.py")
    spec = importlib.util.spec_from_file_location("claude_generator_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cg = _load_module()
ErrorCodes = sys.modules["query.util.error_codes"].ErrorCodes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONTENT = [{"type": "text", "text": "hi"}]


def b64(raw: bytes | str) -> str:
    """Encode to the base64 string shape PartHolder.data carries."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def part(mime: str, raw: bytes | str = b"payload", filename: str = "f"):
    return SimpleNamespace(mime_type=mime, data=b64(raw), filename=filename)


def make_generator(
    model_name="claude-sonnet-5@20260101",
    model_parameters=None,
    extra_adaptive=(),
    extra_no_sampling=(),
):
    llm_config = SimpleNamespace(
        name=model_name,
        model_parameters=model_parameters if model_parameters is not None else {},
        project_id="proj-123",
        r2d2_coin="coin-1",
        default_prompt_id="prompt-1",
    )
    environment = SimpleNamespace(
        claude_project_id="env-proj",
        claude_region="us-east5",
        claude_api_base="https://r2d2.example",
        claude_extra_adaptive_thinking_prefixes=list(extra_adaptive),
        claude_extra_no_sampling_prefixes=list(extra_no_sampling),
    )
    token_roller = SimpleNamespace(get_token=lambda: "tok")
    return cg.ClaudeGenerator(environment, token_roller, llm_config, use_case="unit-test")


def build_args(generator, system_prompt="", max_tokens=None, response_schema=None):
    return generator._build_create_args(system_prompt, CONTENT, max_tokens, response_schema)


# ---------------------------------------------------------------------------
# _bare_model_name
# ---------------------------------------------------------------------------

class TestBareModelName(unittest.TestCase):
    def test_strips_vertex_snapshot_suffix(self):
        self.assertEqual(cg._bare_model_name("claude-opus-4-5@20251101"), "claude-opus-4-5")

    def test_passthrough_without_suffix(self):
        self.assertEqual(cg._bare_model_name("claude-sonnet-5"), "claude-sonnet-5")


# ---------------------------------------------------------------------------
# resolve_error_code
# ---------------------------------------------------------------------------

class TestResolveErrorCode(unittest.TestCase):
    def test_429_is_rate_limit(self):
        self.assertIs(cg.resolve_error_code(429), ErrorCodes.GR008)

    def test_400_is_bad_request(self):
        self.assertIs(cg.resolve_error_code(400), ErrorCodes.GR007)

    def test_other_4xx_is_client_error(self):
        for status in (401, 403, 404, 422):
            with self.subTest(status=status):
                self.assertIs(cg.resolve_error_code(status), ErrorCodes.GR010)

    def test_5xx_is_server_error(self):
        for status in (500, 503, 529):
            with self.subTest(status=status):
                self.assertIs(cg.resolve_error_code(status), ErrorCodes.GR009)


# ---------------------------------------------------------------------------
# _build_content_block — the five-way MIME router
# ---------------------------------------------------------------------------

class TestBuildContentBlockImages(unittest.TestCase):
    def test_native_image_passes_base64_through_untouched(self):
        p = part("image/png", b"rawpng")
        block = cg._build_content_block(p)
        self.assertEqual(block["type"], "image")
        self.assertEqual(block["source"]["type"], "base64")
        self.assertEqual(block["source"]["media_type"], "image/png")
        self.assertEqual(block["source"]["data"], p.data)  # not re-encoded

    def test_all_four_native_image_types_route_to_image(self):
        for mime in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            with self.subTest(mime=mime):
                self.assertEqual(cg._build_content_block(part(mime))["type"], "image")

    def test_tiff_is_converted_to_png_and_re_encoded(self):
        block = cg._build_content_block(part("image/tiff", b"tiffdata"))
        self.assertEqual(block["type"], "image")
        self.assertEqual(block["source"]["media_type"], "image/png")
        self.assertEqual(base64.b64decode(block["source"]["data"]), b"PNGBYTES:tiffdata")


class TestBuildContentBlockText(unittest.TestCase):
    def test_text_is_decoded_and_sent_as_plain_text_document(self):
        block = cg._build_content_block(part("text/csv", "a,b\n1,2"))
        self.assertEqual(block["type"], "document")
        self.assertEqual(block["source"]["type"], "text")
        self.assertEqual(block["source"]["media_type"], cg.TEXT_PLAIN)
        self.assertEqual(block["source"]["data"], "a,b\n1,2")  # decoded, not base64

    def test_every_text_mime_routes_to_text_document(self):
        for mime in cg._CLAUDE_TEXT_MIME_TYPES:
            with self.subTest(mime=mime):
                block = cg._build_content_block(part(mime, "hello"))
                self.assertEqual(block["source"]["media_type"], cg.TEXT_PLAIN)

    def test_non_utf8_text_raises_unicodedecodeerror(self):
        """Documents current behavior: latin-1 bytes crash rather than being skipped."""
        with self.assertRaises(UnicodeDecodeError):
            cg._build_content_block(part("text/csv", b"caf\xe9"))


class TestBuildContentBlockDocuments(unittest.TestCase):
    def test_pdf_passes_base64_through_as_document(self):
        p = part("application/pdf", b"%PDF-1.7")
        block = cg._build_content_block(p)
        self.assertEqual(block["type"], "document")
        self.assertEqual(block["source"]["type"], "base64")
        self.assertEqual(block["source"]["media_type"], "application/pdf")
        self.assertEqual(block["source"]["data"], p.data)

    def test_pdf_is_the_only_native_document_type(self):
        self.assertEqual(cg._CLAUDE_DOCUMENT_MIME_TYPES, frozenset({"application/pdf"}))

    def test_docx_is_converted_to_text(self):
        block = cg._build_content_block(part(DOCX, "docbody"))
        self.assertEqual(block["type"], "document")
        self.assertEqual(block["source"]["type"], "text")
        self.assertEqual(block["source"]["data"], "WORD::docbody")

    def test_xlsx_is_converted_to_text(self):
        block = cg._build_content_block(part(XLSX, "sheet"))
        self.assertEqual(block["source"]["data"], "XLSX::sheet")

    def test_odt_is_converted_to_text(self):
        block = cg._build_content_block(part(ODT, "odtbody"))
        self.assertEqual(block["source"]["data"], "ODT::odtbody")


class TestBuildContentBlockUnsupported(unittest.TestCase):
    def test_unsupported_mime_returns_none(self):
        for mime in ("video/mp4", "application/zip", "image/bmp", "application/octet-stream"):
            with self.subTest(mime=mime):
                self.assertIsNone(cg._build_content_block(part(mime)))


# ---------------------------------------------------------------------------
# _build_message_content
# ---------------------------------------------------------------------------

class TestBuildMessageContent(unittest.TestCase):
    def test_parts_precede_prompt_text(self):
        gen = make_generator()
        content = gen._build_message_content(
            [part("image/png"), part("application/pdf")], "the question"
        )
        self.assertEqual([b["type"] for b in content], ["image", "document", "text"])
        self.assertEqual(content[-1], {"type": "text", "text": "the question"})

    def test_unsupported_parts_are_skipped_not_fatal(self):
        gen = make_generator()
        content = gen._build_message_content(
            [part("video/mp4"), part("image/png")], "q"
        )
        self.assertEqual([b["type"] for b in content], ["image", "text"])

    def test_text_only_still_appends_prompt(self):
        gen = make_generator()
        self.assertEqual(gen._build_message_content([], "q"), [{"type": "text", "text": "q"}])


# ---------------------------------------------------------------------------
# max_tokens resolution
# ---------------------------------------------------------------------------

class TestMaxTokensResolution(unittest.TestCase):
    def test_explicit_override_wins(self):
        gen = make_generator(model_parameters={"max_tokens": 1000})
        self.assertEqual(build_args(gen, max_tokens=42)["max_tokens"], 42)

    def test_config_max_tokens(self):
        gen = make_generator(model_parameters={"max_tokens": 1000, "max_output_tokens": 2000})
        self.assertEqual(build_args(gen)["max_tokens"], 1000)

    def test_config_max_output_tokens_vertex_spelling(self):
        gen = make_generator(model_parameters={"max_output_tokens": 2000})
        self.assertEqual(build_args(gen)["max_tokens"], 2000)

    def test_default_is_64000(self):
        self.assertEqual(build_args(make_generator())["max_tokens"], 64000)


# ---------------------------------------------------------------------------
# response_schema — native vs prompt-injected
# ---------------------------------------------------------------------------

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}}


class TestResponseSchema(unittest.TestCase):
    def test_native_mode_uses_output_config(self):
        gen = make_generator(model_parameters={"native_json_schema": True})
        args = build_args(gen, system_prompt="sys", response_schema=SCHEMA)
        self.assertEqual(
            args["output_config"],
            {"format": {"type": "json_schema", "schema": SCHEMA}},
        )
        self.assertEqual(args["system"], "sys")  # system prompt left clean

    def test_fallback_mode_injects_into_system_prompt(self):
        args = build_args(make_generator(), system_prompt="sys", response_schema=SCHEMA)
        self.assertNotIn("output_config", args)
        self.assertTrue(args["system"].startswith("sys\n\n"))
        self.assertIn("valid JSON only", args["system"])
        self.assertIn('"properties"', args["system"])
        self.assertIn("markdown code fences", args["system"])

    def test_fallback_mode_with_empty_system_prompt(self):
        args = build_args(make_generator(), system_prompt="", response_schema=SCHEMA)
        self.assertTrue(args["system"].startswith("You must respond with valid JSON"))

    def test_no_schema_leaves_both_out(self):
        args = build_args(make_generator())
        self.assertNotIn("output_config", args)
        self.assertNotIn("system", args)


# ---------------------------------------------------------------------------
# _apply_thinking_config
# ---------------------------------------------------------------------------

class TestThinking(unittest.TestCase):
    def test_legacy_model_gets_manual_budget(self):
        gen = make_generator(
            model_name="claude-sonnet-4-5@20250929",
            model_parameters={"thinking_config": {"thinking_budget": "1024"}},
        )
        self.assertEqual(build_args(gen)["thinking"], {"type": "enabled", "budget_tokens": 1024})

    def test_modern_model_gets_adaptive_and_ignores_budget_value(self):
        gen = make_generator(
            model_name="claude-sonnet-5@20260101",
            model_parameters={"thinking_config": {"thinking_budget": 1024}},
        )
        self.assertEqual(build_args(gen)["thinking"], {"type": "adaptive"})

    def test_unknown_model_falls_back_to_manual_budget(self):
        """Unlisted models take the legacy path — this is why the env override exists."""
        gen = make_generator(
            model_name="claude-opus-5@20270101",
            model_parameters={"thinking_config": {"thinking_budget": 2048}},
        )
        self.assertEqual(build_args(gen)["thinking"], {"type": "enabled", "budget_tokens": 2048})

    def test_env_extra_prefix_promotes_unknown_model_to_adaptive(self):
        gen = make_generator(
            model_name="claude-opus-5@20270101",
            model_parameters={"thinking_config": {"thinking_budget": 2048}},
            extra_adaptive=["claude-opus-5"],
        )
        self.assertEqual(build_args(gen)["thinking"], {"type": "adaptive"})

    def test_malformed_thinking_config_means_thinking_off(self):
        gen = make_generator(model_parameters={"thinking_config": "yes please"})
        self.assertNotIn("thinking", build_args(gen))

    def test_missing_budget_means_thinking_off(self):
        gen = make_generator(model_parameters={"thinking_config": {}})
        self.assertNotIn("thinking", build_args(gen))


# ---------------------------------------------------------------------------
# _apply_model_params
# ---------------------------------------------------------------------------

class TestModelParams(unittest.TestCase):
    def test_sampling_param_on_modern_model_raises_gr007(self):
        gen = make_generator(
            model_name="claude-sonnet-5@20260101",
            model_parameters={"temperature": 0.2},
        )
        with self.assertRaises(_GenaiCommonException) as ctx:
            build_args(gen)
        self.assertIs(ctx.exception.code, ErrorCodes.GR007)
        self.assertIn("temperature", ctx.exception.description)

    def test_env_extra_prefix_makes_unknown_model_reject_sampling(self):
        gen = make_generator(
            model_name="claude-opus-5@20270101",
            model_parameters={"top_k": 40},
            extra_no_sampling=["claude-opus-5"],
        )
        with self.assertRaises(_GenaiCommonException):
            build_args(gen)

    def test_non_sampling_params_still_forwarded_on_modern_model(self):
        gen = make_generator(
            model_name="claude-sonnet-5@20260101",
            model_parameters={"stop_sequences": ["END"]},
        )
        self.assertEqual(build_args(gen)["stop_sequences"], ["END"])

    def test_legacy_model_keeps_sampling_with_float_coercion(self):
        gen = make_generator(
            model_name="claude-sonnet-4-5@20250929",
            model_parameters={"temperature": "0.2", "top_k": 40},
        )
        args = build_args(gen)
        self.assertEqual(args["temperature"], 0.2)
        self.assertIsInstance(args["temperature"], float)
        self.assertEqual(args["top_k"], 40)

    def test_temperature_forced_to_1_when_thinking_enabled(self):
        gen = make_generator(
            model_name="claude-sonnet-4-5@20250929",
            model_parameters={
                "temperature": 0.2,
                "thinking_config": {"thinking_budget": 1024},
            },
        )
        self.assertEqual(build_args(gen)["temperature"], 1.0)

    def test_non_allowlisted_params_never_forwarded(self):
        gen = make_generator(
            model_parameters={
                "native_json_schema": True,
                "thinking_config": {"thinking_budget": 1},
                "max_tokens": 500,
                "response_mime_type": "application/json",  # Gemini-only key
                "temprature": 0.5,  # typo — must be ignored, not crash
            },
        )
        args = build_args(gen)
        for key in ("native_json_schema", "thinking_config", "response_mime_type", "temprature"):
            self.assertNotIn(key, args)


# ---------------------------------------------------------------------------
# unwrap_llm_response
# ---------------------------------------------------------------------------

class TestUnwrapLlmResponse(unittest.TestCase):
    def test_returns_first_text_block_with_zero_confidence(self):
        response = SimpleNamespace(content=[
            SimpleNamespace(type="thinking", thinking="..."),
            SimpleNamespace(type="text", text="answer"),
            SimpleNamespace(type="text", text="ignored"),
        ])
        text, confidence = cg.ClaudeGenerator.unwrap_llm_response(response)
        self.assertEqual(text, "answer")
        self.assertEqual(confidence.confidence_score, 0)
        self.assertEqual(confidence.token_wise_confidence_scores, [])

    def test_empty_content_raises(self):
        with self.assertRaises(ValueError):
            cg.ClaudeGenerator.unwrap_llm_response(SimpleNamespace(content=[]))

    def test_no_text_block_raises(self):
        response = SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking="...")])
        with self.assertRaises(ValueError):
            cg.ClaudeGenerator.unwrap_llm_response(response)


if __name__ == "__main__":
    unittest.main()
