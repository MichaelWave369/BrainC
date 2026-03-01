#!/usr/bin/env python3
"""BrainC v0.3 — Dataset Quality Analyzer

Reports statistics on the exported Alpaca dataset and flags quality issues
before committing time to fine-tuning.

Usage:
    python finetune/analyze_dataset.py
    python finetune/analyze_dataset.py --dataset finetune/datasets/alpaca_dataset.json
    python finetune/analyze_dataset.py --short-threshold 40
"""

import argparse
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_DATASET = HERE / "datasets" / "alpaca_dataset.json"
MIN_RECOMMENDED_PAIRS = 500


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Analyze quality of a BrainC fine-tuning dataset."
    )
    p.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to Alpaca-format JSON dataset (default: finetune/datasets/alpaca_dataset.json)",
    )
    p.add_argument(
        "--short-threshold",
        type=int,
        default=30,
        help="Word count below which outputs are flagged as short (default: 30)",
    )
    return p.parse_args()


# ── Metrics helpers ──────────────────────────────────────────────────────────


def _wc(text: str) -> int:
    return len(text.split())


def _median(values: list[int]) -> float:
    s = sorted(values)
    n = len(s)
    return (s[n // 2] + s[(n - 1) // 2]) / 2 if n else 0.0


def ascii_histogram(values: list[int], bins: int = 10, bar_width: int = 38) -> str:
    """Render an ASCII histogram of integer values."""
    if not values:
        return "  (no data)"
    lo, hi = min(values), max(values)
    if lo == hi:
        return f"  All values: {lo}"
    step = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - lo) / step), bins - 1)
        counts[idx] += 1
    max_count = max(counts)
    rows = []
    for i, count in enumerate(counts):
        low = int(lo + i * step)
        high = int(lo + (i + 1) * step)
        bar_len = int(count / max_count * bar_width) if max_count else 0
        bar = "█" * bar_len
        rows.append(f"  {low:>5}–{high:<6} │{bar:<{bar_width}}│ {count}")
    return "\n".join(rows)


# ── Issue detection ──────────────────────────────────────────────────────────

_ERROR_KEYWORDS = ("[error", "[connection error", "[http", "failed to reach")


def flag_issues(
    records: list[dict], short_threshold: int
) -> tuple[list[str], list[dict]]:
    """Return (list_of_issue_messages, list_of_problematic_records)."""
    issues: list[str] = []
    flagged: list[dict] = []

    # Short outputs
    short = [r for r in records if _wc(r["output"]) < short_threshold]
    if short:
        issues.append(
            f"{len(short)} output(s) under {short_threshold} words"
            " — consider raising --min-words in collect.py"
        )
        flagged.extend(short[:3])  # show first 3

    # Duplicate instructions
    instr_counts = Counter(r["instruction"] for r in records)
    duplicates = {k: v for k, v in instr_counts.items() if v > 1}
    if duplicates:
        issues.append(
            f"{len(duplicates)} duplicate instruction(s) — "
            f"{sum(v - 1 for v in duplicates.values())} extra copies"
        )

    # Error-like instructions
    error_records = [
        r
        for r in records
        if any(kw in r["instruction"].lower() for kw in _ERROR_KEYWORDS)
    ]
    if error_records:
        issues.append(
            f"{len(error_records)} record(s) with error-like instructions "
            "(consider rerunning collect.py with stricter filters)"
        )
        flagged.extend(error_records[:2])

    return issues, flagged


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()

    if not args.dataset.exists():
        print(f"[error] Dataset not found: {args.dataset}")
        print("  Run: python finetune/collect.py")
        raise SystemExit(1)

    records: list[dict] = json.loads(args.dataset.read_text())
    total = len(records)

    print(f"\n── Dataset Analysis ────────────────────────────────────────────────")
    print(f"  File  : {args.dataset}")
    print(f"  Pairs : {total}")

    if total == 0:
        print("  [warning] Dataset is empty. Run: python finetune/collect.py")
        return

    if total < MIN_RECOMMENDED_PAIRS:
        print(
            f"  [warning] {total} pairs is below the recommended minimum of "
            f"{MIN_RECOMMENDED_PAIRS}.\n"
            "  Have more conversations with BrainC before fine-tuning."
        )

    instr_lens = [_wc(r["instruction"]) for r in records]
    out_lens = [_wc(r["output"]) for r in records]

    print()
    print(f"  {'Metric':<38} {'Instructions':>15} {'Outputs':>15}")
    print(f"  {'─' * 68}")
    print(f"  {'Average length (words)':<38} {sum(instr_lens) // total:>15} {sum(out_lens) // total:>15}")
    print(f"  {'Median length (words)':<38} {_median(instr_lens):>15.0f} {_median(out_lens):>15.0f}")
    print(f"  {'Min length (words)':<38} {min(instr_lens):>15} {min(out_lens):>15}")
    print(f"  {'Max length (words)':<38} {max(instr_lens):>15} {max(out_lens):>15}")

    # ── Quality flags ──────────────────────────────────────────────────────────
    issues, flagged = flag_issues(records, args.short_threshold)

    print()
    if issues:
        print("  ── Quality Flags ───────────────────────────────────────────────")
        for issue in issues:
            print(f"  ⚠  {issue}")
        if flagged:
            print("\n  Sample flagged records:")
            for r in flagged[:3]:
                print(f"    instruction: {r['instruction'][:80]!r}")
                print(f"    output     : {r['output'][:80]!r}\n")
    else:
        print("  No quality issues detected.")

    # ── Histograms ─────────────────────────────────────────────────────────────
    print("\n  ── Output length distribution (words) ──────────────────────────")
    print(ascii_histogram(out_lens))

    print("\n  ── Instruction length distribution (words) ─────────────────────")
    print(ascii_histogram(instr_lens))

    print()


if __name__ == "__main__":
    main()
