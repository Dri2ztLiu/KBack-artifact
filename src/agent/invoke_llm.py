import os
import re
import shutil
import time
import json
import subprocess
from pathlib import Path

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.callbacks import FileCallbackHandler
from langchain_openai import ChatOpenAI, AzureChatOpenAI

from agent.prompt import (
    SYSTEM_PROMPT_PLAN,
    USER_PROMPT_PLAN,
    SYSTEM_PROMPT_HUNK_ADAPT,
    USER_PROMPT_HUNK_ADAPT,
    SYSTEM_PROMPT_PATCH_FEEDBACK,
    USER_PROMPT_PATCH_FEEDBACK,
)
from tools.logger import logger
from tools.project import Project
from tools.utils import split_patch, merge_patches_with_single_commit_msg
from typing import Any, Dict, Optional


STAGE_PLAN = "plan"
STAGE_HUNK_ADAPT = "hunk_adapt"
STAGE_PATCH_FEEDBACK = "patch_feedback"
PLAN_DRIFT_LOG_ENV = "BACKPORT_LOG_PLAN_DRIFT"


def _escape_non_placeholder_braces(template: str, allowed_vars: set[str]) -> str:
    """Escape JSON braces for LangChain templates while keeping valid placeholders."""
    escaped = template.replace("{", "{{").replace("}", "}}")
    for var in allowed_vars:
        escaped = escaped.replace("{{" + var + "}}", "{" + var + "}")
    return escaped


def _ckpt_path(data) -> str:
    # 你也可以放到 data.project_dir 下
    return os.path.join(data.patch_dataset_dir, ".backport_ckpt.json")


def load_ckpt(data) -> Optional[Dict[str, Any]]:
    path = _ckpt_path(data)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_ckpt(data, ckpt: Dict[str, Any]) -> None:
    path = _ckpt_path(data)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def clear_ckpt(data) -> None:
    path = _ckpt_path(data)
    if os.path.exists(path):
        os.remove(path)


def invoke_with_retry(agent_executor, payload, callbacks, max_attempts=5, base_sleep=2):
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return agent_executor.invoke(payload, {"callbacks": callbacks})
        except Exception as e:
            last_exc = e
            # 指数退避
            sleep_sec = base_sleep * (2 ** (attempt - 1))
            logger.warning(f"LLM invoke failed (attempt {attempt}/{max_attempts}): {e}")
            if attempt < max_attempts:
                time.sleep(sleep_sec)
    raise last_exc


