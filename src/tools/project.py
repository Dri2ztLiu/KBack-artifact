import os
from pydoc import doc
import re
import subprocess
import tempfile
from types import SimpleNamespace
from typing import List, Tuple, Optional

import Levenshtein
from git import Repo
from langchain_core.tools import tool
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import tools.utils as utils
from tools.logger import logger
from langchain_core.tools import StructuredTool, BaseTool, Tool
import json


DEFAULT_ORACLE_COMPARE_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "run_oracle_compare_patch.sh")
)


class Project:
    def __init__(self, data: SimpleNamespace):
        self.project_url = data.project_url
        self.dir = data.project_dir
        self.repo = Repo(data.project_dir)

        if not data.error_message:
            self.err_msg = "no err_msg"
        else:
            self.err_msg = data.error_message

        self.new_patch_parent = data.new_patch_parent
        self.target_release = data.target_release
        self.succeeded_patches = []
        self.context_mismatch_times = 0
        self.missing_func_compile_failures = 0
        self.round_succeeded = False
        self.all_hunks_applied_succeeded = False
        self.compile_succeeded = False
        self.testcase_succeeded = False
        self.oracle_succeeded = False
        self.poc_succeeded = False
        self.symbol_map = {}
        self.now_hunk = ""
        self.now_hunk_num = 0
        self.hunk_log_info = {}
        self.add_percent = 0
        self.last_context = []
        self._recent_validate_patches: list[str] = []  # track recent validate submissions for duplicate detection
        self._consecutive_dup_count = 0  # consecutive duplicate validate calls
        self.patch_dataset_dir = data.patch_dataset_dir
        self.stable_repo_dir = data.stable_repo_dir
        self._viewcode_cache: dict[tuple, str] = {}  # cache for viewcode results
        self.project_dir = data.project_dir
        self.config_file = getattr(data, "config_file", "")
        self.oracle_enabled = bool(getattr(data, "oracle_enabled", True))
        self.oracle_compare_script = getattr(
            data,
            "oracle_compare_script",
            DEFAULT_ORACLE_COMPARE_SCRIPT,
        )
        self.oracle_timeout_minutes = int(getattr(data, "oracle_timeout_minutes", 120))

    def _checkout(self, ref: str) -> None:
        self.repo.git.reset("--hard")
        self.repo.git.checkout(ref)

    def _get_patch(self, ref: str) -> str:
        try:
            return self.repo.git.show(f"{ref}^..{ref}")
        except:
            return "Error commit id, please check if the commit id is correct."

    def _prepare(self, ref: str) -> None:
        """
        Prepares the project by generating a symbol map using ctags.

        Raises:
            subprocess.CalledProcessError: If the ctags command fails.
        """
        ctags = subprocess.run(
            ["ctags", "--excmd=number", "-R", "."],
            stdout=subprocess.PIPE,
            cwd=self.dir,
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        ctags.check_returncode()

        self.symbol_map[ref] = {}
        with open(os.path.join(self.dir, "tags"), "rb") as f:
            for line in f.readlines():
                if text := line.decode("utf-8", errors="ignore"):
                    if text.startswith("!_TAG_"):
                        continue
                    try:
                        symbol, file, lineno = text.strip().split(';"')[0].split("\t")
                        lineno = int(lineno)
                        if symbol not in self.symbol_map[ref]:
                            self.symbol_map[ref][symbol] = []
                        self.symbol_map[ref][symbol].append((file, lineno))
                    except:
                        continue

    def _viewcode(self, ref: str, path: str, startline: int, endline: int) -> str:
        """
        View a file from a specific ref of the target repository. Lines between startline and endline are shown.

        Args:
            ref (str): The specific ref of the target repository.
            path (str): The path of the file to view.
            startline (int): The starting line number to display.
            endline (int): The ending line number to display.

        Returns:
            str: The content of the file between the specified startline and endline.
                 If the file doesn't exist in the commit, a message indicating that is returned.
        """
        # Check cache to avoid repeated identical viewcode calls
        cache_key = (ref, path, startline, endline)
        if cache_key in self._viewcode_cache:
            logger.debug(f"viewcode cache hit: {path}:{startline}-{endline}")
            return (
                "[NOTE: You already viewed this exact code range before. "
                "The content has NOT changed. Re-reading the same lines will not help. "
                "If you need different information, try a DIFFERENT line range or file.]\n\n"
                + self._viewcode_cache[cache_key]
            )
        # Check for highly overlapping ranges (>= 80% overlap with a cached range)
        for (c_ref, c_path, c_start, c_end), c_result in self._viewcode_cache.items():
            if c_ref == ref and c_path == path:
                overlap_start = max(startline, c_start)
                overlap_end = min(endline, c_end)
                if overlap_end >= overlap_start:
                    overlap_len = overlap_end - overlap_start + 1
                    request_len = endline - startline + 1
                    if request_len > 0 and overlap_len / request_len >= 0.8:
                        logger.debug(f"viewcode overlap hit: {path}:{startline}-{endline} vs cached {c_start}-{c_end}")
                        return (
                            f"[NOTE: You already viewed {path}:{c_start}-{c_end} which covers {overlap_len}/{request_len} "
                            f"lines of your request. The content has NOT changed since then. "
                            f"If you need lines outside that range, request only the NEW lines.]\n\n"
                            + c_result
                        )
        try:
            file = self.repo.tree(ref) / path
        except:
            return "This file doesn't exist in this commit."
        content = file.data_stream.read().decode("utf-8", errors="ignore")
        lines = content.split("\n")
        ret = []
        if endline > len(lines):
            startline -= endline - len(lines)
            endline = len(lines)
            ret.append(
                f"This file only has {len(lines)} lines. Here are lines {startline} through {endline}.\n"
            )
        else:
            ret.append(f"Here are lines {startline} through {endline}.\n")
        for i in range(startline - 1, endline):
            ret.append(lines[i])
        result = (
            "\n".join(ret)
            + "\nBased on the previous information, think carefully do you see the target code? You may want to keep checking if you don't.\n"
        )
        self._viewcode_cache[cache_key] = result
        return result

    def _locate_symbol(self, ref: str, symbol: str) -> List[Tuple[str, int]] | None:
        """
        Locate a symbol in a specific ref of the target repository.

        Args:
            ref (str): The reference of the target repository.
            symbol (str): The symbol to locate.

        Returns:
            List[Tuple[str, int]] | None: File path and code lines.
        """
        # XXX: Analyzing ctags file everytime locate symbol is time-consuming.
        if ref not in self.symbol_map:
            self._checkout(ref)
            self._prepare(ref)

        if symbol in self.symbol_map[ref]:
            return self.symbol_map[ref][symbol]
        else:
            return None

    def _locate_similar_symbol(
        self, ref: str, symbol: str, top_n: int = 5
    ) -> Tuple[List[dict], str]:
        """
        Locate the most similar symbols in a specific ref of the target repository.
        Returns top-N candidates ranked by name similarity + same-file bonus,
        each with function signature extracted from the source.

        Args:
            ref (str): The reference of the target repository.
            symbol (str): The symbol to locate.
            top_n (int): Number of candidates to return.

        Returns:
            Tuple[List[dict], str]: List of candidate dicts and the best match name.
        """
        import heapq

        symbols = self.symbol_map.get(ref, {})
        if not symbols:
            return [], ""

        # Determine the file context of the missing symbol for same-file bonus
        # (the upstream patch likely tells us which file it's in)
        context_files = set()
        context_dirs = set()
        if hasattr(self, 'now_hunk') and self.now_hunk and self.now_hunk != "completed":
            m = re.findall(r"--- a/(.*)", self.now_hunk)
            if m:
                context_files.add(m[0])
                # also add the directory for same-directory bonus
                context_dirs = {os.path.dirname(m[0])}

        # Score all symbols: lower is better
        scored = []
        for sym_name, locations in symbols.items():
            edit_dist = Levenshtein.distance(symbol, sym_name)

            # Same-file bonus: reduce distance by 3
            same_file = any(f in context_files for f, _ in locations)
            same_dir = any(
                os.path.dirname(f) in context_dirs for f, _ in locations
            ) if context_dirs else False

            adjusted = edit_dist
            if same_file:
                adjusted = max(0, adjusted - 3)
            elif same_dir:
                adjusted = max(0, adjusted - 1)

            scored.append((adjusted, edit_dist, sym_name, locations))

        # Get top-N by adjusted score
        top_candidates = heapq.nsmallest(top_n, scored, key=lambda x: (x[0], x[1]))

        # Extract function signatures for each candidate
        candidates = []
        for adjusted, edit_dist, sym_name, locations in top_candidates:
            file_path, lineno = locations[0]
            signature = self._extract_signature(ref, file_path, lineno)
            candidates.append({
                "name": sym_name,
                "file": file_path,
                "line": lineno,
                "edit_distance": edit_dist,
                "signature": signature,
                "same_file": any(f in context_files for f, _ in locations),
            })

        best_name = candidates[0]["name"] if candidates else ""
        return candidates, best_name

    def _extract_signature(self, ref: str, file_path: str, lineno: int) -> str:
        """Extract the function/macro signature starting at lineno (up to closing paren or 3 lines)."""
        try:
            blob = self.repo.tree(ref) / file_path
            content = blob.data_stream.read().decode("utf-8", errors="ignore")
            lines = content.split("\n")
            # Collect up to 4 lines starting from lineno to capture multi-line signatures
            sig_lines = []
            for i in range(lineno - 1, min(lineno + 3, len(lines))):
                sig_lines.append(lines[i])
                if "{" in lines[i] or ";" in lines[i]:
                    break
            sig = " ".join(l.strip() for l in sig_lines)
            # Trim after opening brace
            if "{" in sig:
                sig = sig[: sig.index("{")].rstrip()
            return sig
        except Exception:
            return ""

    def _git_history(self) -> str:
        """
        XXX: TBD

        Args:
            XXX

        Returns:
            XXX(str):
        """
        if self.now_hunk != "completed":
            merge_base = self.repo.merge_base(
                self.target_release, self.new_patch_parent
            )
            start_commit = merge_base[0].hexsha if merge_base else None
            hunk = self.now_hunk
            filepath = re.findall(r"--- a/(.*)", hunk)[0]
            chunks = re.findall(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)", hunk)[0]
            start_line = chunks[0]
            end_line = int(chunks[0]) + int(chunks[1]) - 1
            log_message = self.repo.git.log(
                "--oneline",
                f"-L {start_line},{end_line}:{filepath}",
                f"{start_commit}..{self.new_patch_parent}",
            )
            # save each hunk related refs
            if self.now_hunk_num not in self.hunk_log_info and log_message:
                last_context = list(utils.split_patch(log_message, False))[-1]
                (
                    _,
                    context_line_num,
                    self.last_context,
                    add_line_num,
                ) = utils.extract_context(last_context.split("\n")[3:])
                self.add_percent = add_line_num / (add_line_num + context_line_num)

                self.hunk_log_info[self.now_hunk_num] = []
                patch_list = log_message.split("\n")
                for idx, line in enumerate(patch_list):
                    if line.startswith("diff --git"):
                        sha_num = patch_list[idx - 2].split(" ")[0]
                        self.hunk_log_info[self.now_hunk_num].append(sha_num)

            ret = log_message[len(log_message) - 5001 : -1]
            ret += "\nYou need to do the following analysis based on the information in the last commit:\n"
            ret += "Analyze the code logic of the context of the patch to be ported in this commit step by step.\n"
            ret += "If code logic already existed before this commit, the patch context can be assumed to remain in a similar location. Use `locate` and `viewcode` to check your results.\n"
            ret += "If code logic were added in this commit, then you need to `git_show` for further details.\n"
            ret += "If the information provided so far is still insufficient to clearly identify or reconstruct the intent of this hunk, you may call `similar_fix_cluster` to reference fix patches from similar crashes. Use these patches only to infer common modification locations (files/functions) and high-level fix patterns to help validate the porting direction, but do not copy any code directly."
            return ret

        else:
            # XXX TBD
            # JUST return each hunk related refs
            pass

    def _git_show(self) -> str:
        """
        Show commit message for a specific ref when LLM need.

        Args:
            ref (str): The reference of the target repository.

        Returns:
            message(str): The commit message of ref
        """
        try:
            # XXX maybe too much context will confuse LLM, how could we refine it.
            ref_line = self.hunk_log_info[self.now_hunk_num][-1]
            ref = ref_line.split(" ")[0].strip()
            log = self.repo.git.show(f"{ref}")
            pps = utils.split_patch(log, False)
            dist = float("inf")
            last_context_len = len(self.last_context)
            best_context = []
            file_path = ""
            file_no = 0

            for idx, pp in enumerate(pps):
                try:
                    file_path_i = re.findall(r"--- a/(.*)", pp)[0]
                    chunks = re.findall(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)", pp)[0]
                    contexts, _, _, _ = utils.extract_context(pp.split("\n")[3:])
                    if (int(chunks[1]) - int(chunks[3])) < last_context_len:
                        continue
                    lineno, dist_i = utils.find_most_similar_block(
                        self.last_context, contexts, last_context_len, False
                    )
                    if dist_i < dist:
                        best_context = contexts[
                            lineno - 1 : lineno - 1 + last_context_len
                        ]
                        dist = dist_i
                        file_path = file_path_i
                        file_no = int(chunks[0]) + lineno - 1
                except:
                    continue

            ret = ""
            stat = self.repo.git.show("--stat", f"{ref}")
            ret += stat[0 : min(len(stat), 3000)]
            ret += "\n"
            if self.add_percent < 0.6:
                ret += f"[IMPORTANT] The relevant code shown by `git_history` is not fully `+` lines.\n"
                ret += f"[IMPORTANT] This means that the code in question was not added or migrated in this commit.\n"
                ret += f"[IMPORTANT] Please think step by step and check the abstract below carefully. If error exists in abstract, please ignore the info below.\n"
            elif best_context:
                ret += f"Because the commit's code change maybe too long, so I generate the abstract of the code change to show you how code changed in this commit.\n"
                ret += f"Commit shows that the patch code in old version maybe in the file {file_path} around line number {file_no} to {file_no + last_context_len}. The code is below\n"
                code_snippets = "\n".join(best_context)
                ret += f"{code_snippets}"
                ret += f"\nYou can call `viewcode` and `locate_symbol` to find the relevant code based on this information step by step."
            else:
                ret += f"This commit shows that there is a high probability that this code is new, so the corresponding code segment cannot be found in the old version.\n"
                ret += f"You can call `viewcode` and `locate_symbol` to further check the results step by step. For newly introduced code, we consider that this hunk `need not ported`.\n"
            return ret
        except:
            return "Something error, maybe you don't use git_history before or git_history is empty."

    def _apply_error_handling(self, ref: str, revised_patch: str) -> Tuple[str, str]:
        """
        Generate feedback to llm when an error patch is applied.
        When a file is not found, it is looked for in the five most similar files.

        Args:
            ref (str): The reference of the target repository.
            revised_patch (str): The patch to be applied.

        Returns:
            Tuple[str, str]: Bug patch similar code block information and difference between patch context and original code context.

        """
        path_matches = re.findall(r"--- a/(.*)", revised_patch)
        if not path_matches:
            return (
                "The patch is malformed: missing `--- a/...` file header. "
                "Please provide a complete unified diff with proper headers.\n",
                "",
            )
        path = path_matches[0]
        revised_patch_line = revised_patch.split("\n")[3:]
        contexts, num_context, _, _ = utils.extract_context(revised_patch_line)
        lineno = -1
        lines = []
        min_distance = float("inf")

        try:
            file = self.repo.tree(ref) / path
            content = file.data_stream.read().decode("utf-8", errors="ignore")
            lines = content.split("\n")
            lineno, dist = utils.find_most_similar_block(
                contexts, lines, num_context, False
            )
        except:
            similar_files = utils.find_most_similar_files(path.split("/")[-1], self.dir)
            for similar_file in similar_files:
                file = self.repo.tree(ref) / similar_file
                content = file.data_stream.read().decode("utf-8", errors="ignore")
                similar_lines = content.split("\n")
                current_line, current_dist = utils.find_most_similar_block(
                    "\n".join(contexts), similar_lines, num_context, False
                )

                if current_dist < min_distance:
                    min_distance = current_dist
                    lineno = current_line
                    path = similar_file
                    lines = similar_lines

        startline = max(lineno - 1, 0)
        endline = min(lineno + num_context, len(lines))
        if not lines or lineno < 0:
            block = f"Could not locate similar code block in {path} for commit {ref}.\n"
        else:
            block = "Here are lines {} through {} of file {} for commit {}.\n".format(
                startline, endline, path, ref
            )
            block += "```code snippet\n"
            for i in range(startline, endline):
                block = block + lines[i] + "\n"
            block += "```\n"

        differ = "```context diff\n"
        contexts = contexts[: min(len(lines), len(contexts))]
        j = 0
        for i, context in enumerate(revised_patch_line):
            if context.startswith(" ") or context.startswith("-"):
                src_idx = lineno - 1 + j
                if src_idx >= len(lines):
                    break
                if context[1:] != lines[src_idx]:
                    differ += f"On the line {i + 4} of your patch.\n"
                    differ += f"          Your patch:{context[1:]}\n"
                    differ += f"Original source code:{lines[src_idx]}\n"
                j += 1

        if differ == "```context diff\n":
            differ = "Here it shows that there is no difference between your context and the original code, the reason for the failure is that you didn't keep at least three lines of source code at the beginning and end of the patch, please follow this to fix it.\n"
        else:
            differ += "```\nPlease eliminate these diffs step by step. Be sure to eliminate these diffs the next time you generate a patch!\n"
        return block, differ

    def _apply_file_move_handling(self, ref: str, old_patch: str) -> str:
        """
        If a patch cannot apply for "No such file", try to find the symbol and apply the patch to the correct file.

        Args:
            ref (str): The reference string.
            old_patch (str): The patch that raises "No such file" when apply.

        Returns:
            str: If the file is found, return the current file path. Else, return all possible file paths.
        """
        ret = ""
        file_paths = []
        missing_file_path = re.findall(r"--- a/(.*)", old_patch)[0]

        # locate file by git diff
        diff_args = [
            "--diff-filter=R",
            "--name-status",
            "--follow",
            self.target_release,
            self.new_patch_parent,
            "--",
            missing_file_path,
        ]
        file_diff = self.repo.git.diff(diff_args)
        if file_diff:
            file_path = file_diff.split("\t")[1]
            logger.debug(
                f"We have found the patch's file path is {file_path} at target release by git diff."
            )
            file_paths.append(file_path)

        # locate target file by symbol or utils.find_most_similar_files
        if not file_paths:
            try:
                # XXX: find symbol: the word before the first '{' or '('
                # @@ -135,7 +135,6 @@ struct ksmbd_transport_ops {
                # @@ -416,13 +416,7 @@ static void stop_sessions(void)
                at_line = old_patch.split("\n")[2]
                symbol_name = re.findall(r"\b\w+(?=\s*[{\(])", at_line)[0]
                symbol_locations = self._locate_symbol(ref, symbol_name)
                if not symbol_locations:
                    logger.debug(
                        f"No {missing_file_path} and no {symbol_name} in the repo."
                    )
                    file_paths = utils.find_most_similar_files(
                        missing_file_path.split("/")[-1], self.dir
                    )
                else:
                    logger.debug(f"Find {symbol_name} in {symbol_locations}.")
                    file_paths = [item[0] for item in symbol_locations]
            except:
                logger.debug("Can not find a symbol in given patch.")
                file_paths = utils.find_most_similar_files(
                    missing_file_path.split("/")[-1], self.dir
                )

        # try to apply patch to the target files
        for file_path in file_paths:
            new_patch = old_patch.replace(missing_file_path, file_path)
            logger.debug(f"Try to apply patch to {file_path}.")
            apply_ret = self._apply_hunk(ref, new_patch, False)
            if "successfully" in apply_ret:
                logger.debug(f"{missing_file_path} has been moved to {file_path}.")
                return f"{missing_file_path} has been moved to {file_path}. Please use --- a/{file_path} in your patch.\n"
            else:
                ret += apply_ret

        # patch can not apply directly
        logger.debug(f"Patch can not be applied to {file_paths}.")
        return f"The target file has been moved, here is possible file paths:{file_paths}\n{ret}"

    def _apply_hunk(self, ref: str, patch: str, revise_context: bool = False) -> str:
        """
        Apply a hunk to a specific ref of the target repository.

        Args:
            ref (str): The reference of the target repository.
            patch (str): The patch to be applied.

        Returns:
            str: A string indicating the result of the patch application.

        Raises:
            Exception: If the patch fails to apply.

        """
        ret = ""
        self._checkout(ref)
        self.repo.git.reset("--hard")

        # Re-apply previously succeeded hunks so the working tree is up-to-date
        for prev_patch in self.succeeded_patches:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as pf:
                pf.write(prev_patch)
            try:
                self.repo.git.apply([pf.name], v=True)
            except Exception:
                logger.warning("Failed to re-apply a previously succeeded hunk, skipping")

        patch = self._normalize_patch_text(patch)
        if revise_context:
            logger.debug("original patch:\n" + patch)
        revised_patch, fixed = utils.revise_patch(patch, self.dir, revise_context)
        revised_patch = self._normalize_patch_text(revised_patch)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
            f.write(revised_patch)
        logger.debug("revised patch:\n" + revised_patch)
        logger.debug(f"Applying patch {f.name}")

        # Detect no-op patches where removed and added lines are identical
        _removes = [l[1:].strip() for l in revised_patch.splitlines()
                     if l.startswith('-') and not l.startswith('---')]
        _adds = [l[1:].strip() for l in revised_patch.splitlines()
                 if l.startswith('+') and not l.startswith('+++')]
        if _removes and _removes == _adds:
            logger.debug("No-op patch detected: removed and added lines are identical")
            ret += ("This patch has NO actual code change — the removed lines and added lines "
                    "are identical. Please provide a patch with meaningful modifications that "
                    "actually fix the bug.\n")
            self.repo.git.reset("--hard")
            return ret

        try:
            self.repo.git.apply([f.name], v=True)
            ret += "Patch applied successfully\n"
            self.succeeded_patches.append(revised_patch)
            self.round_succeeded = True
        except Exception as e:
            if "No such file" in e.stderr:
                logger.debug(f"File not found")
                find_ret = self._apply_file_move_handling(ref, revised_patch)
                ret += find_ret
            elif "corrupt patch" in e.stderr:
                ret = "Unexpected corrupt patch, Please carefully check your answer, especially in your call tools arguments.\n"
                # raise Exception("Unexpected corrupt patch")
            else:
                # Fallback: try relaxed context matching (-C1, then -C0)
                applied_with_fuzzy = False
                try:
                    self.repo.git.reset("--hard")
                    self._checkout(ref)
                    for prev_patch in self.succeeded_patches:
                        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as pf:
                            pf.write(prev_patch)
                        try:
                            self.repo.git.apply([pf.name], v=True)
                        except Exception:
                            pass
                    self.repo.git.apply([f.name, "-C1"], v=True)
                    logger.info("Patch applied successfully with -C1")
                    ret += "Patch applied successfully (with -C1 fuzzy context)\n"
                    self.succeeded_patches.append(revised_patch)
                    self.round_succeeded = True
                    applied_with_fuzzy = True
                except Exception:
                    logger.debug("Fallback -C1 also failed")

                if not applied_with_fuzzy:
                    # Fallback: try wiggle --replace for word-level merge
                    try:
                        self.repo.git.reset("--hard")
                        self._checkout(ref)
                        for prev_patch in self.succeeded_patches:
                            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as pf:
                                pf.write(prev_patch)
                            try:
                                self.repo.git.apply([pf.name], v=True)
                            except Exception:
                                pass
                        # Extract target file path from patch
                        _target_files = [
                            line.split("b/", 1)[1].strip()
                            for line in revised_patch.splitlines()
                            if line.startswith("+++ b/")
                        ]
                        wiggle_ok = True
                        for tf in _target_files:
                            tf_abs = os.path.join(self.dir, tf)
                            if not os.path.isfile(tf_abs):
                                wiggle_ok = False
                                break
                            wr = subprocess.run(
                                ["wiggle", "--replace", tf_abs, "-"],
                                input=revised_patch, capture_output=True, text=True, timeout=30
                            )
                            if wr.returncode == 2:  # 2 = unresolved conflicts
                                wiggle_ok = False
                                # Restore original file
                                if os.path.isfile(tf_abs + ".porig"):
                                    os.replace(tf_abs + ".porig", tf_abs)
                                break
                            # wiggle returns 0 (clean) or 1 (resolved with wiggling)
                        if wiggle_ok and _target_files:
                            # Clean up .porig backup files
                            for tf in _target_files:
                                porig = os.path.join(self.dir, tf) + ".porig"
                                if os.path.isfile(porig):
                                    os.remove(porig)
                            # After wiggle successfully modified files, revise the patch headers
                            try:
                                revised_patch2, fixed2 = utils.revise_patch(revised_patch, self.dir, True)
                                revised_patch2 = self._normalize_patch_text(revised_patch2)
                                logger.info("Patch applied successfully via wiggle (headers revised)")
                                ret += "Patch applied successfully (via wiggle word-level merge; headers revised)\n"
                                self.succeeded_patches.append(revised_patch2)
                            except Exception:
                                # Fallback to original revised_patch if revise fails
                                logger.info("Patch applied successfully via wiggle (header revise failed, using original)")
                                ret += "Patch applied successfully (via wiggle word-level merge)\n"
                                self.succeeded_patches.append(revised_patch)
                            self.round_succeeded = True
                            applied_with_fuzzy = True
                    except Exception as wiggle_err:
                        logger.debug(f"Wiggle fallback failed: {wiggle_err}")

                if not applied_with_fuzzy:
                    logger.debug(f"Context mismatch")
                    ret += "This patch does not apply because of CONTEXT MISMATCH. Context are patch lines that already exist in the file, that is, lines starting with ` ` and `-`. You should modify the error patch according to the context of older version.\n"
                    block, differ = self._apply_error_handling(ref, revised_patch)
                    ret += block
                    ret += "Besides, here is detailed info about how the context differs between the patch and the old version.\n"
                    ret += differ

        self.repo.git.reset("--hard")
        return ret

    def _compile_patch(
        self, ref: str, complete_patch: str, revise_context: bool = False
    ) -> str:
        """
        If all hunks could be applied successfully, compiles the patched source code after applying the joined patch.

        Args:
            ref (str): The reference to checkout before applying the patch.
            complete_patch (str): The complete patch to be applied.

        Returns:
            str: A message indicating the result of the compilation process.

        Raises:
            subprocess.TimeoutExpired: If the compilation process times out.

        """
        # apply joined patch
        self._checkout(ref)
        ret = ""
        complete_patch = self._normalize_patch_text(complete_patch)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
            f.write(complete_patch)
            logger.debug(f"The completed patch file {f.name}")
        pps = utils.split_patch(complete_patch, False)
        revised_hunks = []
        for idx, pp in enumerate(pps):
            revised_patch, fixed = utils.revise_patch(pp, self.dir, revise_context)
            revised_patch = self._normalize_patch_text(revised_patch)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
                f.write(revised_patch)
            try:
                self.repo.git.apply([f.name], v=True)
                revised_hunks.append(revised_patch)
                logger.debug(
                    f"The joined patch hunk {idx} could be applied successfully, file {f.name}"
                )
            except Exception as e:
                # Fallback: try relaxed context matching (-C1, then -C0)
                applied_with_fuzzy = False
                try:
                    self.repo.git.apply([f.name, "-C1"], v=True)
                    revised_hunks.append(revised_patch)
                    logger.info(
                        f"The joined patch hunk {idx} applied with -C1, file {f.name}"
                    )
                    applied_with_fuzzy = True
                except Exception:
                    logger.debug(f"Fallback -C1 for hunk {idx} also failed")

                if applied_with_fuzzy:
                    continue

                # Fallback: try wiggle --replace for word-level merge
                try:
                    _target_files = [
                        line.split("b/", 1)[1].strip()
                        for line in revised_patch.splitlines()
                        if line.startswith("+++ b/")
                    ]
                    wiggle_ok = True
                    for tf in _target_files:
                        tf_abs = os.path.join(self.dir, tf)
                        if not os.path.isfile(tf_abs):
                            wiggle_ok = False
                            break
                        wr = subprocess.run(
                            ["wiggle", "--replace", tf_abs, "-"],
                            input=revised_patch, capture_output=True, text=True, timeout=30
                        )
                        if wr.returncode == 2:
                            wiggle_ok = False
                            if os.path.isfile(tf_abs + ".porig"):
                                os.replace(tf_abs + ".porig", tf_abs)
                            break
                    if wiggle_ok and _target_files:
                        for tf in _target_files:
                            porig = os.path.join(self.dir, tf) + ".porig"
                            if os.path.isfile(porig):
                                os.remove(porig)
                        # Revise hunk header to match actual applied location after wiggle
                        try:
                            revised_patch2, fixed2 = utils.revise_patch(revised_patch, self.dir, True)
                            revised_patch2 = self._normalize_patch_text(revised_patch2)
                            revised_hunks.append(revised_patch2)
                            logger.info(f"The joined patch hunk {idx} applied via wiggle (headers revised)")
                        except Exception:
                            revised_hunks.append(revised_patch)
                            logger.info(f"The joined patch hunk {idx} applied via wiggle")
                        continue
                except Exception as wiggle_err:
                    logger.debug(f"Wiggle fallback for hunk {idx} failed: {wiggle_err}")

                logger.debug(
                    f"Failed to apply Complete patch hunk {idx}, file {f.name}"
                )
                # TODO: give feedback to LLM about which line can not be applied
                ret = f"For the patch you just generated, there was an APPLY failure during testing. Specifically there was a context mismatch in hunk {idx} across the patch, below is part of the feedback I found for you.\n"
                block, differ = self._apply_error_handling(ref, revised_patch)
                ret += block
                ret += f"Here is the source code near the hunk context for your reference, a good patch context should look exactly like the source code.\n"
                ret += f"In addition to that, I've got more detailed error messages for you below where the context of your generated patch differs specifically from the source code context.(The line numbers below are all line numbers in the hunk, not the entire patch.)\n"
                ret += differ
                ret += f"Based on the above feedback, MUST you please modify only hunk {idx} in the patch and leave the other hunks untouched so that the context present in hunk {idx} is exactly the same as the source code to guarantee that git apply can be executed normally.\n"
                self.repo.git.reset("--hard")
                return ret

        # Store the revised (actually applied) patch for oracle consumption
        if revised_hunks:
            self._last_revised_patch = "\n".join(h.rstrip("\n") for h in revised_hunks) + "\n"
        else:
            self._last_revised_patch = None

        # compile the patch
        logger.debug("Start compile the patched source code")
        if not os.path.exists(os.path.join(self.dir, "build.sh")):
            logger.debug("No build.sh file found.")
            ret += "The patched source code could be COMPILED successfully! I really thank you for your great efforts.\n"
            self.compile_succeeded = True
            return ret

        patch_dataset_dir = self.patch_dataset_dir
        # If a build.sh exists in the provided dataset dir, copy it into the project tree first.
        logger.debug(f"patch_dataset_dir: {patch_dataset_dir}")
        if patch_dataset_dir and os.path.exists(os.path.join(patch_dataset_dir, "build.sh")):
            abs_dataset = os.path.abspath(patch_dataset_dir)
            try:
                shutil.copy2(os.path.join(abs_dataset, "build.sh"), os.path.join(self.dir, "build.sh"))
            except Exception as e:
                logger.warning(f"Failed to copy dataset build.sh into project dir: {e}")

        build_command = ["/bin/bash", "build.sh"]
        logger.info("Build Command: " + " ".join(build_command))
        build_process = subprocess.Popen(
            build_command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.dir,
            text=True,
        )
        try:
            out, compile_result = build_process.communicate(timeout=60 * 60)
        except subprocess.TimeoutExpired:
            build_process.kill()
            ret += f"The compilation process of the patched source code is timeout. "
            self.repo.git.reset("--hard")
            logger.warning(
                "Timeout in project compilation. Please check patch manually!"
            )
            for patch in self.succeeded_patches:
                logger.info(patch)
            return ret
        logger.info("Command Returncode: " + str(build_process.returncode))
        if build_process.returncode != 0:
            logger.info(f"Compile message: {compile_result}")
            logger.info(f"Compilation                       FAILED")
            error_lines = "\n".join(
                [
                    line
                    for line in compile_result.splitlines()
                    if "error:" in line.lower()
                ]
            )
            logger.debug(error_lines)
            ret += "The source code could not be COMPILED successfully after applying the patch. "
            ret += "Next I'll give you the error message during compiling, and you should modify the error patch. "
            ret += f"Here is the error message:\n{error_lines}\n"

            # Show actual source code around error lines so LLM can see the problem
            source_context_snippets = self._extract_compile_error_context(error_lines)
            if source_context_snippets:
                ret += "\n[Source code at error locations (AFTER patch was applied)]\n"
                ret += "Use this to understand what the compiler actually sees:\n"
                ret += source_context_snippets + "\n"
            if "implicit declaration of function" in error_lines or "undefined reference" in error_lines:
                self.missing_func_compile_failures += 1
                if self.missing_func_compile_failures >= 2:
                    ret += "HINT: The error above indicates a MISSING FUNCTION in the target branch. "
                    ret += "You have already tried replacing it with an existing similar function, but compilation still fails. "
                    ret += "Use `locate_symbol` to confirm, then use `viewcode` with the UPSTREAM ref to read the missing function's implementation. "
                    ret += "If the function is simple and self-contained, create a static inline version adapted to the target branch and add it to the patch BEFORE the calling code. "
                    ret += "Do NOT just replace the call with -EINVAL or remove the fix logic.\n"
            ret += "Please revise the patch with above error message. "
            ret += "Or use tools `locate_symbol`,`similar_fix_cluster` and `viewcode` to re-check patch-related code snippet. "
            ret += "Please DO NOT send the same patch to me, repeated patches will harm the lives of others.\n"
            self.repo.git.reset("--hard")
        else:
            logger.info(f"Compilation                       PASS")
            ret += "The patched source code could be COMPILED successfully! I really thank you for your great efforts.\n"
            self.compile_succeeded = True
        # self.repo.git.reset("--hard")
        return ret

    def _extract_compile_error_context(self, error_lines: str, context_radius: int = 5) -> str:
        """Extract source code snippets around compile error locations.

        Parses gcc error lines like 'fs/sysv/super.c:353:1: error: ...'
        and reads ±context_radius lines from each error location.
        """
        import re
        seen = set()
        snippets = []
        for line in error_lines.splitlines():
            m = re.match(r'^([^:]+):(\d+):\d+:\s*error:', line)
            if not m:
                continue
            filepath = m.group(1)
            lineno = int(m.group(2))
            key = (filepath, lineno)
            if key in seen:
                continue
            seen.add(key)
            if len(seen) > 5:
                break
            abs_path = os.path.join(self.dir, filepath)
            if not os.path.isfile(abs_path):
                continue
            try:
                with open(abs_path, "r", errors="replace") as f:
                    src_lines = f.readlines()
                start = max(0, lineno - context_radius - 1)
                end = min(len(src_lines), lineno + context_radius)
                snippet = ""
                for i in range(start, end):
                    marker = ">>>" if i == lineno - 1 else "   "
                    snippet += f"{marker} {i+1:5d} | {src_lines[i].rstrip()}\n"
                snippets.append(f"--- {filepath}:{lineno} ---\n{snippet}")
            except Exception:
                continue
        return "\n".join(snippets)

    def _precheck_complete_patch_apply(
        self, ref: str, complete_patch: str, revise_context: bool = False
    ) -> str:
        """Fast precheck: verify full patch can be applied before compile/oracle."""
        self._checkout(ref)
        self.repo.git.reset("--hard")

        complete_patch = self._normalize_patch_text(complete_patch)
        pps = utils.split_patch(complete_patch, False)
        for idx, pp in enumerate(pps):
            revised_patch, _ = utils.revise_patch(pp, self.dir, revise_context)
            revised_patch = self._normalize_patch_text(revised_patch)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
                f.write(revised_patch)
            try:
                self.repo.git.apply([f.name], v=True)
            except Exception:
                # Fallback: try relaxed context matching (-C1, then -C0)
                applied_with_fuzzy = False
                try:
                    self.repo.git.apply([f.name, "-C1"], v=True)
                    logger.info(f"Precheck hunk {idx} applied with -C1")
                    applied_with_fuzzy = True
                except Exception:
                    pass

                if applied_with_fuzzy:
                    continue

                # Fallback: try wiggle --replace for word-level merge
                try:
                    _target_files = [
                        line.split("b/", 1)[1].strip()
                        for line in revised_patch.splitlines()
                        if line.startswith("+++ b/")
                    ]
                    wiggle_ok = True
                    for tf in _target_files:
                        tf_abs = os.path.join(self.dir, tf)
                        if not os.path.isfile(tf_abs):
                            wiggle_ok = False
                            break
                        wr = subprocess.run(
                            ["wiggle", "--replace", tf_abs, "-"],
                            input=revised_patch, capture_output=True, text=True, timeout=30
                        )
                        if wr.returncode == 2:
                            wiggle_ok = False
                            if os.path.isfile(tf_abs + ".porig"):
                                os.replace(tf_abs + ".porig", tf_abs)
                            break
                    if wiggle_ok and _target_files:
                        for tf in _target_files:
                            porig = os.path.join(self.dir, tf) + ".porig"
                            if os.path.isfile(porig):
                                os.remove(porig)
                        logger.info(f"Precheck hunk {idx} applied via wiggle")
                        continue
                except Exception as wiggle_err:
                    logger.debug(f"Wiggle fallback for precheck hunk {idx} failed: {wiggle_err}")

                ret = (
                    "For the patch you just generated, there was an APPLY failure before expensive validation. "
                    f"Specifically there was a context mismatch in hunk {idx} across the patch.\n"
                )
                block, differ = self._apply_error_handling(ref, revised_patch)
                ret += block
                ret += (
                    "Here is the source code near the hunk context for your reference, a good patch context should "
                    "look exactly like the source code.\n"
                )
                ret += (
                    "In addition to that, I've got more detailed error messages for you below where the context of "
                    "your generated patch differs specifically from the source code context. "
                    "(The line numbers below are all line numbers in the hunk, not the entire patch.)\n"
                )
                ret += differ
                ret += (
                    f"Based on the above feedback, MUST you please modify only hunk {idx} in the patch and leave "
                    "the other hunks untouched so that git apply can be executed normally.\n"
                )
                self.repo.git.reset("--hard")
                return ret

        self.repo.git.reset("--hard")
        return "Patch apply precheck passed."

    def _run_testcase(self) -> str:
        """
        Runs the testcase after compiling a patch.

        Returns:
            str: A message indicating the result of the testcase process.
        """
        ret = ""
        logger.debug("Run testcase after compile")

        if not os.path.exists(os.path.join(self.dir, "test.sh")):
            logger.debug("No test.sh file found, considered as test passed.")
            self.testcase_succeeded = True
            ret += "The patched source code could pass TESTCASE! I really thank you for your great efforts.\n"
            return ret
        testcase_process = subprocess.Popen(
            ["/bin/bash", "test.sh"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.dir,
            text=True,
        )

        try:
            _, testcase_result = testcase_process.communicate(timeout=60 * 30)
        except subprocess.TimeoutExpired:
            testcase_process.kill()
            ret += "The TESTCASE process of the patched source code is timeout. "
            return ret

        if testcase_process.returncode != 0:
            logger.info(f"Testsuite                         FAILED")
            logger.debug(f"{testcase_result}")
            ret = "The patched program could not pass the testcase. "
            ret += "Next I'll give you the error message during running the testcase, and you should modify the previous error patch according to this section. "
            ret += f"Here is the error message:\n{testcase_result}\n"
            ret += "Please revise the patch with above error message. "
            ret += "Or use tools `locate_symbol` and `viewcode` to re-check patch-related code snippet. "
            ret += "Please DO NOT send the same patch to me, repeated patches will harm the lives of others.\n"
            self.compile_succeeded = False
        else:
            logger.info(f"Testsuite                         PASS")
            ret += "The patched source code could pass TESTCASE! I really thank you for your great efforts.\n"
            self.testcase_succeeded = True
        return ret

    def _run_poc(self, complete_patch) -> str:
        """
        Runs the Proof of Concept (PoC) after running the testcase.

        Returns:
            str: A message indicating the result of the PoC process.
        """
        ret = ""
        logger.debug("Run PoC after compile and run testcase")

        if not os.path.exists(os.path.join(self.dir, "poc.sh")):
            logger.debug("No poc.sh file found, considered as PoC passed.")
            self.poc_succeeded = True
            self.succeeded_patches.clear()
            self.succeeded_patches.append(complete_patch)
            ret += "Existing PoC could NOT TRIGGER the bug, which means your patch successfully fix the bug! I really thank you for your great efforts.\n"
            return ret
        poc_process = subprocess.Popen(
            ["/bin/bash", "poc.sh"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.dir,
            text=True,
        )

        try:
            _, poc_result = poc_process.communicate(timeout=60 * 10)
        except subprocess.TimeoutExpired:
            poc_process.kill()
            ret += "The TESTCASE process of the patched source code is timeout. "
            return ret

        if self.err_msg in poc_result:
            logger.info(f"PoC test                          FAILED")
            logger.debug(f"returncode = {poc_process.returncode}")
            logger.debug(f"stderr: {poc_result}")
            ret += "Existing PoC could still trigger the bug, which means your patch fail to fix the bug. "
            ret += "Next I'll give you the error message during running the PoC, and you should modify the previous error patch according to this section. "
            ret += f"Here is the error message:\n{poc_result}\n"
            ret += "Please revise the patch with above error message. "
            ret += "Or use tools `locate_symbol` and `viewcode` to re-check patch-related code snippet. "
            ret += "Please DO NOT send the same patch to me, repeated patches will harm the lives of others.\n"
            self.compile_succeeded = False
            self.testcase_succeeded = False
        else:
            logger.info(f"PoC test                          PASS")
            ret += "Existing PoC could NOT TRIGGER the bug, which means your patch successfully fix the bug! I really thank you for your great efforts.\n"
            self.succeeded_patches.clear()
            self.succeeded_patches.append(complete_patch)
            self.poc_succeeded = True
        return ret
    
    def _extract_hints(self, text: str, max_lines: int = 120) -> str:
        """
        Extract actionable error-like lines from oracle output.
        Keep it simple but useful for agent feedback.
        """
        if not text:
            return ""
        rx = re.compile(
            r"(error:|failed|failure|BUG:|WARNING:|KASAN:|KCSAN:|UBSAN:|Oops:|panic|"
            r"blocked for more than|rcu: INFO: .*stall|not ready|timeout|No such file|"
            r"Compilation\s+FAILED|Testsuite\s+FAILED|PoC test\s+FAILED)",
            re.IGNORECASE,
        )
        hits = []
        for line in text.splitlines():
            if rx.search(line):
                hits.append(line.rstrip())
                if len(hits) >= max_lines:
                    break
        return "\n".join(hits)

    def _extract_error_lines(self, text: str, max_lines: int = 120) -> str:
        """Extract only build/runtime error lines to reduce noisy tail output."""
        if not text:
            return ""
        rx = re.compile(
            r"(error:|fatal error:|undefined reference|BUILD_BUG|compiletime_assert|"
            r"make\[\d+\]: \*\*\*|FAILED)",
            re.IGNORECASE,
        )
        hits = []
        for line in text.splitlines():
            if rx.search(line):
                hits.append(line.rstrip())
                if len(hits) >= max_lines:
                    break
        return "\n".join(hits)

    def _extract_stage_key_output(self, stage: str, text: str, max_lines: int = 120) -> str:
        """Extract stage-specific key lines so feedback stays focused by failure type."""
        if not text:
            return ""

        stage = (stage or "").strip()
        if stage == "kernel_build":
            return self._extract_error_lines(text, max_lines)

        patterns = {
            "patch_apply": re.compile(
                r"(Failed to apply patch|patch failed:|corrupt patch|malformed patch|No such file to patch|"
                r"git apply.*failed|Hunk #\d+ FAILED)",
                re.IGNORECASE,
            ),
            "qemu_boot": re.compile(
                r"(qemu.*(failed|timeout|not ready)|ssh.*(refused|failed|timeout)|Kernel panic|"
                r"BUG:|Oops:|not syncing)",
                re.IGNORECASE,
            ),
            "reproduce": re.compile(
                r"(BUG:|KASAN:|KCSAN:|UBSAN:|WARNING:|panic|general protection fault|"
                r"signature|runtime missing|repro.*failed)",
                re.IGNORECASE,
            ),
        }

        rx = patterns.get(stage)
        if not rx:
            return self._extract_hints(text, max_lines)

        hits = []
        for line in text.splitlines():
            if rx.search(line):
                hits.append(line.rstrip())
                if len(hits) >= max_lines:
                    break
        return "\n".join(hits)

    def _extract_primary_error_matches(self, focus_text: str, max_lines: int = 120) -> list[str]:
        """Extract only lines under [primary_error_matches] section from build.focus.log."""
        if not focus_text:
            return []
        lines = focus_text.splitlines()
        in_section = False
        out: list[str] = []
        for raw in lines:
            line = raw.rstrip()
            if line.strip() == "[primary_error_matches]":
                in_section = True
                continue
            if in_section and line.startswith("["):
                break
            if not in_section:
                continue
            if not line.strip():
                continue
            out.append(line)
            if len(out) >= max_lines:
                break
        return out

    def _tail(self, text: str, n: int = 200) -> str:
        if not text:
            return ""
        lines = text.splitlines()
        return "\n".join(lines[-n:])

    def _normalize_patch_text(self, patch: str) -> str:
        if patch is None:
            return ""
        text = str(patch)
        if text and not text.endswith("\n"):
            text += "\n"
        return text

    def _write_patch_artifact(self, patch: str) -> tuple[bool, str]:
        """Persist current candidate patch for oracle compare script consumption."""
        dataset_dir = self.patch_dataset_dir or ""
        if not dataset_dir:
            return False, "patch_dataset_dir is empty"
        try:
            os.makedirs(dataset_dir, exist_ok=True)
            patch_file = os.path.join(dataset_dir, "patch.txt")
            patch_tmp = patch_file + ".tmp"
            with open(patch_tmp, "w", encoding="utf-8") as f:
                f.write(self._normalize_patch_text(patch))
            os.replace(patch_tmp, patch_file)
            return True, patch_file
        except Exception as e:
            return False, str(e)

    def _apply_kernel_config_updates(self, updates: list[dict]) -> str:
        """Apply CONFIG_* updates to runtime config copy while keeping original kernel.config untouched.

        Safety behavior:
        - Always read current runtime/base config first.
        - Only update keys that already exist in the config file.
        - Unknown CONFIG_* keys are skipped to avoid guess-based config writes.
        """
        repro_dir = os.path.join(self.patch_dataset_dir or "", "repro")
        config_path = os.path.join(repro_dir, "kernel.config")
        backup_path = os.path.join(repro_dir, "kernel.config.backup")
        runtime_path = os.path.join(repro_dir, "kernel.config.runtime")
        if not os.path.isfile(config_path):
            return f"kernel config not found: {config_path}"
        if not isinstance(updates, list) or not updates:
            return "no config updates requested"

        # Keep immutable baseline copy. All updates are applied to runtime copy.
        try:
            if not os.path.isfile(backup_path):
                with open(config_path, "r", encoding="utf-8", errors="ignore") as src:
                    original_text = src.read()
                with open(backup_path, "w", encoding="utf-8") as bak:
                    bak.write(original_text)
        except Exception as e:
            return f"failed to prepare kernel config backup: {e}"

        source_path = runtime_path if os.path.isfile(runtime_path) else backup_path

        try:
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.read().splitlines()
        except Exception as e:
            return f"failed to read kernel config: {e}"

        existing_keys = set()
        set_rx = re.compile(r"^(CONFIG_[A-Z0-9_]+)=.*$")
        unset_rx = re.compile(r"^# (CONFIG_[A-Z0-9_]+) is not set$")
        for line in lines:
            m = set_rx.match(line)
            if m:
                existing_keys.add(m.group(1))
                continue
            m = unset_rx.match(line)
            if m:
                existing_keys.add(m.group(1))

        changed = []
        skipped_unknown = []
        skipped_invalid = []
        for item in updates:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()
            val = str(item.get("value", "")).strip().lower()
            if not re.fullmatch(r"CONFIG_[A-Z0-9_]+", key):
                skipped_invalid.append(key)
                continue
            if val not in {"y", "m", "n"}:
                skipped_invalid.append(f"{key}={val}")
                continue
            if key not in existing_keys:
                skipped_unknown.append(key)
                continue

            new_line = f"# {key} is not set" if val == "n" else f"{key}={val}"
            set_pat = re.compile(rf"^{re.escape(key)}=.*$")
            unset_pat = re.compile(rf"^# {re.escape(key)} is not set$")

            replaced = False
            for i, line in enumerate(lines):
                if set_pat.match(line) or unset_pat.match(line):
                    if lines[i] != new_line:
                        lines[i] = new_line
                        changed.append(f"{key}={val}")
                    replaced = True
                    break

            if not replaced:
                # Should not happen because key is required to exist, but keep safe fallback.
                skipped_unknown.append(key)

        if not changed:
            msg = "no valid kernel config updates applied"
            extras = []
            if skipped_unknown:
                extras.append("unknown keys skipped: " + ", ".join(skipped_unknown[:16]))
            if skipped_invalid:
                extras.append("invalid updates skipped: " + ", ".join(skipped_invalid[:16]))
            if extras:
                msg += "; " + "; ".join(extras)
            return msg

        try:
            with open(runtime_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            return f"failed to write kernel config: {e}"

        ret = (
            "applied kernel config updates: "
            + ", ".join(changed)
            + f" (runtime={runtime_path}, original_kept={config_path})"
        )
        if skipped_unknown:
            ret += "; unknown keys skipped: " + ", ".join(skipped_unknown[:16])
        if skipped_invalid:
            ret += "; invalid updates skipped: " + ", ".join(skipped_invalid[:16])
        return ret

    def _parse_oracle_summary_kv(self, summary_text: str) -> dict:
        kv = {}
        if not summary_text:
            return kv
        for line in summary_text.splitlines():
            line = line.strip()
            if not line:
                continue
            for k, v in re.findall(r"([A-Za-z_]+)=([^\s]+)", line):
                kv[k] = v
        return kv

    def _pick_matching_lines(self, text: str, pattern: str, max_lines: int = 10) -> list:
        if not text:
            return []
        rx = re.compile(pattern, re.IGNORECASE)
        out = []
        for line in text.splitlines():
            if rx.search(line):
                out.append(line.rstrip())
                if len(out) >= max_lines:
                    break
        return out

    def _build_ready_marker_from_log(self, build_log_path: str) -> bool:
        """Build is considered ready only if the third line from the end is the bzImage ready marker."""
        if not build_log_path or not os.path.isfile(build_log_path):
            return False
        try:
            with open(build_log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.read().splitlines()
        except Exception:
            return False
        if len(lines) < 3:
            return False
        return lines[-3].strip() == "Kernel: arch/x86/boot/bzImage is ready"

    def _userspace_ready_from_log(self, userspace_log_path: str) -> bool:
        """QEMU/userspace is considered ready only when userspace.log exists and is non-empty."""
        if not userspace_log_path or not os.path.isfile(userspace_log_path):
            return False
        try:
            return os.path.getsize(userspace_log_path) > 0
        except Exception:
            return False

    def _parse_oracle_structured_feedback(
        self,
        oracle_output: str,
        summary_text: str,
        evidence_text: str,
        oracle_rc: int,
        kernel_build_primary_lines: list[str] | None = None,
        build_ready_marker: bool | None = None,
        qemu_userspace_ready: bool | None = None,
    ) -> dict:
        summary = self._parse_oracle_summary_kv(summary_text)
        merged = "\n".join([oracle_output or "", evidence_text or ""])

        def _choose_stage_value(key: str, default: str = "") -> str:
            """Prefer after_* values for patch-related classification; fallback to before_* only when after is unavailable/skipped."""
            after_v = str(summary.get(f"after_{key}", "") or "").strip()
            before_v = str(summary.get(f"before_{key}", "") or "").strip()
            if after_v and after_v != "skipped":
                return after_v
            if not after_v:
                return before_v or default
            return default

        apply_fail = self._pick_matching_lines(
            merged,
            r"(Failed to apply patch|patch failed:|corrupt patch|malformed patch|No such file to patch|git apply.*failed)",
        )
        apply_pass = self._pick_matching_lines(
            merged,
            r"(Applying patch|patch applied|apply patch.*success)",
        )

        build_fail = [x.rstrip() for x in (kernel_build_primary_lines or []) if str(x).strip()]
        if not build_fail:
            build_fail = self._pick_matching_lines(
                merged,
                r"(Compilation\s+FAILED|build failed|make\[\d+\]: \*\*\*|error:)",
            )
        build_pass = self._pick_matching_lines(
            merged,
            r"(Compilation\s+PASS|build succeeded)",
        )

        qemu_fail = self._pick_matching_lines(
            merged,
            r"(qemu.*(failed|timeout|not ready)|missing userspace\.log|ssh.*(refused|failed)|Kernel panic|BUG:)",
        )
        qemu_pass = self._pick_matching_lines(
            merged,
            r"(userspace\.log|boot completed|login:)",
        )

        apply_status = "unknown"
        if apply_fail:
            apply_status = "failed"
        elif apply_pass:
            apply_status = "passed"
        apply_summary_status = _choose_stage_value("patch_apply_status")
        if apply_summary_status:
            apply_status = apply_summary_status

        build_status = "unknown"
        if build_fail:
            build_status = "failed"
        elif build_pass:
            build_status = "passed"
        build_summary_status = _choose_stage_value("kernel_build_status")
        # Only let summary override if it's a definitive status;
        # don't let "pending" override a regex-detected "failed".
        if build_summary_status and build_summary_status not in {"pending", "unknown"}:
            build_status = build_summary_status
        elif build_summary_status == "pending" and build_fail:
            build_status = "failed"
        if build_ready_marker is True and build_status in {"unknown", "pending"}:
            build_status = "passed"

        qemu_status = "unknown"
        detect_after = summary.get("detect_after", "")
        if detect_after == "125":
            qemu_status = "inconclusive"
        elif detect_after in {"0", "1"}:
            qemu_status = "passed"
        if qemu_fail:
            qemu_status = "failed"
        elif qemu_pass and qemu_status == "unknown":
            qemu_status = "passed"
        qemu_summary_status = _choose_stage_value("qemu_boot_status")
        if qemu_summary_status:
            qemu_status = qemu_summary_status
        if qemu_userspace_ready is False and qemu_status not in {"skipped", "pending"}:
            qemu_status = "failed"
            if not qemu_fail:
                qemu_fail = ["missing userspace.log"]

        verdict_after = summary.get("verdict_after", "")
        if verdict_after == "clean":
            repro_status = "passed"
        elif verdict_after == "crash":
            repro_status = "failed"
        elif verdict_after == "inconclusive":
            repro_status = "inconclusive"
        elif verdict_after == "SKIPPED":
            repro_status = "skipped"
        else:
            repro_status = "unknown"
        repro_summary_status = _choose_stage_value("reproduce_status")
        if repro_summary_status:
            repro_status = repro_summary_status

        selected_failure_reason = _choose_stage_value("failure_reason")

        overall = summary.get("RESULT", "")
        if not overall:
            if oracle_rc == 0:
                overall = "FIXED"
            elif oracle_rc == 125:
                overall = "INCONCLUSIVE"
            else:
                overall = "FAILED"

        failure_stage = ""
        failure_reason = ""
        # Deterministic stage decision order: build -> patch_apply -> qemu -> reproduce.
        if build_status == "failed":
            failure_stage = "kernel_build"
            failure_reason = selected_failure_reason or "kernel_build_failed"
        elif apply_status == "failed":
            failure_stage = "patch_apply"
            failure_reason = selected_failure_reason
        elif qemu_status in {"failed", "inconclusive"}:
            failure_stage = "qemu_test"
            failure_reason = selected_failure_reason or "qemu_userspace_not_ready"
        elif repro_status in {"failed", "inconclusive", "skipped"}:
            failure_stage = "reproduce"
            failure_reason = selected_failure_reason

        stage_payload = {
            "patch_apply": {
                "status": apply_status,
                "evidence": apply_fail[:6] if apply_fail else apply_pass[:3],
            },
            "kernel_build": {
                "status": build_status,
                "evidence": build_fail[:6] if build_fail else build_pass[:3],
            },
            "qemu_test": {
                "status": qemu_status,
                "evidence": qemu_fail[:6] if qemu_fail else qemu_pass[:3],
            },
            "reproduce": {
                "status": repro_status,
                "evidence": [
                    f"verdict_before={summary.get('verdict_before', '')}",
                    f"verdict_after={summary.get('verdict_after', '')}",
                ],
            },
        }

        if not failure_stage:
            failure_stage = _choose_stage_value("failure_stage")
            failure_reason = selected_failure_reason

        # When overall result is FIXED, suppress failure fields — they are artifacts
        # of single-run stage_status.json which doesn't know "clean" means success.
        if overall == "FIXED":
            failure_stage = ""
            failure_reason = ""

        concise_stages = {}
        if failure_stage and failure_stage in stage_payload:
            concise_stages[failure_stage] = stage_payload[failure_stage]
        # Always include kernel_build evidence when failure_reason mentions it
        if "kernel_build" in (failure_reason or "") and "kernel_build" not in concise_stages:
            concise_stages["kernel_build"] = stage_payload["kernel_build"]

        # For FIXED results, include reproduce stage with correct verdict info
        if overall == "FIXED" and "reproduce" not in concise_stages:
            concise_stages["reproduce"] = {
                "status": "passed",
                "evidence": [
                    f"verdict_before={summary.get('verdict_before', '')}",
                    f"verdict_after={summary.get('verdict_after', '')}",
                ],
            }

        return {
            "overall_result": overall,
            "oracle_exit_code": oracle_rc,
            "summary": {
                "failure_stage": failure_stage,
                "failure_reason": failure_reason,
                "verdict_before": summary.get("verdict_before", ""),
                "verdict_after": summary.get("verdict_after", ""),
            },
            "stages": concise_stages,
        }

    def _run_oracle(self) -> str:
        """
        Run oracle compare script and convert result into LLM-actionable feedback.
        """
        ret = ""
        logger.debug("Run oracle after compile")

        if not self.oracle_enabled:
            logger.info("Oracle                           SKIPPED (oracle_enabled=false)")
            self.oracle_succeeded = True
            return "Oracle validation is disabled by configuration.\n"

        oracle_script = self.oracle_compare_script or ""
        if not oracle_script:
            oracle_script = DEFAULT_ORACLE_COMPARE_SCRIPT

        if not os.path.isabs(oracle_script):
            oracle_script = os.path.abspath(oracle_script)

        config_file = self.config_file or ""

        if not os.path.exists(oracle_script):
            logger.info("Oracle                           FAILED")
            self.compile_succeeded = False
            self.testcase_succeeded = False
            self.poc_succeeded = False
            self.oracle_succeeded = False
            return (
                "Oracle script is missing, so oracle validation could not run. "
                f"Missing script: {oracle_script}\n"
            )

        if not config_file or not os.path.isfile(config_file):
            logger.info("Oracle                           FAILED")
            self.compile_succeeded = False
            self.testcase_succeeded = False
            self.poc_succeeded = False
            self.oracle_succeeded = False
            return (
                "Oracle config file is missing, so oracle validation could not run. "
                f"Missing config: {config_file}\n"
            )

        cmd = ["/bin/bash", oracle_script, config_file]
        logger.debug("oracle cmd: %s", " ".join(cmd))
        oracle_process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.dir,
            text=True,
        )

        try:
            out, err = oracle_process.communicate(timeout=60 * self.oracle_timeout_minutes)
        except subprocess.TimeoutExpired:
            oracle_process.kill()
            self.compile_succeeded = False
            self.testcase_succeeded = False
            self.poc_succeeded = False
            self.oracle_succeeded = False
            ret += "The ORACLE process of the patched source code is timeout. "
            return ret

        # merge output like many of your other steps
        oracle_result = ""
        if out:
            oracle_result += out
        if err:
            if oracle_result and not oracle_result.endswith("\n"):
                oracle_result += "\n"
            oracle_result += err

        # Enrich with latest oracle artifacts (summary + llm_evidence) when available.
        summary_text = ""
        evidence_text = ""
        kernel_build_primary_lines: list[str] = []
        build_ready_marker: bool | None = None
        qemu_userspace_ready: bool | None = None
        root_dir = os.path.abspath(
            os.path.join(os.path.dirname(oracle_script), "..", "oracle_runs")
        )
        try:
            if os.path.isdir(root_dir):
                latest = sorted(
                    [
                        os.path.join(root_dir, x)
                        for x in os.listdir(root_dir)
                        if x.startswith("compare_patch_")
                    ],
                    key=os.path.getmtime,
                )
                if latest:
                    summary_file = os.path.join(latest[-1], "summary.txt")
                    evidence_file = os.path.join(latest[-1], "llm_evidence.txt")
                    if os.path.isfile(summary_file):
                        with open(summary_file, "r", encoding="utf-8", errors="ignore") as f:
                            summary_text = f.read()
                            oracle_result += "\n\n[oracle_summary]\n" + summary_text
                    if os.path.isfile(evidence_file):
                        with open(evidence_file, "r", encoding="utf-8", errors="ignore") as f:
                            evidence_text = f.read()
                            evidence_errors = self._extract_error_lines(evidence_text, 120)
                            if evidence_errors:
                                oracle_result += "\n\n[oracle_llm_evidence_errors]\n" + evidence_errors
        except Exception as e:
            logger.warning("Collect oracle artifacts failed: %s", e)

        # Load stage-focused logs based on summary kv (before/after failure_stage and *_log pointers).
        try:
            summary_kv = self._parse_oracle_summary_kv(summary_text)
            build_log_candidates = [
                summary_kv.get("after_kernel_build_log", "").strip(),
                summary_kv.get("before_kernel_build_log", "").strip(),
            ]
            for p in build_log_candidates:
                if p and os.path.isfile(p):
                    build_ready_marker = self._build_ready_marker_from_log(p)
                    break
            userspace_candidates = [
                summary_kv.get("after_reproduce_userspace_log", "").strip(),
                summary_kv.get("before_reproduce_userspace_log", "").strip(),
            ]
            for p in userspace_candidates:
                if p:
                    qemu_userspace_ready = self._userspace_ready_from_log(p)
                    break
            after_failure_stage = summary_kv.get("after_failure_stage", "").strip().lower()
            prefixes = ["after"] if after_failure_stage and after_failure_stage != "skipped" else ["after", "before"]
            for prefix in prefixes:
                stage = summary_kv.get(f"{prefix}_failure_stage", "").strip()
                if not stage:
                    continue
                log_key = f"{prefix}_{stage}_log"
                focus_log_key = f"{prefix}_{stage}_focus_log"
                focus_log = summary_kv.get(focus_log_key, "").strip()
                if not focus_log:
                    focus_log = summary_kv.get(log_key, "").strip()
                if focus_log and os.path.isfile(focus_log):
                    with open(focus_log, "r", encoding="utf-8", errors="ignore") as f:
                        focus_text = f.read()
                        if stage == "kernel_build":
                            primary_lines = self._extract_primary_error_matches(focus_text, 120)
                            if primary_lines:
                                kernel_build_primary_lines = primary_lines
                        focus_errors = self._extract_stage_key_output(stage, focus_text, 120)
                        if not focus_errors:
                            continue
                        oracle_result += (
                            f"\n\n[oracle_stage_focus_{prefix}] stage={stage} reason="
                            f"{summary_kv.get(f'{prefix}_failure_reason', '')}\n"
                        )
                        oracle_result += focus_errors

                if stage == "reproduce":
                    userspace_key = f"{prefix}_reproduce_userspace_log"
                    userspace_log = summary_kv.get(userspace_key, "").strip()
                    if userspace_log and os.path.isfile(userspace_log):
                        with open(userspace_log, "r", encoding="utf-8", errors="ignore") as f:
                            oracle_result += f"\n\n[oracle_userspace_focus_{prefix}]\n"
                            oracle_result += self._tail(f.read(), 160)
        except Exception as e:
            logger.warning("Collect oracle stage focus logs failed: %s", e)

        # hint_lines = self._extract_hints(oracle_result)
        structured_feedback = self._parse_oracle_structured_feedback(
            oracle_result,
            summary_text,
            evidence_text,
            oracle_process.returncode,
            kernel_build_primary_lines,
            build_ready_marker,
            qemu_userspace_ready,
        )
        structured_feedback_json = json.dumps(
            structured_feedback,
            ensure_ascii=False,
            indent=2,
        )
        if oracle_process.returncode != 0:
            logger.info("Oracle                           FAILED")
            logger.debug("Oracle failed: emitting structured + error-focused feedback")

            ret = "The patched program could not pass the oracle validation. "
            ret += "Next I'll give you the oracle feedback (patch apply / kernel build / qemu / reproduce), and you should modify the previous patch according to this section. "
            ret += f"Structured oracle feedback (JSON):\n{structured_feedback_json}\n"
            failure_stage = structured_feedback.get("summary", {}).get("failure_stage", "")
            failure_reason = structured_feedback.get("summary", {}).get("failure_reason", "")
            if failure_stage:
                ret += f"Detected failure stage: {failure_stage}. "
            if failure_reason:
                ret += f"Failure reason: {failure_reason}. "
            if failure_stage == "kernel_build" or "kernel_build" in (failure_reason or ""):
                ret += "This failure is likely pre-patch/config related (the kernel build failed, possibly even WITHOUT the patch applied). You may use `adjust_config` first for configuration experiments (including control runs to skip patch-focused flows). If configuration changes do not improve oracle results, treat this case as environment-limited rather than forcing patch-context analysis. "
            elif failure_stage == "patch_apply":
                ret += "This failure is a patch-application issue. Please inspect the patch context and use `viewcode`/`locate_symbol` if needed. "
            else:
                ret += "Please revise according to the stage-specific error message above. "
            ret += "Please DO NOT send the same patch to me, repeated patches will harm the lives of others.\n"

            # mark as failed like testcase does
            self.compile_succeeded = False
            self.testcase_succeeded = False
            self.poc_succeeded = False
            self.oracle_succeeded = False
        else:
            logger.info("Oracle                           PASS")
            ret += "The patched source code could pass ORACLE validation! Thank you for your great efforts.\n"
            ret += f"Structured oracle feedback (JSON):\n{structured_feedback_json}\n"
            self.oracle_succeeded = True
            self.testcase_succeeded = True
            self.poc_succeeded = True
        logger.info(ret)
        return ret

    def _validate(self, ref: str, patch: str) -> str:
        """
        Validates a patch by using the `_compile_patch`, `_run_testcase`, and `_run_poc` methods.

        Args:
            ref (str): The reference string.
            patch (str): The patch string.

        Returns:
            str: The validation result.

        """
        # Duplicate patch detection within a single agent invocation
        normalized = self._normalize_patch_text(patch) if patch else ""
        if normalized and self._recent_validate_patches and normalized == self._recent_validate_patches[-1]:
            self._consecutive_dup_count += 1
            if self._consecutive_dup_count >= 3:
                logger.warning("Validate called with the same patch %d consecutive times, forcing early stop", self._consecutive_dup_count)
                return (
                    "FATAL: You have submitted the EXACT SAME patch %d times in a row. "
                    "Each attempt produces the same compilation errors. Continuing to submit identical patches is pointless.\n"
                    "MANDATORY: You MUST use `viewcode` to read the actual source code at the error locations, "
                    "understand what the compiler sees, and produce a STRUCTURALLY DIFFERENT patch.\n"
                    "If you cannot fix the compilation error, stop calling validate and explain the issue instead." % self._consecutive_dup_count
                )
        else:
            self._consecutive_dup_count = 0
        self._recent_validate_patches.append(normalized)
        if self.all_hunks_applied_succeeded:
            ret = ""
            self.oracle_succeeded = False
            if not self.compile_succeeded:
                ret += self._compile_patch(
                    ref, patch, revise_context=True
                )
                self.context_mismatch_times += 1
            if self.compile_succeeded and not self.oracle_succeeded:
                artifact_patch = getattr(self, '_last_revised_patch', None) or patch
                if artifact_patch != patch:
                    logger.info("Using revised (context-fixed) patch for oracle artifact")
                ok, info = self._write_patch_artifact(artifact_patch)
                if not ok:
                    self.compile_succeeded = False
                    self.testcase_succeeded = False
                    self.poc_succeeded = False
                    return (
                        "Failed to persist patch.txt for oracle validation, so oracle could not run. "
                        f"Reason: {info}\n"
                    )
                ret += self._run_oracle()  # type: ignore

            # Fallback path when oracle is disabled; preserve old behavior.
            if not self.oracle_enabled:
                if self.compile_succeeded and not self.testcase_succeeded:
                    ret += self._run_testcase()
                if (
                    self.compile_succeeded
                    and self.testcase_succeeded
                    and not self.poc_succeeded
                ):
                    ret += self._run_poc(patch)
            return ret
        else:
            if "need not ported" in patch:
                self.round_succeeded = True
                return "Patch applied successfully\n"

            ret = self._apply_hunk(
                ref, patch, revise_context=True
            )
            if "CONTEXT MISMATCH" in ret:
                self.context_mismatch_times += 1
            return ret

    def get_tools(self):
        return (
            creat_viewcode_tool(self),
            creat_locate_symbol_tool(self),
            create_validate_tool(self),
            create_git_history_tool(self),
            create_git_show_tool(self),
            create_similar_fix_tool(self),
            create_adjust_config_tool(self),
        )


def creat_locate_symbol_tool(project: Project):
    @tool
    def locate_symbol(ref: str, symbol: str) -> str:
        """
        Locate a symbol in a specific ref of the target repository.
        
        REQUIRED PARAMETERS:
        - ref: The commit hash of the ref to search in (REQUIRED)
        - symbol: The function/struct/variable name to locate (REQUIRED - must not be empty)
        
        Returns locations in format 'file_path:line_number'
        """
        res = project._locate_symbol(ref, symbol)
        if res is not None:
            return "\n".join([f"{file}:{line}" for file, line in res])
        else:
            candidates, best_name = project._locate_similar_symbol(ref, symbol)
            ret = f"The symbol `{symbol}` does not exist in the current ref.\n"
            if not candidates:
                ret += "No similar symbols found.\n"
                return ret
            ret += f"Here are the top {len(candidates)} similar symbols with their signatures:\n\n"
            for i, c in enumerate(candidates, 1):
                ret += f"  {i}. `{c['name']}` — {c['file']}:{c['line']}"
                if c['same_file']:
                    ret += " [SAME FILE]"
                ret += "\n"
                if c['signature']:
                    ret += f"     Signature: {c['signature']}\n"
            ret += "\nPlease compare the signatures and semantics to determine which candidate (if any) is a suitable replacement.\n"
            ret += "Use `viewcode` to inspect the full implementation of a candidate before using it.\n"
            return ret

    return locate_symbol


def creat_viewcode_tool(project: Project):
    @tool
    def viewcode(ref: str, path: str, startline: int, endline: int) -> str:
        """
        View a file from a specific ref of the target repository.
        
        REQUIRED PARAMETERS (all must be provided):
        - ref: The commit hash of the ref to view (REQUIRED)
        - path: File path relative to project root (REQUIRED, e.g., 'arch/x86/kvm/x86.c')
        - startline: Starting line number (REQUIRED, must be >= 1)
        - endline: Ending line number (REQUIRED, must be >= startline)
        
        Returns the content of lines between startline and endline (inclusive).
        """
        return project._viewcode(ref, path, startline, endline)

    return viewcode


def create_validate_tool(project: Project):
    @tool
    def validate(ref: str, patch: str) -> str:
        """
        Validate a patch on a specific ref of the target repository.
        
        REQUIRED PARAMETERS:
        - ref: The commit hash to test the patch on (REQUIRED)
        - patch: The patch content with proper formatting (REQUIRED). Each line must start with '+', '-', or ' ' (space). Use tab indentation. For non-portable hunks, use 'need not ported'.
        
        Returns validation result including compilation and test status.
        """
        return project._validate(ref, patch)

    return validate


def create_adjust_config_tool(project: Project):
    @tool
    def adjust_config(config_updates_json: str) -> str:
        """
        Apply kernel config updates to the runtime config copy while keeping the original kernel.config untouched.

        REQUIRED PARAMETERS:
        - config_updates_json: JSON list (or single object) of {"key": "CONFIG_...", "value": "y|m|n"}

        Returns a short summary of the applied config changes.
        """
        config_updates_json = (config_updates_json or "").strip()
        if not config_updates_json:
            return "config_updates_json is empty"

        try:
            parsed = json.loads(config_updates_json)
        except Exception as e:
            return f"failed to parse config_updates_json: {e}"

        if isinstance(parsed, dict):
            updates = [parsed]
        elif isinstance(parsed, list):
            updates = parsed
        else:
            return "config_updates_json must be a JSON object or array"

        return project._apply_kernel_config_updates(updates)

    return adjust_config


def create_git_history_tool(project: Project):
    @tool
    def git_history() -> str:
        """
        get history for lines which relate to patch hunk.
        """
        return project._git_history()

    return git_history


def create_git_show_tool(project: Project):
    @tool
    def git_show() -> str:
        """
        show change log for a specific ref
        """
        return project._git_show()

    return git_show

def create_similar_fix_tool(project):
    @tool
    def similar_fix_cluster(extid: str, limit: int = 30, focus_error: str = "") -> str:
        """
        Given a syzbot extid, call external similar_fix_cluster.py and return the clustered fix guidance.

        Parameters:
        - extid: syzbot extid (REQUIRED)
        - limit: max similar bugs to inspect (default 30)
        - focus_error: optional compile error / failing symbol for relevance ranking
        """
        extid = (extid or "").strip()
        if not extid:
            return "extid is empty"

        script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "similar_fix_cluster.py")
        )
        stable_repo_dir = project.project_dir
        patch_dataset_dir = project.patch_dataset_dir or ""

        if not os.path.exists(script_path):
            return f"similar_fix_cluster script not found: {script_path}"
        if not os.path.isdir(stable_repo_dir):
            return f"stable_repo_dir not found: {stable_repo_dir}"

        cmd = [
            "python3",
            script_path,
            "--extid", extid,
            "--stable-repo-dir", stable_repo_dir,
            "--patch-dataset-dir", patch_dataset_dir,
            "--limit", str(limit),
        ]

        if focus_error.strip():
            cmd += ["--focus-error", focus_error.strip()]

        logger.debug("similar_fix_cluster cmd: %s", " ".join(cmd))

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60 * 5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "similar_fix_cluster script timed out"

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        if proc.returncode != 0:
            msg = f"similar_fix_cluster script failed with rc={proc.returncode}"
            if stderr:
                msg += f"\nstderr:\n{stderr}"
            return msg

        if not stdout:
            return "similar_fix_cluster script returned empty output"

        return stdout

    return similar_fix_cluster