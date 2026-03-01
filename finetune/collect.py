#!/usr/bin/env python3
"""BrainC v0.3 — Dataset Collection Tool

Reads conversation history from the SQLite database, filters low-quality
exchanges, and exports training datasets in Alpaca and ShareGPT formats.

Usage:
    python finetune/collect.py
    python finetune/collect.py --min-words 30 --output-dir finetune/datasets/
"""

import argparse
import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "memory" / "conversations.db"


# ── Database loading ────────────────────────────────────────────────────────


def load_conversations(db_path: Path) -> list[dict]:
    """Load all user/assistant messages from SQLite, grouped by conversation_id."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, role, message, conversation_id, timestamp
        FROM   messages
        WHERE  role IN ('user', 'assistant')
        ORDER  BY conversation_id, timestamp ASC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    # Group by conversation_id while preserving insertion order
    convs: dict[str, list[dict]] = {}
    for row in rows:
        cid = row["conversation_id"]
        convs.setdefault(cid, []).append(row)

    return [{"conversation_id": cid, "messages": msgs} for cid, msgs in convs.items()]


# ── Quality filtering ───────────────────────────────────────────────────────

_ERROR_PATTERNS = re.compile(
    r"^\[(error|connection error)\]"
    r"|^error \d+"
    r"|^ollama returned"
    r"|^failed to reach"
    r"|^\[http error",
    re.IGNORECASE,
)


def _word_count(text: str) -> int:
    return len(text.split())


def _is_error(text: str) -> bool:
    return bool(_ERROR_PATTERNS.match(text.strip()))


def _is_quality_pair(user_msg: str, assistant_msg: str, min_words: int) -> bool:
    if _word_count(user_msg) < min_words:
        return False
    if _word_count(assistant_msg) < min_words:
        return False
    if _is_error(user_msg) or _is_error(assistant_msg):
        return False
    return True


# ── Pair extraction ─────────────────────────────────────────────────────────


def extract_pairs(
    conversations: list[dict], min_words: int
) -> tuple[list[dict], list[dict]]:
    """Extract (user, assistant) pairs and return (alpaca_records, sharegpt_records)."""
    alpaca: list[dict] = []
    sharegpt: list[dict] = []

    for conv in conversations:
        messages = conv["messages"]
        sgpt_turns: list[dict] = []
        i = 0

        while i < len(messages) - 1:
            cur_msg = messages[i]
            nxt_msg = messages[i + 1]

            if cur_msg["role"] == "user" and nxt_msg["role"] == "assistant":
                user_msg = cur_msg["message"].strip()
                asst_msg = nxt_msg["message"].strip()

                if _is_quality_pair(user_msg, asst_msg, min_words):
                    alpaca.append(
                        {"instruction": user_msg, "input": "", "output": asst_msg}
                    )
                    sgpt_turns.append({"from": "human", "value": user_msg})
                    sgpt_turns.append({"from": "gpt", "value": asst_msg})
                i += 2
            else:
                i += 1

        if sgpt_turns:
            sharegpt.append({"conversations": sgpt_turns})

    return alpaca, sharegpt


# ── Summary output ──────────────────────────────────────────────────────────


def _print_summary(conversations: list[dict], alpaca: list[dict]) -> None:
    total_pairs = len(alpaca)
    avg_len = (
        sum(_word_count(r["output"]) for r in alpaca) // total_pairs
        if total_pairs
        else 0
    )
    print("\n── Dataset Collection Summary ──────────────────────────────")
    print(f"  Total conversations scanned : {len(conversations)}")
    print(f"  Total pairs exported        : {total_pairs}")
    print(f"  Average response length     : {avg_len} words")
    print("────────────────────────────────────────────────────────────\n")


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export BrainC conversation history as fine-tuning datasets."
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=20,
        help="Minimum word count for both instruction and output (default: 20)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "datasets",
        help="Directory to write dataset files (default: finetune/datasets/)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help="Path to the SQLite conversations database",
    )
    args = parser.parse_args()

    if not args.db.exists():
        print(f"[error] Database not found: {args.db}")
        print("  Start BrainC and have at least one conversation first.")
        raise SystemExit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading conversations from {args.db} ...")
    conversations = load_conversations(args.db)
    print(f"Found {len(conversations)} conversation(s). Filtering with --min-words={args.min_words} ...")

    alpaca, sharegpt = extract_pairs(conversations, args.min_words)

    alpaca_path = args.output_dir / "alpaca_dataset.json"
    sharegpt_path = args.output_dir / "sharegpt_dataset.json"

    alpaca_path.write_text(json.dumps(alpaca, indent=2, ensure_ascii=False))
    sharegpt_path.write_text(json.dumps(sharegpt, indent=2, ensure_ascii=False))

    print(f"  Alpaca   → {alpaca_path}")
    print(f"  ShareGPT → {sharegpt_path}")

    _print_summary(conversations, alpaca)


if __name__ == "__main__":
    main()