def _safe_read_text(path: Path, max_chars: int = 20000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return text[:max_chars]
    except Exception:
        return ""


def _ensure_text_file_from_script(
    script_path: Path,
    output_path: Path,
    args: list[str],
) -> None:
    if output_path.exists() and output_path.is_file():
        return
    if not script_path.exists() or not script_path.is_file():
        return
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["python3", str(script_path), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        stdout = (proc.stdout or "").strip()
        if stdout:
            output_path.write_text(stdout + "\n", encoding="utf-8")
        elif proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            if stderr:
                logger.warning(
                    "auto-fetch evidence failed for %s: rc=%s stderr=%s",
                    output_path,
                    proc.returncode,
                    stderr,
                )
    except Exception as e:
        logger.warning("auto-fetch evidence failed: %s", e)


def _load_plan_evidence(data) -> Dict[str, str]:
    root = Path(data.patch_dataset_dir)
    repo_src = Path(__file__).resolve().parent.parent
    bisect_fetcher = repo_src / "bisect_log_fetch.py"
    similar_fetcher = repo_src / "similar_fix_cluster.py"

    bisect_candidates = [
        root / "repro" / "bisect_log.txt",
    ]
    crash_candidates = [
        root / "repro" / "report.txt",
        root / "repro" / "crash_report.txt",
    ]
    similar_candidates = [
        root / "repro" / "similar_crash_patch.txt",
    ]
    similar_json_candidates = [
        root / "repro" / "similar_crash_patch.json",
    ]

    def first_existing(candidates):
        for c in candidates:
            if c.exists() and c.is_file():
                return c
        return None

    bisect_file = first_existing(bisect_candidates)
    crash_file = first_existing(crash_candidates)
    similar_file = first_existing(similar_candidates)
    similar_json_file = first_existing(similar_json_candidates)

    if not bisect_file and getattr(data, "tag", ""):
        _ensure_text_file_from_script(
            bisect_fetcher,
            root / "repro" / "bisect_log.txt",
            ["--extid", str(data.tag), "--patch-dataset-dir", str(data.patch_dataset_dir or "")],
        )
        bisect_file = first_existing(bisect_candidates)

    if (
        (not similar_file or not similar_json_file)
        and getattr(data, "tag", "")
        and getattr(data, "stable_repo_dir", "")
    ):
        _ensure_text_file_from_script(
            similar_fetcher,
            root / "repro" / "similar_crash_patch.txt",
            [
                "--extid",
                str(data.tag),
                "--stable-repo-dir",
                str(data.stable_repo_dir),
                "--patch-dataset-dir",
                str(data.patch_dataset_dir or ""),
                "--limit",
                "30",
            ],
        )
        similar_file = first_existing(similar_candidates)
        similar_json_file = first_existing(similar_json_candidates)

    return {
        "bisect_log": _safe_read_text(bisect_file) if bisect_file else "",
        "crash_report": _safe_read_text(crash_file) if crash_file else "",
        "similar_bug": _safe_read_text(similar_file) if similar_file else "",
    }


def _strip_json_fence(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _json_or_fallback(text: str, fallback: str) -> str:
    cleaned = _strip_json_fence(text)
    if not cleaned:
        return fallback
    try:
        obj = json.loads(cleaned)
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return fallback


def _normalize_patch_text(text: str) -> str:
    if text is None:
        return ""
    patch = str(text)
    if patch and not patch.endswith("\n"):
        patch += "\n"
    return patch


def _parse_patch_feedback_output(output_text: str):
    """Support stage-3 outputs as either unified diff or action JSON.

    JSON shape (optional):
    {
      "action": "revise_patch | adjust_config | both | insufficient",
      "patch": "...optional unified diff...",
      "config_updates": [{"key":"CONFIG_FOO","value":"y|m|n"}],
      "reason": "..."
    }
    """
    cleaned = _strip_json_fence(output_text)
    if not cleaned:
        return "", [], "", ""

    try:
        obj = json.loads(cleaned)
    except Exception:
        return "revise_patch", [], _normalize_patch_text(output_text), ""

    if not isinstance(obj, dict):
        return "revise_patch", [], _normalize_patch_text(output_text), ""

    action = str(obj.get("action", "")).strip()
    reason = str(obj.get("reason", "")).strip()
    patch = str(obj.get("patch", "") or "")
    if patch.strip():
        patch = _normalize_patch_text(patch)
    else:
        patch = ""

    updates_raw = obj.get("config_updates", [])
    updates = updates_raw if isinstance(updates_raw, list) else []
    return action, updates, patch, reason


def _extract_hunk_patch_from_adapt_output(output_text: str, hunk_id: str):
    """Parse stage-2 JSON output and return normalized json plus current hunk candidate."""
    empty_obj = {"adapted_hunks": [], "conflict_hunks": []}
    cleaned = _strip_json_fence(output_text)
    if not cleaned:
        return json.dumps(empty_obj, ensure_ascii=False), "", "", ""

    try:
        obj = json.loads(cleaned)
    except Exception:
        return json.dumps(empty_obj, ensure_ascii=False), "", "", ""

    if not isinstance(obj, dict):
        return json.dumps(empty_obj, ensure_ascii=False), "", "", ""

    adapted = obj.get("adapted_hunks", [])
    conflicts = obj.get("conflict_hunks", [])
    if not isinstance(adapted, list):
        adapted = []
    if not isinstance(conflicts, list):
        conflicts = []

    candidate_patch = ""
    candidate_status = ""
    candidate_reason = ""
    for item in adapted:
        if not isinstance(item, dict):
            continue
        if str(item.get("hunk_id", "")).strip() != hunk_id:
            continue
        candidate_patch = str(item.get("patch", "") or "")
        candidate_status = str(item.get("status", "") or "")
        candidate_reason = str(item.get("reason", "") or "")
        break

    normalized = json.dumps(
        {"adapted_hunks": adapted, "conflict_hunks": conflicts},
        ensure_ascii=False,
    )
    return normalized, candidate_patch, candidate_status, candidate_reason


def _scope_plan_to_hunk(backport_plan_json: str, hunk_id: str) -> str:
    """Keep only current hunk entry to reduce cross-hunk confusion in stage-2."""
    if not backport_plan_json:
        return ""
    try:
        obj = json.loads(backport_plan_json)
    except Exception:
        return backport_plan_json

    if not isinstance(obj, dict):
        return backport_plan_json

    hunk_plan = obj.get("hunk_plan", [])
    if not isinstance(hunk_plan, list):
        return backport_plan_json

    filtered = [
        item
        for item in hunk_plan
        if isinstance(item, dict) and str(item.get("hunk_id", "")).strip() == hunk_id
    ]
    obj["hunk_plan"] = filtered
    return json.dumps(obj, ensure_ascii=False)


def _review_plan_json(plan_json: str) -> None:
    """Log key plan signals before entering repair flow on resume/new run."""
    if not plan_json:
        logger.warning("Plan review: empty plan json")
        return
    try:
        obj = json.loads(plan_json)
        clues = obj.get("repair_clues", {}) if isinstance(obj, dict) else {}
        hunk_plan = obj.get("hunk_plan", []) if isinstance(obj, dict) else []
        bug_type = str(clues.get("bug_type", "unknown"))
        fix_intent = str(clues.get("fix_intent", "unknown"))
        confidence = str(clues.get("confidence_summary", "unknown"))
        logger.info(
            "Plan review: bug_type=%s, confidence=%s, hunk_count=%s",
            bug_type,
            confidence,
            len(hunk_plan) if isinstance(hunk_plan, list) else 0,
        )
        logger.debug("Plan review: fix_intent=%s", fix_intent)
    except Exception as e:
        logger.warning(f"Plan review: invalid json, err={e}")


def _extract_hunk_strategy_map(plan_obj: dict) -> dict:
    hunk_plan = plan_obj.get("hunk_plan", []) if isinstance(plan_obj, dict) else []
    ret = {}
    if not isinstance(hunk_plan, list):
        return ret
    for item in hunk_plan:
        if not isinstance(item, dict):
            continue
        hunk_id = str(item.get("hunk_id", "")).strip()
        strategy = str(item.get("strategy", "")).strip()
        if hunk_id:
            ret[hunk_id] = strategy
    return ret


def _log_plan_drift_summary(initial_plan_json: str, current_plan_json: str) -> None:
    if os.environ.get(PLAN_DRIFT_LOG_ENV, "1") == "0":
        return
    if not initial_plan_json or not current_plan_json:
        logger.info("Plan drift: skipped (missing initial/current plan)")
        return
    try:
        init_obj = json.loads(initial_plan_json)
        curr_obj = json.loads(current_plan_json)
    except Exception as e:
        logger.warning(f"Plan drift: skipped (invalid json), err={e}")
        return

    init_clues = init_obj.get("repair_clues", {}) if isinstance(init_obj, dict) else {}
    curr_clues = curr_obj.get("repair_clues", {}) if isinstance(curr_obj, dict) else {}

    init_bug = str(init_clues.get("bug_type", ""))
    curr_bug = str(curr_clues.get("bug_type", ""))
    init_conf = str(init_clues.get("confidence_summary", ""))
    curr_conf = str(curr_clues.get("confidence_summary", ""))

    init_map = _extract_hunk_strategy_map(init_obj)
    curr_map = _extract_hunk_strategy_map(curr_obj)

    changed = []
    for hid in sorted(set(init_map.keys()) | set(curr_map.keys())):
        if init_map.get(hid, "") != curr_map.get(hid, ""):
            changed.append(f"{hid}:{init_map.get(hid, '-')}>{curr_map.get(hid, '-')}")

    if not changed and init_bug == curr_bug and init_conf == curr_conf:
        logger.info("Plan drift: none")
        return

    logger.warning(
        "Plan drift detected: bug_type_changed=%s confidence_changed=%s hunk_strategy_changes=%s",
        init_bug != curr_bug,
        init_conf != curr_conf,
        len(changed),
    )
    if changed:
        logger.warning("Plan drift details: %s", ", ".join(changed[:12]))


def _agent_used_tool(intermediate_steps: Any, tool_name: str) -> bool:
    if not intermediate_steps:
        return False
    for step in intermediate_steps:
        try:
            action = step[0] if isinstance(step, (list, tuple)) and step else step
            name = str(getattr(action, "tool", getattr(action, "tool_input", "")) or "")
            if name == tool_name:
                return True
        except Exception:
            continue
    return False


def _extract_structured_feedback_json(validation_feedback: str) -> dict:
    """Extract structured oracle feedback JSON from validation feedback text."""
    text = str(validation_feedback or "")
    marker = "Structured oracle feedback (JSON):"
    idx = text.find(marker)
    if idx < 0:
        return {}

    tail = text[idx + len(marker):]
    start = tail.find("{")
    if start < 0:
        return {}

    depth = 0
    end = -1
    for i, ch in enumerate(tail[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return {}

    blob = tail[start : end + 1]
    try:
        obj = json.loads(blob)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _is_prepatch_build_failure(validation_feedback: str) -> bool:
    """True when oracle could not evaluate patched case because before-case build already failed."""
    obj = _extract_structured_feedback_json(validation_feedback)
    if not obj:
        return False
    summary = obj.get("summary", {}) if isinstance(obj.get("summary", {}), dict) else {}
    stages = obj.get("stages", {}) if isinstance(obj.get("stages", {}), dict) else {}

    failure_stage = str(summary.get("failure_stage", "") or summary.get("failure_stage_after", "") or "")
    verdict_before = str(summary.get("verdict_before", "") or "")
    verdict_after = str(summary.get("verdict_after", "") or "")
    kernel_build = stages.get("kernel_build", {}) if isinstance(stages.get("kernel_build", {}), dict) else {}
    kernel_build_status = str(kernel_build.get("status", "") or "")

    # New structured schema no longer carries oracle_after. Use verdict transition as equivalent signal.
    skipped_after = verdict_after == "SKIPPED"
    before_inconclusive = verdict_before == "inconclusive"
    return skipped_after and before_inconclusive and (
        failure_stage == "kernel_build" or kernel_build_status == "failed"
    )


def _build_stage_agent_executor(
    stage: str, project: Project, llm: ChatOpenAI, debug_mode: bool, config_only: bool = False
) -> AgentExecutor:
    viewcode, locate_symbol, validate, git_history, git_show, similar_fix_cluster, adjust_config = (
        project.get_tools()
    )

    if stage == STAGE_PLAN:
        system_prompt, user_prompt = SYSTEM_PROMPT_PLAN, USER_PROMPT_PLAN
        tools = [similar_fix_cluster, locate_symbol, viewcode, git_history, git_show]
        allowed_vars = {
            "project_url",
            "target_release",
            "new_patch_parent",
            "extid",
            "bisect_log",
            "crash_report",
            "similar_bug",
            "new_patch",
        }
    elif stage == STAGE_HUNK_ADAPT:
        system_prompt, user_prompt = SYSTEM_PROMPT_HUNK_ADAPT, USER_PROMPT_HUNK_ADAPT
        tools = [viewcode, locate_symbol, validate, git_history, git_show]
        allowed_vars = {
            "project_url",
            "target_release",
            "new_patch_parent",
            "new_patch",
            "backport_plan_json",
            "current_hunk_id",
            "execution_requirement",
            "hunk_validation_feedback",
        }
    elif stage == STAGE_PATCH_FEEDBACK:
        system_prompt, user_prompt = (
            SYSTEM_PROMPT_PATCH_FEEDBACK,
            USER_PROMPT_PATCH_FEEDBACK,
        )
        tools = [adjust_config] if config_only else [viewcode, locate_symbol, validate, similar_fix_cluster, adjust_config]
        allowed_vars = {
            "project_url",
            "target_release",
            "new_patch_parent",
            "extid",
            "new_patch",
            "backport_plan_json",
            "adapted_hunks_json",
            "complete_patch",
            "validation_feedback",
        }
    else:
        raise ValueError(f"Unknown stage: {stage}")

    system_prompt = _escape_non_placeholder_braces(system_prompt, allowed_vars)
    user_prompt = _escape_non_placeholder_braces(user_prompt, allowed_vars)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("user", user_prompt),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=debug_mode,
        max_iterations=50,
        return_intermediate_steps=True,
    )


def initial_agent(project: Project, data, debug_mode: bool):
    use_azure = data.use_azure

    if use_azure:
        azure_endpoint = data.azure_endpoint
        azure_deployment = data.azure_deployment
        azure_api_version = data.azure_api_version
        api_key = data.openai_key

        logger.info(f"Using Azure OpenAI: {azure_endpoint} (deployment: {azure_deployment})")

        llm = AzureChatOpenAI(
            temperature=1.0,  # Set to 1.0 for GPT-5 model; can be changed if using other models
            azure_deployment=azure_deployment,
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=azure_api_version,
            verbose=True,
        )
    else:
        # Regular OpenAI configuration
        # logger.info("Using OpenAI API")
        # # base_url = "https://api.openai.com/v1"
        # base_url = "https://35.aigcbest.top/v1"  # Custom base URL
        # llm = ChatOpenAI(
        #     temperature=0.5,
        #     model="gpt-4o",
        #     api_key=data.openai_key,
        #     openai_api_base=base_url,
        #     verbose=True,
        # )
        base_url = data.api_url
        api_key = data.api_key
        model = data.model
        print(base_url, api_key, model)
        logger.info(f"Using API: {base_url}")
        llm = ChatOpenAI(
            temperature=0.5,
            model=model,
            api_key=api_key,
            openai_api_base=base_url,
            verbose=True,
        )

    # Keep return signature unchanged: default executor is hunk-adapt stage.
    agent_executor = _build_stage_agent_executor(
        STAGE_HUNK_ADAPT, project, llm, debug_mode
    )
    return agent_executor, llm


def do_backport(
    agent_executor: AgentExecutor, project: Project, data, llm: ChatOpenAI, logfile: str
):
    log_handler = FileCallbackHandler(logfile)

    patch = project._get_patch(data.new_patch)
    pps = list(split_patch(patch, True))

    # Stage executors with stage-scoped tool sets.
    plan_executor = _build_stage_agent_executor(STAGE_PLAN, project, llm, False)
    feedback_executor = _build_stage_agent_executor(STAGE_PATCH_FEEDBACK, project, llm, True)
    feedback_config_only_executor = _build_stage_agent_executor(
        STAGE_PATCH_FEEDBACK, project, llm, True, config_only=True
    )

    # ====== 热启动：加载 checkpoint ======
    ckpt = load_ckpt(data)
    resume_idx = 0
    succeeded_hunks = []
    initial_plan_json = ""
    backport_plan_json = ""
    adapted_hunks_json = json.dumps({"adapted_hunks": [], "conflict_hunks": []}, ensure_ascii=False)
    adapted_hunks_records = []

    if ckpt:
        # 防串任务：匹配关键信息
        if ckpt.get("target_release") == str(data.target_release) and ckpt.get("new_patch_parent") == str(data.new_patch_parent):
            resume_idx = int(ckpt.get("resume_idx", 0))
            # Backward compatibility: older ckpt may use `success_chunks`.
            succeeded_hunks = ckpt.get("succeeded_hunks", ckpt.get("success_chunks", [])) or []
            initial_plan_json = ckpt.get("initial_plan_json", ckpt.get("backport_plan_json", "")) or ""
            backport_plan_json = ckpt.get("backport_plan_json", "") or initial_plan_json
            adapted_hunks_json = ckpt.get("adapted_hunks_json", adapted_hunks_json)
            try:
                adapted_hunks_records = json.loads(adapted_hunks_json).get("adapted_hunks", []) or []
            except Exception:
                adapted_hunks_records = []
            # Rewrite ckpt into canonical schema so next resume is deterministic.
            save_ckpt(
                data,
                {
                    "target_release": str(data.target_release),
                    "new_patch_parent": str(data.new_patch_parent),
                    "resume_idx": resume_idx,
                    "succeeded_hunks": succeeded_hunks,
                    "initial_plan_json": initial_plan_json,
                    "backport_plan_json": backport_plan_json,
                    "adapted_hunks_json": adapted_hunks_json,
                },
            )
            logger.info(f"Resume from checkpoint: resume_idx={resume_idx}, succeeded={len(succeeded_hunks)}")
        else:
            logger.warning("Checkpoint does not match current task. Ignoring it.")
            ckpt = None

    # ====== Stage 1: generate plan ======
    if not backport_plan_json:
        evidence = _load_plan_evidence(data)
        plan_payload = {
            "project_url": str(data.project_url or ""),
            "target_release": str(data.target_release or ""),
            "new_patch_parent": str(data.new_patch_parent or ""),
            "extid": str(data.tag or ""),
            "bisect_log": evidence["bisect_log"],
            "crash_report": evidence["crash_report"],
            "similar_bug": evidence["similar_bug"],
            "new_patch": str(patch or ""),
        }
        logger.info("Stage 1/3: generating backport plan")
        try:
            plan_resp = invoke_with_retry(
                plan_executor,
                plan_payload,
                [log_handler],
                max_attempts=5,
            )
            plan_output = plan_resp.get("output", "") if isinstance(plan_resp, dict) else ""
            backport_plan_json = _json_or_fallback(
                plan_output,
                json.dumps(
                    {
                        "repair_clues": {
                            "bug_type": "unknown",
                            "fix_intent": "unknown",
                            "primary_subsystems": [],
                            "primary_files": [],
                            "primary_symbols": [],
                            "supporting_patterns": [],
                            "confidence_summary": "low",
                        },
                        "hunk_plan": [],
                        "backport_risks": ["plan parse failed"],
                        "recommended_next_actions": ["continue with conservative adaptation"],
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as e:
            logger.error(f"Stage 1 plan generation failed: {e}")
            backport_plan_json = json.dumps(
                {
                    "repair_clues": {
                        "bug_type": "unknown",
                        "fix_intent": "unknown",
                        "primary_subsystems": [],
                        "primary_files": [],
                        "primary_symbols": [],
                        "supporting_patterns": [],
                        "confidence_summary": "low",
                    },
                    "hunk_plan": [],
                    "backport_risks": ["plan stage failed"],
                    "recommended_next_actions": ["continue with conservative adaptation"],
                },
                ensure_ascii=False,
            )

        initial_plan_json = backport_plan_json

        save_ckpt(
            data,
            {
                "target_release": str(data.target_release),
                "new_patch_parent": str(data.new_patch_parent),
                "resume_idx": resume_idx,
                "succeeded_hunks": succeeded_hunks,
                "initial_plan_json": initial_plan_json,
                "backport_plan_json": backport_plan_json,
                "adapted_hunks_json": adapted_hunks_json,
                "last_status": "plan_ready",
            },
        )

    # Always review plan before entering stage-2 repair loop.
    _review_plan_json(initial_plan_json or backport_plan_json)
    _log_plan_drift_summary(initial_plan_json or backport_plan_json, backport_plan_json)

    # ====== 如果有已成功 hunks：先把它们重新 apply 恢复工作区 ======
    if succeeded_hunks:
        project.repo.git.reset("--hard")
        project.repo.git.clean("-fdx")

        for i, h in enumerate(succeeded_hunks):
            project.round_succeeded = False
            ret = project._apply_hunk(data.target_release, h, False)
            if not project.round_succeeded:
                logger.error(f"Failed to re-apply checkpoint hunk {i}. Restart from scratch.\nret={ret}")
                clear_ckpt(data)
                resume_idx = 0
                succeeded_hunks = []
                break

        project.succeeded_patches = list(succeeded_hunks)
        logger.debug(data)

    # ====== 主循环：从 resume_idx 开始 ======
    for idx in range(resume_idx, len(pps)):
        logger.info(f"Stage 2/3: adapting hunk {idx + 1}/{len(pps)}")
        pp = pps[idx]
        project.round_succeeded = False
        project.context_mismatch_times = 0
        project._recent_validate_patches.clear()
        project._consecutive_dup_count = 0
        # Snapshot succeeded_patches length so we only keep one new entry per hunk
        _sp_snapshot_len = len(project.succeeded_patches)

        ret = project._apply_hunk(data.target_release, pp, False)
        if project.round_succeeded:
            logger.debug(f"Hunk {idx} can be applied without any conflicts")
            # _apply_hunk already appended to succeeded_patches; trim to only keep the last one added
            project.succeeded_patches = project.succeeded_patches[:_sp_snapshot_len + 1]
            succeeded_hunks = list(project.succeeded_patches)

            save_ckpt(data, {
                "target_release": str(data.target_release),
                "new_patch_parent": str(data.new_patch_parent),
                "resume_idx": idx + 1,
                "succeeded_hunks": succeeded_hunks,
                "initial_plan_json": initial_plan_json,
                "backport_plan_json": backport_plan_json,
                "adapted_hunks_json": json.dumps({"adapted_hunks": adapted_hunks_records, "conflict_hunks": []}, ensure_ascii=False),
                "last_status": "hunk_applied",
                "last_hunk": idx,
            })
            continue

        # 需要 LLM 修复
        logger.debug(f"Hunk {idx} can not be applied, using LLM to generate a fix")
        project.now_hunk = pp
        project.now_hunk_num = idx

        payload = {
            "project_url": data.project_url,
            "new_patch_parent": data.new_patch_parent,
            "new_patch": pp,
            "target_release": data.target_release,
            "backport_plan_json": _scope_plan_to_hunk(backport_plan_json, f"H{idx + 1}"),
            "current_hunk_id": f"H{idx + 1}",
            "execution_requirement": (
                f"Focus only on H{idx + 1}. Return exactly one adapted_hunks item for H{idx + 1}. "
                "Provide a concrete unified-diff hunk patch whenever feasible. "
                "If conflict is unavoidable, explain briefly and keep unrelated hunks out."
            ),
            "hunk_validation_feedback": ret,
            "extid": data.tag,
        }
        for k, v in list(payload.items()):
            payload[k] = "" if (v is None or v is False) else str(v)

        adapt_output = ""
        try:
            # 🔥 关键：重试
            adapt_resp = invoke_with_retry(
                agent_executor, payload, [log_handler], max_attempts=5
            )
            if isinstance(adapt_resp, dict):
                adapt_output = str(adapt_resp.get("output", "") or "")
        except Exception as e:
            # 🔥 关键：失败也落盘，方便下次续跑
            success_chunks = list(project.succeeded_patches) if getattr(project, "succeeded_patches", None) else list(succeeded_hunks)
            save_ckpt(data, {
                "target_release": str(data.target_release),
                "new_patch_parent": str(data.new_patch_parent),
                "resume_idx": idx,  # 下次从当前 hunk 继续
                "succeeded_hunks": success_chunks,
                "initial_plan_json": initial_plan_json,
                "backport_plan_json": backport_plan_json,
                "adapted_hunks_json": json.dumps({"adapted_hunks": adapted_hunks_records, "conflict_hunks": []}, ensure_ascii=False),
                "last_status": "llm_failed",
                "last_hunk": idx,
                "error": repr(e),
                # 可选：把失败 chunk 也存下来便于排查/续跑
                "failed_chunk": pp,
            })
            logger.error(f"LLM failed for hunk {idx}, checkpoint saved. error={e}")
            return

        # Parse stage-2 json output and try to apply current hunk candidate when needed.
        hunk_id = f"H{idx + 1}"
        (
            parsed_adapted_hunks_json,
            candidate_patch,
            candidate_status,
            candidate_reason,
        ) = _extract_hunk_patch_from_adapt_output(adapt_output, hunk_id)
        adapted_hunks_json = parsed_adapted_hunks_json
        try:
            adapted_hunks_records = (
                json.loads(adapted_hunks_json).get("adapted_hunks", []) or []
            )
        except Exception:
            pass

        if not project.round_succeeded and candidate_patch:
            logger.debug(f"Applying stage-2 candidate patch for {hunk_id}")
            apply_ret = project._apply_hunk(data.target_release, candidate_patch, False)
            # Feed the newest apply/validate feedback back into strict retry.
            if apply_ret:
                payload["hunk_validation_feedback"] = apply_ret

        # Hard fallback: if the model returned no patch for current hunk, ask once with stricter requirement.
        if not project.round_succeeded and not candidate_patch:
            strict_payload = dict(payload)
            strict_payload["execution_requirement"] = (
                f"HARD REQUIREMENT: Output exactly one adapted_hunks item for {hunk_id}, "
                "and patch must be a non-empty unified diff hunk for current upstream hunk. "
                "Do not output other hunk IDs. Try validate before concluding conflict if feasible."
            )
            try:
                strict_resp = invoke_with_retry(
                    agent_executor,
                    strict_payload,
                    [log_handler],
                    max_attempts=2,
                )
                strict_output = ""
                if isinstance(strict_resp, dict):
                    strict_output = str(strict_resp.get("output", "") or "")
                (
                    strict_adapt_json,
                    strict_patch,
                    strict_status,
                    strict_reason,
                ) = _extract_hunk_patch_from_adapt_output(strict_output, hunk_id)
                if strict_adapt_json:
                    adapted_hunks_json = strict_adapt_json
                    try:
                        adapted_hunks_records = (
                            json.loads(adapted_hunks_json).get("adapted_hunks", []) or []
                        )
                    except Exception:
                        pass
                if strict_patch:
                    logger.debug(f"Applying strict stage-2 candidate patch for {hunk_id}")
                    project._apply_hunk(data.target_release, strict_patch, False)
                elif strict_status == "discarded":
                    logger.debug(f"{hunk_id} discarded after strict stage-2 retry: {strict_reason}")
                    project.round_succeeded = True
            except Exception as e:
                logger.warning(f"Strict stage-2 retry failed for {hunk_id}: {e}")

        if not project.round_succeeded and candidate_status == "discarded":
            logger.debug(f"{hunk_id} discarded by plan/adaptation: {candidate_reason}")
            project.round_succeeded = True

        # Conflict recovery: if model returned "conflict" with no patch, give one more
        # attempt with explicit guidance that new-code hunks should be inserted directly.
        if not project.round_succeeded and candidate_status == "conflict":
            conflict_payload = dict(payload)
            conflict_reason_str = candidate_reason or ""
            conflict_payload["execution_requirement"] = (
                f"CONFLICT RECOVERY for {hunk_id}. The previous attempt returned conflict "
                f"with reason: {conflict_reason_str}\n\n"
                "IMPORTANT: If this upstream hunk INTRODUCES new definitions (macros, helpers, "
                "static functions, struct fields), those symbols are expected to be absent from "
                "the target branch — the hunk's purpose IS to add them. In that case, the hunk "
                "is NOT a missing-API conflict. You should:\n"
                "1. Use `viewcode` to find the correct INSERTION POINT in the target file "
                "(look for the surrounding context lines from the upstream hunk).\n"
                "2. Adapt only the context lines to match the target branch.\n"
                "3. Output a concrete unified-diff patch that inserts the new code.\n\n"
                "If the hunk truly cannot be adapted (e.g., it modifies code that was completely "
                "removed in the target branch), you may return conflict again, but you MUST first "
                "attempt at least one concrete patch and call `validate` to verify."
            )
            conflict_payload["hunk_validation_feedback"] = (
                payload.get("hunk_validation_feedback", "") +
                "\n[Conflict recovery round] Previous attempt returned conflict without trying a patch. "
                "Please attempt a concrete patch this time."
            )
            try:
                logger.debug(f"Conflict recovery retry for {hunk_id}")
                conflict_resp = invoke_with_retry(
                    agent_executor,
                    conflict_payload,
                    [log_handler],
                    max_attempts=3,
                )
                conflict_output = ""
                if isinstance(conflict_resp, dict):
                    conflict_output = str(conflict_resp.get("output", "") or "")
                (
                    conflict_adapt_json,
                    conflict_patch,
                    conflict_new_status,
                    conflict_new_reason,
                ) = _extract_hunk_patch_from_adapt_output(conflict_output, hunk_id)
                if conflict_adapt_json:
                    adapted_hunks_json = conflict_adapt_json
                    try:
                        adapted_hunks_records = (
                            json.loads(adapted_hunks_json).get("adapted_hunks", []) or []
                        )
                    except Exception:
                        pass
                if conflict_patch:
                    logger.debug(f"Applying conflict-recovery patch for {hunk_id}")
                    project._apply_hunk(data.target_release, conflict_patch, False)
                elif conflict_new_status == "discarded":
                    logger.debug(f"{hunk_id} discarded after conflict recovery: {conflict_new_reason}")
                    project.round_succeeded = True
                elif conflict_new_status == "conflict":
                    logger.debug(f"{hunk_id} still conflict after recovery attempt: {conflict_new_reason}")
            except Exception as e:
                logger.warning(f"Conflict recovery retry failed for {hunk_id}: {e}")

        if not project.round_succeeded:
            success_chunks = list(project.succeeded_patches) if getattr(project, "succeeded_patches", None) else list(succeeded_hunks)
            save_ckpt(data, {
                "target_release": str(data.target_release),
                "new_patch_parent": str(data.new_patch_parent),
                "resume_idx": idx,
                "succeeded_hunks": success_chunks,
                "initial_plan_json": initial_plan_json,
                "backport_plan_json": backport_plan_json,
                "adapted_hunks_json": json.dumps({"adapted_hunks": adapted_hunks_records, "conflict_hunks": []}, ensure_ascii=False),
                "last_status": "max_iterations_or_unsolved",
                "last_hunk": idx,
                "failed_chunk": pp,
            })
            logger.error(f"Reach max_iterations or unsolved for hunk {idx}, checkpoint saved.")
            return

        # Record stage-2 output for stage-3 context.
        adapted_hunks_records.append(
            {
                "hunk_id": hunk_id,
                "status": "adapted",
                "reason": "applied and validated by stage-2 loop",
                "patch": project.succeeded_patches[-1] if project.succeeded_patches else "",
            }
        )

        # 如果 LLM 成功了，Project 内部应已把修复后的 patch 记入 succeeded_patches
        # Trim to snapshot + 1 so we only keep one entry for the current hunk
        project.succeeded_patches = project.succeeded_patches[:_sp_snapshot_len + 1]
        succeeded_hunks = list(project.succeeded_patches)
        adapted_hunks_json = json.dumps(
            {"adapted_hunks": adapted_hunks_records, "conflict_hunks": []},
            ensure_ascii=False,
        )
        save_ckpt(data, {
            "target_release": str(data.target_release),
            "new_patch_parent": str(data.new_patch_parent),
            "resume_idx": idx + 1,
            "succeeded_hunks": succeeded_hunks,
            "initial_plan_json": initial_plan_json,
            "backport_plan_json": backport_plan_json,
            "adapted_hunks_json": adapted_hunks_json,
            "last_status": "hunk_fixed_by_llm",
            "last_hunk": idx,
        })

    # 全部 hunks 结束，清 checkpoint
    # clear_ckpt(data)

    # ====== 下面保持你原来的逻辑不变（组装 complete_patch / validate / 二阶段 agent 等） ======
    project.all_hunks_applied_succeeded = True
    logger.info(f"Aplly all hunks in the patch      PASS")

    project.now_hunk = "completed"
    complete_patch = _normalize_patch_text(
        merge_patches_with_single_commit_msg(project.succeeded_patches)
    )
    logger.info(f"Successfully applied all hunks: {project.succeeded_patches}")
    project.repo.git.clean("-fdx")
    # for file in os.listdir(data.patch_dataset_dir):
    #     if os.path.exists(f"{data.project_dir}{file}"):
    #         os.remove(f"{data.project_dir}{file}")
    #     shutil.copy2(f"{data.patch_dataset_dir}{file}", f"{data.project_dir}{file}")
    for name in os.listdir(data.patch_dataset_dir):
        src = os.path.join(data.patch_dataset_dir, name)
        dst = os.path.join(data.project_dir, name)

        if os.path.exists(dst):
            if os.path.isfile(dst) or os.path.islink(dst):
                os.remove(dst)
            elif os.path.isdir(dst):
                shutil.rmtree(dst)

        if os.path.isfile(src):
            shutil.copy2(src, dst)
        elif os.path.isdir(src):
            shutil.copytree(src, dst)
    project.context_mismatch_times = 0
    project._recent_validate_patches.clear()
    project._consecutive_dup_count = 0
    validate_ret = project._validate(data.target_release, complete_patch)
    logger.info("Complete Patch: %s", complete_patch)
    if project.poc_succeeded:
        logger.info(
            f"Successfully backport the patch to the target release {data.target_release}"
        )
        logger.info("Complete Patch: %s", complete_patch)
        artifact_patch = getattr(project, '_last_revised_patch', None) or complete_patch
        _patch_path = data.patch_dataset_dir + "patch.txt"
        _patch_tmp = _patch_path + ".tmp"
        with open(_patch_tmp, "w", encoding="utf-8") as f:
            f.write(_normalize_patch_text(artifact_patch))
        os.replace(_patch_tmp, _patch_path)
        return

    # ====== Stage 3: patch-level validation feedback loop ======
    logger.info("Stage 3/3: patch-level feedback loop")
    current_patch = complete_patch
    current_feedback = validate_ret
    previous_patch_normalized = _normalize_patch_text(current_patch) if current_patch else ""
    consecutive_compile_failures = 0 if project.compile_succeeded else 1
    model_upgraded = False
    upgrade_threshold = getattr(data, "model_upgrade_threshold", 2)
    fallback_model = getattr(data, "fallback_model", "gpt-5")
    for _ in range(5):
        project._recent_validate_patches.clear()
        project._consecutive_dup_count = 0

        # Auto-upgrade model after N consecutive compile failures
        if not model_upgraded and consecutive_compile_failures >= upgrade_threshold and fallback_model:
            logger.warning(
                "Stage 3: %d consecutive compile failures with model %s, upgrading to %s",
                consecutive_compile_failures, data.model, fallback_model,
            )
            upgraded_llm = ChatOpenAI(
                temperature=0.5,
                model=fallback_model,
                api_key=data.api_key,
                openai_api_base=data.api_url,
                verbose=True,
            )
            feedback_executor = _build_stage_agent_executor(
                STAGE_PATCH_FEEDBACK, project, upgraded_llm, True
            )
            feedback_config_only_executor = _build_stage_agent_executor(
                STAGE_PATCH_FEEDBACK, project, upgraded_llm, True, config_only=True
            )
            model_upgraded = True
        feedback_payload = {
            "project_url": str(data.project_url or ""),
            "new_patch_parent": str(data.new_patch_parent or ""),
            "target_release": str(data.target_release or ""),
            "new_patch": str(patch or ""),
            "backport_plan_json": backport_plan_json,
            "adapted_hunks_json": adapted_hunks_json,
            "complete_patch": str(current_patch or ""),
            "validation_feedback": str(current_feedback or ""),
            "extid": str(data.tag or ""),
        }
        prepatch_build_failed = _is_prepatch_build_failure(current_feedback)
        chosen_feedback_executor = (
            feedback_config_only_executor if prepatch_build_failed else feedback_executor
        )
        if prepatch_build_failed:
            logger.info(
                "Stage 3 detected before-case kernel_build failure (verdict_after=SKIPPED); "
                "switching to config-only feedback mode"
            )
        try:
            feedback_resp = invoke_with_retry(
                chosen_feedback_executor,
                feedback_payload,
                [log_handler],
                max_attempts=3,
            )
        except Exception as e:
            logger.error(f"Stage 3 feedback invoke failed: {e}")
            break

        candidate = ""
        action = ""
        config_updates = []
        action_reason = ""
        config_tool_used = False
        if isinstance(feedback_resp, dict):
            raw_candidate = str(feedback_resp.get("output", "") or "")
            config_tool_used = _agent_used_tool(feedback_resp.get("intermediate_steps", []), "adjust_config")
            if raw_candidate.strip():
                action, config_updates, parsed_patch, action_reason = _parse_patch_feedback_output(raw_candidate)
                if parsed_patch:
                    candidate = parsed_patch
                elif action in {"adjust_config", "both", "insufficient"}:
                    candidate = ""
                elif config_tool_used:
                    candidate = ""
                else:
                    candidate = _normalize_patch_text(raw_candidate)

        if config_updates:
            cfg_ret = project._apply_kernel_config_updates(config_updates)
            logger.info("Stage 3 config action: %s", cfg_ret)
            if candidate:
                current_patch = candidate
                logger.info("Stage 3 config action also keeps patch revision for current round")
            project.compile_succeeded = False
            project.testcase_succeeded = False
            project.poc_succeeded = False
            current_feedback = project._validate(data.target_release, current_patch)
            if action_reason:
                current_feedback = f"[Config action reason] {action_reason}\n" + current_feedback
            if project.compile_succeeded:
                consecutive_compile_failures = 0
            else:
                consecutive_compile_failures += 1
            if project.poc_succeeded:
                complete_patch = current_patch
                break
            continue

        if config_tool_used:
            logger.info("Stage 3 config tool action detected; re-running validation after runtime config update")
            project.compile_succeeded = False
            project.testcase_succeeded = False
            project.poc_succeeded = False
            current_feedback = project._validate(data.target_release, current_patch)
            if project.compile_succeeded:
                consecutive_compile_failures = 0
            else:
                consecutive_compile_failures += 1
            if project.poc_succeeded:
                complete_patch = current_patch
                break
            continue

        if not candidate:
            break

        # Detect duplicate patch submission — skip expensive validation
        candidate_normalized = _normalize_patch_text(candidate)
        if candidate_normalized and candidate_normalized == previous_patch_normalized:
            logger.warning("Stage 3: LLM submitted identical patch as previous round, injecting viewcode hint")
            current_feedback = (
                "WARNING: You submitted the EXACT SAME patch as your previous attempt. "
                "This patch has the same compilation errors. Simply re-submitting will not fix it.\n"
                "MANDATORY next steps:\n"
                "1. Use `viewcode` to read the ACTUAL source file at the error locations listed above.\n"
                "2. Identify exactly what the compiler sees (e.g., duplicate declarations, missing signatures).\n"
                "3. Only then produce a DIFFERENT revised patch.\n"
                "Previous feedback for reference:\n" + str(current_feedback)
            )
            continue
        previous_patch_normalized = candidate_normalized

        current_patch = candidate
        apply_precheck_feedback = project._precheck_complete_patch_apply(
            data.target_release,
            current_patch,
            True if project.context_mismatch_times >= 1 else False,
        )
        if "passed" not in apply_precheck_feedback.lower():
            logger.info("Stage 3 precheck: patch apply failed, skip compile/oracle this round")
            current_feedback = apply_precheck_feedback
            continue

        # Re-run full validation for revised complete patch.
        project.compile_succeeded = False
        project.testcase_succeeded = False
        project.poc_succeeded = False
        current_feedback = project._validate(data.target_release, current_patch)
        if project.compile_succeeded:
            consecutive_compile_failures = 0
        else:
            consecutive_compile_failures += 1
        if project.poc_succeeded:
            complete_patch = current_patch
            break

    if project.poc_succeeded:
        logger.info(
            f"Successfully backport the patch to the target release {data.target_release}"
        )
        _patch_path = data.patch_dataset_dir + "patch.txt"
        _patch_tmp = _patch_path + ".tmp"
        with open(_patch_tmp, "w", encoding="utf-8") as f:
            f.write(_normalize_patch_text(complete_patch))
        os.replace(_patch_tmp, _patch_path)
            
    else:
        logger.error(
            f"Failed backport the patch to the target release {data.target_release}"
        )
