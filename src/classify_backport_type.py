#!/usr/bin/env python3
"""
Classify backport difficulty into Type I-IV by comparing upstream patch
(need_backport.patch) with the actual backported patch (patch.txt).

Type-I:   Identical — the upstream patch can be reused directly.
Type-II:  Location-only — same +/- lines, only hunk line numbers differ.
Type-III: Syntactic — identifier/symbol renaming or minor token-level edits.
Type-IV:  Structural — logical or structural adaptation required.

Usage:
    python classify_backport_type.py --dataset-dir /path/to/5.15.y
    python classify_backport_type.py --sample-dir /path/to/5.15.y/<tag>
    python classify_backport_type.py --upstream patch1.patch --backport patch2.txt
"""

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Patch parsing
# ---------------------------------------------------------------------------

@dataclass
class Hunk:
    file_a: str
    file_b: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    minus_lines: list  # lines starting with '-' (content only, stripped prefix)
    plus_lines: list   # lines starting with '+' (content only, stripped prefix)
    context_lines: list  # lines starting with ' '


def _strip_commit_header(text: str) -> str:
    """Remove commit/author/date header, keep only diff content."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("diff --git ") or line.startswith("--- a/"):
            return "\n".join(lines[i:])
    return text


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_patch(text: str) -> list[Hunk]:
    """Parse a unified diff into a list of Hunk objects."""
    text = _strip_commit_header(text)
    hunks = []
    current_file_a = ""
    current_file_b = ""
    current_hunk: Optional[Hunk] = None

    for line in text.splitlines():
        if line.startswith("diff --git "):
            # e.g. diff --git a/fs/foo.c b/fs/foo.c
            parts = line.split()
            if len(parts) >= 4:
                current_file_a = parts[2].removeprefix("a/")
                current_file_b = parts[3].removeprefix("b/")
            continue

        if line.startswith("--- a/"):
            current_file_a = line[6:].strip()
            continue
        if line.startswith("+++ b/"):
            current_file_b = line[6:].strip()
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            continue

        m = _HUNK_RE.match(line)
        if m:
            if current_hunk is not None:
                hunks.append(current_hunk)
            current_hunk = Hunk(
                file_a=current_file_a,
                file_b=current_file_b,
                old_start=int(m.group(1)),
                old_count=int(m.group(2) or 1),
                new_start=int(m.group(3)),
                new_count=int(m.group(4) or 1),
                minus_lines=[],
                plus_lines=[],
                context_lines=[],
            )
            continue

        if current_hunk is not None:
            if line.startswith("-"):
                current_hunk.minus_lines.append(line[1:])
            elif line.startswith("+"):
                current_hunk.plus_lines.append(line[1:])
            elif line.startswith(" "):
                current_hunk.context_lines.append(line[1:])

    if current_hunk is not None:
        hunks.append(current_hunk)

    return hunks


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------

def _normalize_whitespace(s: str) -> str:
    return " ".join(s.split())


def _extract_identifiers(line: str) -> set[str]:
    """Extract C identifiers from a line."""
    return set(re.findall(r"\b[A-Za-z_][A-Za-z_0-9]*\b", line))


def _lines_identical(lines_a: list[str], lines_b: list[str]) -> bool:
    """Check if two lists of lines are identical (ignoring trailing whitespace)."""
    if len(lines_a) != len(lines_b):
        return False
    return all(a.rstrip() == b.rstrip() for a, b in zip(lines_a, lines_b))


def _lines_whitespace_identical(lines_a: list[str], lines_b: list[str]) -> bool:
    """Check if lines are identical after normalizing whitespace."""
    if len(lines_a) != len(lines_b):
        return False
    return all(
        _normalize_whitespace(a) == _normalize_whitespace(b)
        for a, b in zip(lines_a, lines_b)
    )


def _is_syntactic_rename(lines_a: list[str], lines_b: list[str]) -> bool:
    """
    Check if two line lists differ only by identifier/symbol renaming.
    Returns True if a consistent token substitution maps lines_a to lines_b.
    """
    if len(lines_a) != len(lines_b):
        return False
    if not lines_a:
        return True

    rename_map: dict[str, str] = {}
    reverse_map: dict[str, str] = {}

    for la, lb in zip(lines_a, lines_b):
        toks_a = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|[^A-Za-z_\s]+|\s+", la)
        toks_b = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|[^A-Za-z_\s]+|\s+", lb)
        if len(toks_a) != len(toks_b):
            return False
        for ta, tb in zip(toks_a, toks_b):
            if ta == tb:
                continue
            # Both must be identifiers
            if not (re.match(r"^[A-Za-z_]", ta) and re.match(r"^[A-Za-z_]", tb)):
                return False
            # Check consistency
            if ta in rename_map:
                if rename_map[ta] != tb:
                    return False
            else:
                rename_map[ta] = tb
            if tb in reverse_map:
                if reverse_map[tb] != ta:
                    return False
            else:
                reverse_map[tb] = ta

    return True


def _lines_similarity(lines_a: list[str], lines_b: list[str]) -> float:
    """Compute line-level similarity ratio between two line lists."""
    text_a = "\n".join(l.rstrip() for l in lines_a)
    text_b = "\n".join(l.rstrip() for l in lines_b)
    return SequenceMatcher(None, text_a, text_b).ratio()


def classify_hunk_pair(upstream: Hunk, backport: Hunk) -> str:
    """Classify a single hunk pair."""
    u_minus = upstream.minus_lines
    u_plus = upstream.plus_lines
    b_minus = backport.minus_lines
    b_plus = backport.plus_lines

    # Type-I: identical change lines
    if _lines_identical(u_minus, b_minus) and _lines_identical(u_plus, b_plus):
        if (upstream.old_start == backport.old_start and
                upstream.new_start == backport.new_start):
            return "Type-I"
        else:
            return "Type-II"

    # Whitespace-only differences → still Type-II
    if (_lines_whitespace_identical(u_minus, b_minus) and
            _lines_whitespace_identical(u_plus, b_plus)):
        return "Type-II"

    # Type-III: consistent identifier renaming
    if (_is_syntactic_rename(u_minus, b_minus) and
            _is_syntactic_rename(u_plus, b_plus)):
        return "Type-III"

    return "Type-IV"


def _match_hunks(upstream_hunks: list[Hunk], backport_hunks: list[Hunk]):
    """
    Match upstream hunks to backport hunks.
    Returns list of (upstream_hunk_or_None, backport_hunk_or_None) pairs.
    """
    # Group by file
    u_by_file: dict[str, list[Hunk]] = {}
    b_by_file: dict[str, list[Hunk]] = {}
    for h in upstream_hunks:
        u_by_file.setdefault(h.file_a, []).append(h)
    for h in backport_hunks:
        b_by_file.setdefault(h.file_a, []).append(h)

    pairs = []
    all_files = set(u_by_file.keys()) | set(b_by_file.keys())

    for f in sorted(all_files):
        u_list = u_by_file.get(f, [])
        b_list = b_by_file.get(f, [])

        # Simple positional matching within same file
        for i in range(max(len(u_list), len(b_list))):
            u = u_list[i] if i < len(u_list) else None
            b = b_list[i] if i < len(b_list) else None
            pairs.append((u, b))

    return pairs


def classify_patch_pair(upstream_text: str, backport_text: str) -> dict:
    """
    Classify a backport pair into Type I-IV.
    Returns dict with 'type', 'hunk_details', and 'reason'.
    """
    upstream_hunks = parse_patch(upstream_text)
    backport_hunks = parse_patch(backport_text)

    if not upstream_hunks:
        return {"type": "Unknown", "hunk_details": [], "reason": "No upstream hunks parsed"}
    if not backport_hunks:
        return {"type": "Unknown", "hunk_details": [], "reason": "No backport hunks parsed"}

    # Quick check: if raw diff content is identical → Type-I
    u_stripped = _strip_commit_header(upstream_text).strip()
    b_stripped = backport_text.strip()
    if u_stripped == b_stripped:
        return {
            "type": "Type-I",
            "hunk_details": [{"hunk": i, "type": "Type-I"} for i in range(len(upstream_hunks))],
            "reason": "Patches are identical",
        }

    pairs = _match_hunks(upstream_hunks, backport_hunks)
    hunk_types = []
    hunk_details = []

    for idx, (u, b) in enumerate(pairs):
        if u is None:
            hunk_types.append("Type-IV")
            hunk_details.append({"hunk": idx, "type": "Type-IV", "reason": "extra hunk in backport"})
        elif b is None:
            hunk_types.append("Type-IV")
            hunk_details.append({"hunk": idx, "type": "Type-IV", "reason": "hunk dropped in backport"})
        else:
            ht = classify_hunk_pair(u, b)
            hunk_types.append(ht)
            hunk_details.append({"hunk": idx, "type": ht})

    # Overall type = worst case across all hunks
    type_order = {"Type-I": 0, "Type-II": 1, "Type-III": 2, "Type-IV": 3}
    overall = max(hunk_types, key=lambda t: type_order.get(t, 3))

    reasons = []
    if len(upstream_hunks) != len(backport_hunks):
        reasons.append(f"hunk count differs: {len(upstream_hunks)} upstream vs {len(backport_hunks)} backport")

    return {
        "type": overall,
        "hunk_details": hunk_details,
        "reason": "; ".join(reasons) if reasons else f"worst hunk: {overall}",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def classify_sample(sample_dir: str) -> Optional[dict]:
    """Classify a single sample directory."""
    upstream_path = os.path.join(sample_dir, "need_backport.patch")
    backport_path = os.path.join(sample_dir, "patch.txt")

    if not os.path.exists(upstream_path):
        return None
    if not os.path.exists(backport_path):
        return None

    with open(upstream_path, "r", errors="ignore") as f:
        upstream_text = f.read()
    with open(backport_path, "r", errors="ignore") as f:
        backport_text = f.read()

    if not upstream_text.strip() or not backport_text.strip():
        return None

    result = classify_patch_pair(upstream_text, backport_text)
    result["tag"] = os.path.basename(sample_dir)
    return result


def main():
    parser = argparse.ArgumentParser(description="Classify backport difficulty (Type I-IV)")
    parser.add_argument("--dataset-dir", help="Root dataset dir containing sample subdirs")
    parser.add_argument("--sample-dir", help="Single sample directory")
    parser.add_argument("--extid", help="Sample extid (e.g. 09e7336b5c7f5b7fa856), auto-searches under --dataset-root")
    parser.add_argument("--dataset-root", default="/home/lcj/patch_dataset",
                        help="Root path to search for extid (default: /home/lcj/patch_dataset)")
    parser.add_argument("--upstream", help="Path to upstream patch file")
    parser.add_argument("--backport", help="Path to backported patch file")
    parser.add_argument("--output", "-o", help="Output CSV file path")
    args = parser.parse_args()

    # Resolve --extid to --sample-dir
    if args.extid and not args.sample_dir:
        found = None
        root = args.dataset_root
        if os.path.isdir(root):
            for version_dir in sorted(os.listdir(root)):
                candidate = os.path.join(root, version_dir, args.extid)
                if os.path.isdir(candidate):
                    found = candidate
                    break
        if not found:
            print(f"Error: cannot find extid '{args.extid}' under {root}/*/")
            sys.exit(1)
        args.sample_dir = found
        print(f"Resolved extid to: {found}")

    results = []

    if args.upstream and args.backport:
        with open(args.upstream, "r", errors="ignore") as f:
            u_text = f.read()
        with open(args.backport, "r", errors="ignore") as f:
            b_text = f.read()
        result = classify_patch_pair(u_text, b_text)
        result["tag"] = "single"
        results.append(result)

    elif args.sample_dir:
        r = classify_sample(args.sample_dir)
        if r:
            results.append(r)
        else:
            print(f"Cannot classify: missing need_backport.patch or patch.txt in {args.sample_dir}")
            sys.exit(1)

    elif args.dataset_dir:
        for entry in sorted(os.listdir(args.dataset_dir)):
            sample_path = os.path.join(args.dataset_dir, entry)
            if not os.path.isdir(sample_path):
                continue
            r = classify_sample(sample_path)
            if r:
                results.append(r)

    else:
        parser.print_help()
        sys.exit(1)

    # Print results
    type_counts = {"Type-I": 0, "Type-II": 0, "Type-III": 0, "Type-IV": 0, "Unknown": 0}
    for r in results:
        t = r["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
        n_hunks = len(r["hunk_details"])
        hunk_summary = ", ".join(d["type"] for d in r["hunk_details"])
        print(f"{r['tag']}: {t} ({n_hunks} hunks: [{hunk_summary}]) — {r.get('reason', '')}")

    print(f"\n--- Summary ---")
    total = len(results)
    for t in ["Type-I", "Type-II", "Type-III", "Type-IV", "Unknown"]:
        c = type_counts[t]
        pct = f"{c/total*100:.1f}%" if total > 0 else "0%"
        print(f"  {t}: {c} ({pct})")
    print(f"  Total: {total}")

    # Output CSV if requested
    if args.output:
        with open(args.output, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["tag", "type", "num_hunks", "hunk_types", "reason"])
            for r in results:
                writer.writerow([
                    r["tag"],
                    r["type"],
                    len(r["hunk_details"]),
                    "|".join(d["type"] for d in r["hunk_details"]),
                    r.get("reason", ""),
                ])
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
