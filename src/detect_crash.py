#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Pattern, Tuple

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

PATTERNS_RAW: List[Tuple[str, str]] = [
    ("kernel_panic", r"Kernel panic - not syncing"),
    ("oops", r"\bOops\b"),
    ("kasan", r"\bKASAN:\b"),
    ("ubsan", r"\bUBSAN:\b"),
    ("kmsan", r"\bKMSAN:\b"),
    ("kfence", r"\bKFENCE:\b"),
    ("bug", r"(^|\])\s*BUG:\s"),
    ("warning", r"(^|\])\s*WARNING:\s"),
    ("general_protection", r"general protection fault"),
    ("soft_lockup", r"BUG: soft lockup"),
    ("hard_lockup", r"BUG: hard lockup"),
    ("hung_task", r"INFO: task .* blocked for more than"),
    ("rcu_stall", r"rcu: INFO: rcu_(preempt|sched) detected stalls|RCU Stall|rcu_sched detected stalls"),
    ("lockdep", r"possible circular locking dependency detected"),
    ("call_trace", r"Call Trace:"),
    ("panic_on_warn", r"panic_on_warn"),

    ("oom_killer", r"invoked oom-killer|oom-kill:constraint="),
    ("out_of_memory", r"Out of memory: Killed process"),
    ("oom_reaper", r"oom_reaper: reaped process"),
]

PATTERNS: List[Tuple[str, Pattern[str]]] = [
    (name, re.compile(pat, flags=re.MULTILINE))
    for name, pat in PATTERNS_RAW
]

CRASH_KEYS = {
    "kernel_panic",
    "oops",
    "kasan",
    "ubsan",
    "kmsan",
    "kfence",
    "general_protection",
    "oom_killer",
    "out_of_memory",
    "lockdep",
}

WARNING_KEYS = {
    "bug",
    "warning",
    "soft_lockup",
    "hard_lockup",
    "hung_task",
    "rcu_stall",
    "call_trace",
    "panic_on_warn",
    "oom_reaper",
}


def read_text(p: Path) -> str:
    return p.read_text(errors="ignore")


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def find_hits(text: str) -> List[str]:
    clean = strip_ansi(text)
    hits: List[str] = []

    for name, cre in PATTERNS:
        if cre.search(clean):
            hits.append(name)

    return hits


def classify(hits: List[str]) -> str:
    if not hits:
        return "clean"

    if any(h in CRASH_KEYS for h in hits):
        return "crash"

    if any(h in WARNING_KEYS for h in hits):
        return "warning"

    return "warning"


def analyze_file(path: Path) -> Dict:
    text = read_text(path)
    hits = find_hits(text)
    verdict = classify(hits)

    return {
        "file": str(path),
        "verdict": verdict,
        "hits": hits,
        "hit_count": len(hits),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+", help="log file paths")
    ap.add_argument("--json", action="store_true", help="output JSON")
    ap.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="return non-zero for warning as well as crash",
    )
    ap.add_argument(
        "--show-hits",
        action="store_true",
        help="print matched hit names in text mode",
    )
    args = ap.parse_args()

    results = [analyze_file(Path(p)) for p in args.logs]

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            line = f"{r['file']} -> {r['verdict']}"
            if args.show_hits:
                line += f" | hits={','.join(r['hits']) if r['hits'] else '-'}"
            print(line)

    if args.fail_on_warning:
        exit_code = 1 if any(r["verdict"] in {"crash", "warning"} for r in results) else 0
    else:
        exit_code = 1 if any(r["verdict"] == "crash" for r in results) else 0

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()