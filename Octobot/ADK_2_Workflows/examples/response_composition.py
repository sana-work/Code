"""Exact response assembly without a model or a domain-specific storage system.

The memory store is a fixture implementation. A real multi-worker deployment
must inject durable, owner-scoped storage with immutable references.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class ExecutionScope:
    tenant_id: str
    usecase_id: str
    workflow_run_id: str


@dataclass(frozen=True)
class OriginalOutputRef:
    key: str
    sha256: str
    content_type: str


@dataclass(frozen=True)
class ResponseManifest:
    explanation: str
    original_output: OriginalOutputRef
    finalizer: str = "append_original"
    requires_final_delivery: bool = True


class OriginalOutputStore(Protocol):
    def put(
        self, scope: ExecutionScope, body: bytes, content_type: str
    ) -> OriginalOutputRef: ...

    def get(self, scope: ExecutionScope, ref: OriginalOutputRef) -> bytes: ...


class InMemoryOriginalOutputStore:
    """Run/owner-scoped test adapter, not durable storage."""

    def __init__(self, max_bytes: int = 512_000) -> None:
        self.max_bytes = max_bytes
        self._items: dict[tuple[ExecutionScope, str], tuple[bytes, str]] = {}

    def put(
        self, scope: ExecutionScope, body: bytes, content_type: str
    ) -> OriginalOutputRef:
        if not isinstance(body, bytes):
            raise TypeError("Tool output must be supplied as original bytes")
        if len(body) > self.max_bytes:
            raise ValueError("Tool output exceeds configured size")
        key = "output_" + uuid4().hex
        self._items[(scope, key)] = (body, content_type)
        return OriginalOutputRef(key, sha256(body).hexdigest(), content_type)

    def get(self, scope: ExecutionScope, ref: OriginalOutputRef) -> bytes:
        try:
            body, content_type = self._items[(scope, ref.key)]
        except KeyError:
            raise LookupError("Original output unavailable") from None
        if content_type != ref.content_type:
            raise LookupError("Original output unavailable")
        return body


def compose_manifest(
    explanation: str, original_output: OriginalOutputRef
) -> ResponseManifest:
    """The node after the agent produces a small, explicit response contract."""
    return ResponseManifest(explanation=explanation, original_output=original_output)


def finalize_response(
    scope: ExecutionScope, store: OriginalOutputStore, manifest: ResponseManifest
) -> bytes:
    """Run only at the last trusted delivery boundary, after model processing."""
    if manifest.finalizer != "append_original" or not manifest.requires_final_delivery:
        raise ValueError("Unsupported final response policy")
    original = store.get(scope, manifest.original_output)
    if sha256(original).hexdigest() != manifest.original_output.sha256:
        raise ValueError("Original output integrity check failed")
    return manifest.explanation.encode("utf-8") + b"\n\n" + original
