#!/usr/bin/env python3
"""Read-only R13 witness verification. Never issues runtime authorizations."""
from __future__ import annotations
import json
from pathlib import Path
import sys
from r13_witness import verify_witness


def bounded(path: str, limit: int):
    item=Path(path)
    if not item.is_file() or item.stat().st_size>limit:
        raise ValueError("Missing or oversized local JSON file.")
    return json.loads(item.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    if len(argv)!=6:
        print("Usage: python3 scripts/r13_check.py <R12-ledger.json> "
              "<pinned-operator-trust.json> <pinned-witness-trust.json> "
              "<witness-receipt.json> <receiver-protected-minimum-event-count>",
              file=sys.stderr)
        return 2
    try:
        _,ledger,operators,witnesses,receipt,count=argv
        if not count.isdecimal():
            raise ValueError("Minimum event count must be nonnegative integer.")
        floor=int(count)
        if floor>128:
            raise ValueError("Minimum count exceeds frozen R12 bound.")
        report=verify_witness(bounded(ledger,192000),bounded(operators,16000),
                              bounded(receipt,3000),bounded(witnesses,14000),floor)
        print(json.dumps(report,indent=2))
        return 0 if report["witnessValid"] else 1
    except (OSError,ValueError,TypeError,KeyError) as error:
        print("R13 rejected: "+str(error),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main(sys.argv))
