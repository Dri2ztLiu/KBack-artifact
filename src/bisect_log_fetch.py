#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import html
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen


SYZBOT_BASE = "https://syzkaller.appspot.com"


def _http_get_text(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": "KBack-artifact/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _fetch_bug_html_by_extid(extid: str) -> str:
    return _http_get_text(f"{SYZBOT_BASE}/bug?extid={extid}")


def _html_to_text(page_html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", "", page_html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", "", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)
    text = re.sub(r"(?i)</td\s*>", "\t", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def _normalize_lines(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    out = []
    prev_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and prev_blank:
            continue
        out.append(line)
        prev_blank = blank
    return "\n".join(out).strip()


def _extract_bisect_log(page_html: str) -> str:
    text = _normalize_lines(_html_to_text(page_html))
    if not text:
        return ""

    start_markers = [
        r"ci\d* starts bisection",
        r"bisecting fixing commit since",
        r"# git bisect start",
    ]
    end_markers = [
        r"\* Struck through repros",
        r"Similar bugs \(",
        r"Last patch testing requests \(",
        r"Fix bisection attempts \(",
    ]

    start = None
    for pattern in start_markers:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            start = match.start() if start is None else min(start, match.start())

    if start is None:
        return ""

    end = len(text)
    for pattern in end_markers:
        match = re.search(pattern, text[start:], flags=re.IGNORECASE)
        if match:
            end = min(end, start + match.start())

    extracted = text[start:end].strip()
    return extracted


def _cache_path(patch_dataset_dir: str) -> Path:
    return Path(patch_dataset_dir) / "repro" / "bisect_log.txt"


def fetch_bisect_log(extid: str, patch_dataset_dir: str = "") -> str:
    extid = (extid or "").strip()
    if not extid:
        return "extid is empty"

    cache_file = _cache_path(patch_dataset_dir) if patch_dataset_dir else None
    if cache_file and cache_file.exists() and cache_file.is_file():
        return cache_file.read_text(encoding="utf-8", errors="ignore")

    page_html = _fetch_bug_html_by_extid(extid)
    bisect_log = _extract_bisect_log(page_html)
    if not bisect_log:
        return "no bisect log found"

    if cache_file:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(bisect_log, encoding="utf-8")

    return bisect_log


def main():
    parser = argparse.ArgumentParser(description="Fetch and cache syzbot bisect log by extid.")
    parser.add_argument("--extid", required=True, help="syzbot extid")
    parser.add_argument("--patch-dataset-dir", default="", help="dataset dir to cache bisect_log.txt under repro/")
    args = parser.parse_args()

    print(fetch_bisect_log(args.extid, args.patch_dataset_dir))


if __name__ == "__main__":
    main()