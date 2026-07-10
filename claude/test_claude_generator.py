"""
Unit tests for ClaudeGenerator's pure request-assembly logic.

The production module imports the `query` framework, the `anthropic` SDK and
`google` auth — none of which are needed to exercise `_build_create_args`,
`_bare_model_name`, `_build_content_block` or `unwrap_llm_response`.
Lightweight stubs are injected into sys.modules before the module is loaded
from its file path, so the tests run anywhere with a bare Python install.

Run from this directory:
    python3 -m unittest test_claude_generator -v
"""

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

def _module(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


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

    class _ErrorCode:
        def __init__(self, name):
            self._name = name

        def get_description(self):
            return self._name

    class _GenaiCommonException(Exception):
        def __init__(self, code, description, cause=None):
            super().__init__(description)
            self.code, self.description, self.cause = code, description, cause

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
        ObservabilityLogType=SimpleNamespace(OTHER=SimpleNamespace(value="other")),
        ObservabilityLogger=mock.MagicMock(),
    )
    _module("query.models.part_holder", PartHolder=object)
    _module("query.util")
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONTENT = [{"type": "text", "text": "hi"}]


def make_generator(model_name="claude-sonnet-5@20260101", model_parameters=None):
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
        gen = make_generator()
        self.assertEqual(build_args(gen)["max_tokens"], 64000)


# ---------------------------------------------------------------------------
# response_schema modes
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
        # system prompt must NOT be polluted with the schema in native mode
        self.assertEqual(args["system"], "sys")

    def test_fallback_mode_injects_into_system_prompt(self):
        gen = make_generator()
        args = build_args(gen, system_prompt="sys", response_schema=SCHEMA)
        self.assertNotIn("output_config", args)
        self.assertTrue(args["system"].startswith("sys\n\n"))
        self.assertIn("valid JSON only", args["system"])
        self.assertIn('"properties"', args["system"])
        self.assertIn("markdown code fences", args["system"])

    def test_fallback_mode_with_empty_system_prompt(self):
        gen = make_generator()
        args = build_args(gen, system_prompt="", response_schema=SCHEMA)
        self.assertTrue(args["system"].startswith("You must respond with valid JSON"))

    def test_no_schema_no_output_config_no_system(self):
        gen = make_generator()
        args = build_args(gen)
        self.assertNotIn("output_config", args)
        self.assertNotIn("system", args)


# ---------------------------------------------------------------------------
# Extended thinking translation
# ---------------------------------------------------------------------------

class TestThinking(unittest.TestCase):
    def test_legacy_model_gets_manual_budget(self):
        gen = make_generator(
            model_name="claude-sonnet-4-5@20250929",
            model_parameters={"thinking_config": {"thinking_budget": "1024"}},
        )
        args = build_args(gen)
        self.assertEqual(args["thinking"], {"type": "enabled", "budget_tokens": 1024})

    def test_modern_model_gets_adaptive(self):
        gen = make_generator(
            model_name="claude-sonnet-5@20260101",
            model_parameters={"thinking_config": {"thinking_budget": 1024}},
        )
        self.assertEqual(build_args(gen)["thinking"], {"type": "adaptive"})

    def test_unknown_future_model_defaults_to_adaptive(self):
        gen = make_generator(
            model_name="claude-opus-5@20270101",
            model_parameters={"thinking_config": {"thinking_budget": 1024}},
        )
        self.assertEqual(build_args(gen)["thinking"], {"type": "adaptive"})

    def test_malformed_thinking_config_means_thinking_off(self):
        gen = make_generator(model_parameters={"thinking_config": "yes please"})
        self.assertNotIn("thinking", build_args(gen))

    def test_missing_budget_means_thinking_off(self):
        gen = make_generator(model_parameters={"thinking_config": {}})
        self.assertNotIn("thinking", build_args(gen))


# ---------------------------------------------------------------------------
# Param forwarding: allowlist, sampling removal, coercion, temperature rule
# ---------------------------------------------------------------------------

class TestParamForwarding(unittest.TestCase):
    def test_modern_model_drops_sampling_but_keeps_others(self):
        gen = make_generator(
            model_name="claude-sonnet-5@20260101",
            model_parameters={
                "temperature": 0.2,
                "top_p": 0.9,
                "top_k": 40,
                "stop_sequences": ["END"],
            },
        )
        args = build_args(gen)
        for dropped in ("temperature", "top_p", "top_k"):
            self.assertNotIn(dropped, args)
        self.assertEqual(args["stop_sequences"], ["END"])

    def test_unknown_future_model_drops_sampling(self):
        gen = make_generator(
            model_name="claude-opus-5@20270101",
            model_parameters={"temperature": 0.2},
        )
        self.assertNotIn("temperature", build_args(gen))

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
# _build_content_block
# ---------------------------------------------------------------------------

class TestBuildContentBlock(unittest.TestCase):
    def _part(self, mime):
        return SimpleNamespace(mime_type=mime, data="b64data", filename="f")

    def test_image_mime_routes_to_image_block(self):
        block = cg._build_content_block(self._part("image/png"))
        self.assertEqual(block["type"], "image")
        self.assertEqual(block["source"]["media_type"], "image/png")

    def test_document_mime_routes_to_document_block(self):
        block = cg._build_content_block(self._part("application/pdf"))
        self.assertEqual(block["type"], "document")

    def test_unsupported_mime_returns_none(self):
        self.assertIsNone(cg._build_content_block(self._part("video/mp4")))


# ---------------------------------------------------------------------------
# unwrap_llm_response
# ---------------------------------------------------------------------------

class TestUnwrapLlmResponse(unittest.TestCase):
    def test_returns_first_text_block_with_zero_confidence(self):
        response = SimpleNamespace(content=[
            SimpleNamespace(type="thinking", thinking="..."),
            SimpleNamespace(type="text", text="answer"),
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
