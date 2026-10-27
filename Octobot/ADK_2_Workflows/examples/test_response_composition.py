"""Focused helper tests; these do not claim native ADK or transport coverage."""

from dataclasses import asdict, replace
import json
import unittest

from response_composition import (
    ExecutionScope,
    InMemoryOriginalOutputStore,
    OriginalOutputRef,
    compose_manifest,
    finalize_response,
)


class ResponseCompositionTests(unittest.TestCase):
    def setUp(self):
        self.scope = ExecutionScope("tenant-a", "report-usecase", "run-1")
        self.store = InMemoryOriginalOutputStore()
        self.original = b"ID | Value\r\nR1 | 001.20\r\nR2 | 085.50  \r\n"
        self.ref = self.store.put(self.scope, self.original, "text/plain; charset=utf-8")

    def test_original_block_is_unchanged_after_narrative(self):
        explanation = "Here are your results."
        result = finalize_response(self.scope, self.store, compose_manifest(explanation, self.ref))
        prefix = explanation.encode() + b"\n\n"
        self.assertEqual(result[:len(prefix)], prefix)
        self.assertEqual(result[len(prefix):], self.original)

    def test_non_ascii_bytes_and_whitespace_are_preserved(self):
        original = "Name,Value\r\nCaf\u00e9,  001.20 \r\n".encode("utf-8")
        ref = self.store.put(self.scope, original, "text/csv; charset=utf-8")
        result = finalize_response(self.scope, self.store, compose_manifest("Results", ref))
        self.assertEqual(result[len(b"Results\n\n"):], original)

    def test_manifest_contains_reference_instead_of_original_data(self):
        encoded = json.dumps(asdict(compose_manifest("Results", self.ref)))
        self.assertIn(self.ref.key, encoded)
        self.assertNotIn("001.20", encoded)
        self.assertNotIn("085.50", encoded)

    def test_other_tenant_cannot_resolve_original_output(self):
        other = replace(self.scope, tenant_id="tenant-b")
        with self.assertRaises(LookupError):
            finalize_response(other, self.store, compose_manifest("Results", self.ref))

    def test_other_run_cannot_resolve_original_output(self):
        other = replace(self.scope, workflow_run_id="run-2")
        with self.assertRaises(LookupError):
            finalize_response(other, self.store, compose_manifest("Results", self.ref))

    def test_changed_checksum_is_rejected(self):
        bad_ref = replace(self.ref, sha256="0" * 64)
        with self.assertRaises(ValueError):
            finalize_response(self.scope, self.store, compose_manifest("Results", bad_ref))

    def test_changed_stored_bytes_are_rejected(self):
        class CorruptStore:
            def get(self, scope, ref):
                return b"altered output"

        with self.assertRaises(ValueError):
            finalize_response(self.scope, CorruptStore(), compose_manifest("Results", self.ref))

    def test_missing_reference_is_not_substituted_with_model_text(self):
        missing = OriginalOutputRef("missing", self.ref.sha256, self.ref.content_type)
        with self.assertRaises(LookupError):
            finalize_response(self.scope, self.store, compose_manifest("Results", missing))

    def test_oversized_original_output_is_rejected_before_storage(self):
        with self.assertRaises(ValueError):
            InMemoryOriginalOutputStore(max_bytes=1).put(self.scope, b"ab", "text/plain")


if __name__ == "__main__":
    unittest.main()
