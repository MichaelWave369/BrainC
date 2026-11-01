"""Φ Memory Polyglot R2: strict BrainC read-only consumer contract.

This module parses *synthetic* envelopes only. JSON structure does not prove
TMC identity, operator approval, source authenticity, or truth. No API, DB,
prompt, model, tool, or network integration is enabled.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re

SCHEMA = "phi.memory.polyglot.consumer.r2"
EVIDENCE = "source_claim_not_independently_verified"
RETENTION = "ephemeral_preview_only"
_ROOT = {
    "schema", "reader", "capsule_id", "source_sha256",
    "evidence_status", "retention", "payload",
}
_PAYLOAD = {"kind", "text", "tags", "truncated", "summary", "entities"}


@dataclass(frozen=True, slots=True)
class UnverifiedMemoryContext:
    capsule_id: str
    source_sha256: str
    text: str
    summary: str
    tags: tuple[str, ...]
    entities: tuple[str, ...]
    truncated: bool
    status: str = "unverified_external_context"


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate memory field")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise ValueError("invalid JSON constant")


def _labels(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= 8
        and all(isinstance(x, str) and len(x) <= 64 for x in value)
    )


def parse_brainc_polyglot(raw: str) -> UnverifiedMemoryContext:
    """Read an ephemeral typed envelope, without trusting or persisting it."""
    if not isinstance(raw, str) or len(raw) > 32768:
        raise ValueError("invalid or oversized memory envelope")
    try:
        value = json.loads(raw, object_pairs_hook=_strict_object,
                           parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise ValueError("malformed memory envelope") from exc
    if not isinstance(value, dict) or set(value) != _ROOT:
        raise ValueError("invalid memory envelope fields")
    payload = value.get("payload")
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD:
        raise ValueError("invalid semantic payload")
    capsule_id = value["capsule_id"]
    digest = value["source_sha256"]
    if (
        value["schema"] != SCHEMA
        or value["reader"] != "brainc"
        or value["evidence_status"] != EVIDENCE
        or value["retention"] != RETENTION
        or not isinstance(capsule_id, str) or not 1 <= len(capsule_id) <= 128
        or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or payload["kind"] != "semantic_context"
        or not isinstance(payload["text"], str)
        or not payload["text"].strip()
        or len(payload["text"]) > 4096
        or not isinstance(payload["summary"], str)
        or len(payload["summary"]) > 512
        or not _labels(payload["tags"])
        or not _labels(payload["entities"])
        or type(payload["truncated"]) is not bool
    ):
        raise ValueError("invalid or misaddressed BrainC memory envelope")
    return UnverifiedMemoryContext(
        capsule_id=capsule_id,
        source_sha256=digest,
        text=payload["text"],
        summary=payload["summary"],
        tags=tuple(payload["tags"]),
        entities=tuple(payload["entities"]),
        truncated=payload["truncated"],
    )
