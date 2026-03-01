#!/usr/bin/env python3
"""BrainC v0.3 — A/B Testing Framework

Runs a set of test prompts against two Ollama models and prints a
side-by-side comparison with response-time metrics.

Usage:
    python finetune/ab_test.py
    python finetune/ab_test.py --model-a braincbrain --model-b braincbrain-ft
    python finetune/ab_test.py --prompts finetune/test_prompts.txt --timeout 180
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).parent
DEFAULT_PROMPTS = HERE / "test_prompts.txt"
RESULTS_DIR = HERE / "ab_results"
OLLAMA_URL = "http://localhost:11434"

_COL_WIDTH = 78
_HALF = (_COL_WIDTH - 3) // 2


# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="A/B test two Ollama models on a shared prompt set."
    )
    p.add_argument(
        "--model-a",
        default="braincbrain",
        help="First model (default: braincbrain)",
    )
    p.add_argument(
        "--model-b",
        default="braincbrain-ft",
        help="Second model (default: braincbrain-ft)",
    )
    p.add_argument(
        "--prompts",
        type=Path,
        default=DEFAULT_PROMPTS,
        help="Path to test prompts file — one prompt per line (default: finetune/test_prompts.txt)",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Seconds to wait per model response (default: 120)",
    )
    return p.parse_args()


# ── Prompt loading ───────────────────────────────────────────────────────────


def load_prompts(path: Path) -> list[str]:
    if not path.exists():
        print(f"[error] Prompts file not found: {path}")
        raise SystemExit(1)
    lines = [l.strip() for l in path.read_text().splitlines()]
    return [l for l in lines if l and not l.startswith("#")]


# ── Ollama query ─────────────────────────────────────────────────────────────


def query_model(model: str, prompt: str, timeout: int) -> tuple[str, float]:
    """Query a model and return (response_text, elapsed_seconds)."""
    t0 = time.monotonic()
    try:
        resp = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        text = resp.json().get("message", {}).get("content", "").strip()
        return text, time.monotonic() - t0
    except httpx.HTTPStatusError as e:
        return f"[HTTP {e.response.status_code}]", 0.0
    except Exception as e:
        return f"[error: {e}]", 0.0


# ── Display helpers ──────────────────────────────────────────────────────────


def _word_wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            if current:
                lines.append(current)
            current = word
        else:
            current = (current + " " + word).lstrip()
    if current:
        lines.append(current)
    return lines or [""]


def print_comparison(
    prompt: str,
    model_a: str,
    resp_a: str,
    model_b: str,
    resp_b: str,
) -> None:
    truncated = prompt[:_COL_WIDTH - 9]
    print(f"\n{'─' * _COL_WIDTH}")
    print(f"PROMPT: {truncated}")
    print(f"{'─' * _COL_WIDTH}")
    print(f"{'[' + model_a + ']':^{_HALF}} │ {'[' + model_b + ']':^{_HALF}}")
    print(f"{'─' * _HALF}─┼─{'─' * (_COL_WIDTH - _HALF - 3)}")

    lines_a = _word_wrap(resp_a, _HALF - 1)
    lines_b = _word_wrap(resp_b, _COL_WIDTH - _HALF - 3)
    for i in range(max(len(lines_a), len(lines_b))):
        la = lines_a[i] if i < len(lines_a) else ""
        lb = lines_b[i] if i < len(lines_b) else ""
        print(f"{la:<{_HALF - 1}} │ {lb}")


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()
    prompts = load_prompts(args.prompts)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print(
        f"\nBrainC A/B Test — {args.model_a}  vs  {args.model_b}\n"
        f"Prompts: {len(prompts)}  ·  Timeout: {args.timeout}s\n"
    )

    results = []
    metrics: dict[str, list] = {
        "lengths_a": [], "lengths_b": [],
        "tpt_a": [], "tpt_b": [],       # time-per-token (approx. time-per-word)
    }

    for idx, prompt in enumerate(prompts, 1):
        print(f"[{idx}/{len(prompts)}] {prompt[:70]} ...")

        resp_a, time_a = query_model(args.model_a, prompt, args.timeout)
        resp_b, time_b = query_model(args.model_b, prompt, args.timeout)

        wc_a = len(resp_a.split())
        wc_b = len(resp_b.split())
        tpt_a = time_a / max(wc_a, 1)
        tpt_b = time_b / max(wc_b, 1)

        metrics["lengths_a"].append(wc_a)
        metrics["lengths_b"].append(wc_b)
        metrics["tpt_a"].append(tpt_a)
        metrics["tpt_b"].append(tpt_b)

        print_comparison(prompt, args.model_a, resp_a, args.model_b, resp_b)
        print(
            f"\n  {args.model_a}: {wc_a} words, {time_a:.1f}s  "
            f"({tpt_a * 1000:.0f} ms/word)"
        )
        print(
            f"  {args.model_b}: {wc_b} words, {time_b:.1f}s  "
            f"({tpt_b * 1000:.0f} ms/word)"
        )

        results.append(
            {
                "prompt": prompt,
                args.model_a: {
                    "response": resp_a,
                    "elapsed_s": round(time_a, 2),
                    "word_count": wc_a,
                    "ms_per_word": round(tpt_a * 1000, 1),
                },
                args.model_b: {
                    "response": resp_b,
                    "elapsed_s": round(time_b, 2),
                    "word_count": wc_b,
                    "ms_per_word": round(tpt_b * 1000, 1),
                },
            }
        )

    # ── Summary table ──────────────────────────────────────────────────────────
    n = len(prompts)
    avg_len_a = sum(metrics["lengths_a"]) // n
    avg_len_b = sum(metrics["lengths_b"]) // n
    avg_tpt_a = sum(metrics["tpt_a"]) / n * 1000
    avg_tpt_b = sum(metrics["tpt_b"]) / n * 1000

    print(f"\n{'═' * _COL_WIDTH}")
    print("SUMMARY")
    print(f"{'═' * _COL_WIDTH}")
    print(f"  {'Metric':<32} {args.model_a:>20} {args.model_b:>20}")
    print(f"  {'─' * 72}")
    print(f"  {'Avg response length (words)':<32} {avg_len_a:>20} {avg_len_b:>20}")
    print(
        f"  {'Avg time per word (ms)':<32} {avg_tpt_a:>20.1f} {avg_tpt_b:>20.1f}"
    )

    # ── Persist results ────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"result_{ts}.json"
    out_path.write_text(
        json.dumps(
            {
                "timestamp": ts,
                "model_a": args.model_a,
                "model_b": args.model_b,
                "summary": {
                    args.model_a: {"avg_words": avg_len_a, "avg_ms_per_word": round(avg_tpt_a, 1)},
                    args.model_b: {"avg_words": avg_len_b, "avg_ms_per_word": round(avg_tpt_b, 1)},
                },
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"\n  Results saved → {out_path}")


if __name__ == "__main__":
    main()
