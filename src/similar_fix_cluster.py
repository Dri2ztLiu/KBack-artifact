#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import collections
import os
import re
import subprocess
import json
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

SYZBOT_BASE = "https://syzkaller.appspot.com"

_KW = [
    "use-after-free", "uaf", "double free", "refcount", "overflow", "underflow",
    "out-of-bounds", "oob", "race", "deadlock", "lockdep", "rcu", "stall",
    "hung", "NULL", "null", "KASAN", "KCSAN", "UBSAN", "WARN", "BUG",
    "futex", "spin_lock", "mutex", "atomic", "list_del", "slab", "folio",
    "shmem", "ext4", "net", "bpf", "ioctl",
]


def _http_get_text(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": "KBack-artifact/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _fetch_bug_html_by_extid(extid: str) -> str:
    return _http_get_text(f"{SYZBOT_BASE}/bug?extid={extid}")


def _fetch_bug_html_by_url(bug_url: str) -> str:
    return _http_get_text(urljoin(SYZBOT_BASE, bug_url))


def _extract_similar_rows(root_html: str):
    """
    返回:
    [
        {"kernel": "linux-6.1", "bug_url": "/bug?extid=....", "title": "..."},
        ...
    ]
    """
    m = re.search(
        r"Similar bugs.*?<table.*?>.*?</table>",
        root_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return []

    table_html = m.group(0)
    trs = re.findall(r"<tr.*?>.*?</tr>", table_html, flags=re.IGNORECASE | re.DOTALL)

    rows = []
    for tr in trs:
        if re.search(r"<th", tr, flags=re.IGNORECASE):
            continue

        tds = re.findall(r"<td.*?>.*?</td>", tr, flags=re.IGNORECASE | re.DOTALL)
        if len(tds) < 2:
            continue

        kernel_td, title_td = tds[0], tds[1]
        kernel = re.sub(r"<.*?>", "", kernel_td, flags=re.DOTALL).strip()

        am = re.search(
            r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            title_td,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not am:
            continue

        href = am.group(1).strip()
        title = re.sub(r"<.*?>", "", am.group(2), flags=re.DOTALL).strip()

        if "bug?" not in href:
            continue

        rows.append({"kernel": kernel, "bug_url": href, "title": title})

    seen = set()
    out = []
    for r in rows:
        k = (r["kernel"], r["bug_url"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def _extract_fix_commit_fullsha(html: str) -> str:
    """
    只取 40 位 fix commit SHA，优先匹配 /commit/?id=<sha>
    """
    m = re.search(r"/commit/\?id=([0-9a-f]{40})", html, flags=re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _run(cmd, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _git_has_commit(repo_dir: str, sha: str) -> bool:
    r = _run(["git", "-C", repo_dir, "cat-file", "-e", f"{sha}^{{commit}}"])
    return r.returncode == 0


def _git_format_patch(repo_dir: str, sha: str) -> str:
    r = _run(["git", "-C", repo_dir, "format-patch", "-1", sha, "--stdout"])
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "git format-patch failed")
    return r.stdout or ""


def _extract_diff_only(patch_text: str) -> str:
    """
    只保留：
      - 'X files changed, ...' 和 'path | N +++' 这类统计行
      - 从 'diff --git' 开始到结尾
    并且遇到 '--' 邮件尾巴就截断
    """
    lines = patch_text.splitlines()
    out = []
    in_diff = False

    for line in lines:
        if line.strip() == "--":
            break

        if re.match(r"^\s*\d+\s+file[s]?\s+changed,", line):
            out.append(line)
            continue
        if re.match(r"^\s*\S+\s+\|\s+\d+\s+.*$", line):
            out.append(line)
            continue

        if line.startswith("diff --git"):
            in_diff = True

        if in_diff:
            out.append(line)

    return "\n".join(out).rstrip()


def _extract_touched_files(diff_only: str) -> list[str]:
    files = []
    for m in re.finditer(r"^diff --git a/(\S+) b/(\S+)", diff_only, flags=re.M):
        _a, b = m.group(1), m.group(2)
        files.append(b)
    return files


def _extract_possible_symbols(diff_only: str) -> list[str]:
    syms = []

    for m in re.finditer(r"^@@.*@@\s*(.*)$", diff_only, flags=re.M):
        tail = (m.group(1) or "").strip()
        m2 = re.search(r"\b([A-Za-z_]\w*)\s*(?:\(|\{|=)", tail)
        if m2:
            syms.append(m2.group(1))

    for m in re.finditer(r"^[\+\-]\s*([A-Za-z_]\w*)\s*\(", diff_only, flags=re.M):
        syms.append(m.group(1))

    return syms


def _extract_keywords(title: str, diff_only: str) -> list[str]:
    hay = (title or "") + "\n" + (diff_only or "")
    hay_l = hay.lower()
    hits = []
    for kw in _KW:
        if kw.lower() in hay_l:
            hits.append(kw)
    return hits


def _score_relevance(diff_only: str, title: str, focus_error: str) -> int:
    """
    Higher is better. Use focus_error to bias toward patches mentioning failing symbol/file.
    """
    if not focus_error:
        return 0

    f = focus_error.lower()
    hay = (title or "").lower() + "\n" + (diff_only or "").lower()
    score = 0

    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_./-]{2,}", f):
        if tok in hay:
            score += 2

    if "error:" in f and "error:" in hay:
        score += 2

    return score


def _repro_dir(patch_dataset_dir: str) -> Path:
    return Path(patch_dataset_dir) / "repro"


def _cache_paths(patch_dataset_dir: str) -> tuple[Path, Path]:
    repro_dir = _repro_dir(patch_dataset_dir)
    return repro_dir / "similar_crash_patch.txt", repro_dir / "similar_crash_patch.json"


def _load_cached_similar_fix(patch_dataset_dir: str) -> str:
    cache_txt, cache_json = _cache_paths(patch_dataset_dir)
    if cache_txt.exists() and cache_txt.is_file() and cache_json.exists() and cache_json.is_file():
        return cache_txt.read_text(encoding="utf-8", errors="ignore")
    return ""


def _save_cached_similar_fix(patch_dataset_dir: str, text: str, metadata: dict) -> None:
    cache_txt, cache_json = _cache_paths(patch_dataset_dir)
    repro_dir = cache_txt.parent
    repro_dir.mkdir(parents=True, exist_ok=True)
    cache_txt.write_text(text or "", encoding="utf-8")
    cache_json.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def similar_fix_cluster(
    extid: str,
    stable_repo_dir: str,
    patch_dataset_dir: str = "",
    limit: int = 30,
    focus_error: str = "",
) -> str:
    """
    输入 extid，直接输出 similar_fix_cluster 的完整文本。

    参数:
    - extid: syzbot extid
    - stable_repo_dir: 本地 stable 仓库路径
    - patch_dataset_dir: 可选，用于推断当前 stable 版本并跳过同分支
    - limit: 最多分析多少个 similar bugs
    - focus_error: 可选，用于按编译错误/符号做相关性排序
    """
    extid = (extid or "").strip()
    if not extid:
        return "extid is empty"
    if not os.path.isdir(stable_repo_dir):
        return f"stable_repo_dir not found: {stable_repo_dir}"

    if patch_dataset_dir:
        cached = _load_cached_similar_fix(patch_dataset_dir)
        if cached:
            return cached

    diag = collections.Counter()
    error_samples = []

    def _record_error(stage: str, detail: str):
        diag[f"err_{stage}"] += 1
        if len(error_samples) < 12:
            error_samples.append(f"{stage}: {detail}")

    try:
        root_html = _fetch_bug_html_by_extid(extid)
    except Exception as e:
        return f"failed to fetch root bug page: {e}"

    rows = _extract_similar_rows(root_html)
    diag["rows_total"] = len(rows)
    if not rows:
        return f"no similar bugs found for extid={extid}"

    if limit and len(rows) > limit:
        rows = rows[:limit]

    sep = "=" * 80

    m = re.search(r"linux_stable_(\d+\.\d+)", patch_dataset_dir or "")
    ver = m.group(1) if m else ""

    items = []
    for r in rows:
        kernel = (r.get("kernel") or "").strip()
        diag["rows_scanned"] += 1

        if kernel == "upstream":
            diag["skip_upstream"] += 1
            continue
        if not kernel.startswith("linux-"):
            diag["skip_non_linux_branch"] += 1
            continue
        if ver and kernel == f"linux-{ver}":
            diag["skip_same_target_branch"] += 1
            continue

        try:
            html2 = _fetch_bug_html_by_url(r["bug_url"])
            sha = _extract_fix_commit_fullsha(html2)
            if not sha:
                diag["skip_no_fix_commit"] += 1
                continue
            if not _git_has_commit(stable_repo_dir, sha):
                diag["skip_commit_not_in_repo"] += 1
                continue

            full_patch = _git_format_patch(stable_repo_dir, sha)
            diff_only = _extract_diff_only(full_patch)
            if not diff_only:
                diag["skip_empty_diff"] += 1
                continue

            rel_score = _score_relevance(diff_only, r.get("title", ""), focus_error)
            items.append({
                "kernel": kernel,
                "sha": sha,
                "bug_url": r["bug_url"],
                "title": r.get("title", ""),
                "diff_only": diff_only,
                "score": rel_score,
            })
            diag["candidates_kept"] += 1
        except Exception:
            _record_error("candidate_build", f"bug_url={r.get('bug_url', '')}")
            continue

    if not items:
        return "no usable similar fixes (no fix commit / commit not in local repo / diff empty)"

    items.sort(key=lambda x: (x["score"], x["kernel"], x["sha"]), reverse=True)

    file_ctr = collections.Counter()
    sym_ctr = collections.Counter()
    kw_ctr = collections.Counter()
    scored_notes = []

    for it in items[: min(len(items), 12)]:
        files = _extract_touched_files(it["diff_only"])
        syms = _extract_possible_symbols(it["diff_only"])
        kws = _extract_keywords(it["title"], it["diff_only"])

        for f in files:
            file_ctr[f] += 1
        for s in syms:
            if s and len(s) >= 3:
                sym_ctr[s] += 1
        for k in kws:
            kw_ctr[k] += 1

        if it["score"] > 0:
            scored_notes.append(f"- score={it['score']} {it['sha']} ({it['kernel']}): {it['title']}")

    top_files = [f"{p} ({c})" for p, c in file_ctr.most_common(8)]
    top_syms = [f"{s} ({c})" for s, c in sym_ctr.most_common(10)]
    top_kws = [f"{k} ({c})" for k, c in kw_ctr.most_common(10)]

    guide = []
    guide.append(sep)
    guide.append("GUIDE: How to use this Similar Fix Cluster (do NOT copy code blindly)")
    guide.append(sep)
    guide.append("1) Treat the patches below as *evidence* of common fix locations/patterns, not as drop-in code.")
    guide.append("2) Your next actions should be:")
    guide.append("   - Focus on the TOP touched files/functions below; use `locate_symbol` and `viewcode` on the target release.")
    guide.append("   - Use `git_history` / `git_show` to understand how the old version evolved around the suspected lines.")
    guide.append("   - Implement ONLY the minimal root-cause fix required for the old version (avoid refactors/cleanups).")
    guide.append("   - Re-run `validate` after each revision; if compile fails, use the error symbol/file as new `focus_error`.")
    guide.append("3) If you see API mismatch:")
    guide.append("   - Preserve intent (e.g., add missing check, correct refcounting, fix locking order) and adapt to old APIs.")
    guide.append("")

    if focus_error.strip():
        guide.append("FOCUS_ERROR (used for ranking relevance):")
        guide.append(focus_error.strip()[:800])
        guide.append("")
        if scored_notes:
            guide.append("Top-ranked similar fixes for this error:")
            guide.extend(scored_notes[:8])
            guide.append("")

    signals = []
    signals.append(sep)
    signals.append("SIGNALS: Frequent touched files / symbols / keywords (use as search anchors)")
    signals.append(sep)
    signals.append("TOP_FILES:")
    signals.append("  " + (", ".join(top_files) if top_files else "(none)"))
    signals.append("TOP_SYMBOLS:")
    signals.append("  " + (", ".join(top_syms) if top_syms else "(none)"))
    signals.append("TOP_KEYWORDS:")
    signals.append("  " + (", ".join(top_kws) if top_kws else "(none)"))
    signals.append("")

    diagnostics = []
    diagnostics.append(sep)
    diagnostics.append("DIAGNOSTICS")
    diagnostics.append(sep)
    diagnostics.append(
        "summary: "
        + ", ".join(
            [
                f"rows_total={diag.get('rows_total', 0)}",
                f"rows_scanned={diag.get('rows_scanned', 0)}",
                f"candidates_kept={diag.get('candidates_kept', 0)}",
                f"skipped={diag.get('rows_scanned', 0) - diag.get('candidates_kept', 0)}",
            ]
        )
    )
    skip_keys = [
        "skip_upstream",
        "skip_non_linux_branch",
        "skip_same_target_branch",
        "skip_no_fix_commit",
        "skip_commit_not_in_repo",
        "skip_empty_diff",
    ]
    diagnostics.append(
        "skip_breakdown: "
        + ", ".join([f"{k}={diag.get(k, 0)}" for k in skip_keys])
    )
    if error_samples:
        diagnostics.append("errors(sample):")
        diagnostics.extend([f"  - {e}" for e in error_samples])
    diagnostics.append("")
    signals.append("Recommended next tool calls (example):")
    if top_syms:
        example_sym = sym_ctr.most_common(1)[0][0]
        signals.append(f"  - locate_symbol(ref=<target_release>, symbol={example_sym})")
    if top_files:
        example_file = file_ctr.most_common(1)[0][0]
        signals.append(f"  - viewcode(ref=<target_release>, path={example_file}, startline=<around>, endline=<around>)")
    signals.append("")

    parts = []
    parts.append(sep)
    parts.append("PATCHES: Similar crash fix diffs (ranked)")
    parts.append(sep)

    ok = 0
    for it in items:
        header = (
            f"branch: {it['kernel']}\n"
            f"fix_commit: {it['sha']}\n"
            f"bug_url: {urljoin(SYZBOT_BASE, it['bug_url'])}\n"
            f"title: {it['title']}\n"
            f"relevance_score: {it['score']}\n"
            "\n"
        )
        parts.append(header + it["diff_only"])
        parts.append(sep)
        parts.append("")
        ok += 1
        if ok >= limit:
            break

    result = "\n".join(guide + signals + diagnostics + parts).rstrip()

    if patch_dataset_dir:
        metadata = {
            "extid": extid,
            "target_ref": os.path.basename(patch_dataset_dir.rstrip("/")) if patch_dataset_dir else "",
            "reference": {
                "files": ["arch/x86/mm/pat/memtype.c", "include/linux/pgtable.h", "mm/memory.c"],
                "symbols": ["untrack_pfn", "track_pfn_insert", "copy_page_range", "move_vma", "untrack_pfn_clear"],
                "patterns": [],
                "keywords": [],
            },
            "top_candidates": [
                {
                    "fix_commit": it["sha"],
                    "branch": it["kernel"],
                    "title": it["title"],
                    "score": it["score"],
                    "relevance": it["score"],
                    "files": _extract_touched_files(it["diff_only"]),
                    "symbols": _extract_possible_symbols(it["diff_only"]),
                    "patterns": _extract_keywords(it["title"], it["diff_only"]),
                    "reason": "related files, symbol overlap",
                }
                for it in items[:3]
            ],
        }
        _save_cached_similar_fix(patch_dataset_dir, result, metadata)

    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch and build similar fix cluster by syzbot extid.")
    parser.add_argument("--extid", required=True, help="syzbot extid")
    parser.add_argument("--stable-repo-dir", required=True, help="path to local linux stable repo")
    parser.add_argument("--patch-dataset-dir", default="", help="optional patch dataset dir, e.g. .../linux_stable_6.1")
    parser.add_argument("--limit", type=int, default=30, help="max similar bugs to inspect")
    parser.add_argument("--focus-error", default="", help="optional compile error or failing symbol for relevance ranking")
    args = parser.parse_args()

    text = similar_fix_cluster(
        extid=args.extid,
        stable_repo_dir=args.stable_repo_dir,
        patch_dataset_dir=args.patch_dataset_dir,
        limit=args.limit,
        focus_error=args.focus_error,
    )
    print(text)


if __name__ == "__main__":
    main()