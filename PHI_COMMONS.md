# Phi Commons — BrainC

BrainC is part of the **Phi Commons**.

Unless a file or directory states otherwise, original BrainC software and documentation in this repository are released under the MIT License in `LICENSE`.

## Why BrainC is open

BrainC is an important ancestor of the modern PhiOS / PhiVessel architecture. It contains early local-first implementations of:

- Ollama-backed local inference;
- FastAPI streaming chat;
- SQLite conversation and semantic memory;
- local tools and workspace boundaries;
- MCP integration;
- local web search integration;
- model switching and runtime health;
- fine-tuning and evaluation utilities.

The Commons goal is to make those ideas inspectable, reusable, and remixable rather than trapping them in an abandoned private repository.

## What MIT covers

The MIT grant covers project-owned BrainC code and documentation.

It does not relicense:

- third-party Python packages;
- SearXNG;
- Ollama;
- Qwen or other model weights;
- datasets used for fine-tuning;
- external MCP servers;
- copied upstream code or assets carrying their own terms.

See `THIRD_PARTY_NOTICES.md` and `MODEL_LICENSES.md`.

## Capability is not authority

BrainC contains tools including code execution, file reading, web search, notes, calendar operations, and model/tool routing.

Open licensing does not make those capabilities safe or authorized in every environment.

Consumers integrating BrainC into PhiOS should place mutating or externally visible actions behind the PhiOS Action Gate and explicit grants rather than inheriting BrainC's historical execution model unchanged.

## Historical role

BrainC is a donor system, not a mandatory dependency of modern PhiOS.

Useful components may be adapted, rewritten, or absorbed into newer contracts without forcing the current platform to preserve every BrainC API or internal assumption.
