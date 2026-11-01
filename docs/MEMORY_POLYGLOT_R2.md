# Φ Memory Polyglot R2 | BrainC read-only consumer

**Experimental; synthetic-only; no network exposure or active integration.**

`api/core/polyglot_consumer.py` provides `parse_brainc_polyglot(raw_json)`, a strict parser for the **BrainC-addressed** consumer handoff contract `phi.memory.polyglot.consumer.r2`.

It returns a frozen `UnverifiedMemoryContext` record with text, summary, tags, entities, capsule ID, source SHA-256 change indicator, truncation flag and an explicit `unverified_external_context` status. No memory is written to BrainC's conversation database, inserted into prompts, used as instructions, or sent to tools. The existing BrainC authentication and chat APIs are not changed.

The parser rejects wrong audiences, unknown/additional keys, duplicate JSON keys, malformed/oversized input, non-ephemeral retention, claimed verification, oversized text (4096 characters), summary (512), tags and entities (8 entries of max 64 each), bad hashes and non-boolean truncation flags.

**Security:** A valid envelope is *not authenticated*. Source SHA-256 and text are merely claims carried by a JSON object. Before connecting real TMC memories, implement trusted transport authenticated on both ends, independent operator approval, response size limits, revocation propagation and client isolation. In particular, do not expose or trust a direct connection to TMC's currently unauthenticated HTTP routes.

Test: `python -m pytest -q tests/test_polyglot_consumer_r2.py`.

Reference: TMC `docs/MEMORY_POLYGLOT_R2_CONSUMER.md`.
