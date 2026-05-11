#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: run_oracle_compare_patch.sh CONFIG_YML

Example:
bash run_oracle_compare_patch.sh \
  /path/to/patch_dataset_dir/linux_stable_5.15/2d6fd444c6491140f297/config.yml

Exit code:
  0   : FIXED
  1   : FAILED
  2   : USAGE / missing args
  125 : INCONCLUSIVE
EOF
}

die() { echo "[!] $*" >&2; exit 2; }

log() {
  if [[ -n "${COMPARE_LOG:-}" ]]; then
    echo "[*] $*" >> "$COMPARE_LOG"
  fi
}

REPO=""
BASE_REF=""
PATCH_FILE=""
ROOT_DIR=""
DETECT_SCRIPT=""
CCACHE_DIR="${HOME}/.ccache"
USE_WORKTREE=1
ORACLE_ARGS=()

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORACLE_RUNNER="${SCRIPT_DIR}/run_oracle.sh"
if [[ -z "${ROOT_DIR}" ]]; then
  ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)/oracle_runs"
fi
if [[ -z "${DETECT_SCRIPT}" ]]; then
  DETECT_SCRIPT="${SCRIPT_DIR}/detect_crash.py"
fi

yaml_get() {
  local yaml_file="$1"
  local key="$2"
  python3 - "$yaml_file" "$key" <<'PY'
import sys

yaml_file = sys.argv[1]
key = sys.argv[2]
val = ""

with open(yaml_file, "r", encoding="utf-8") as f:
    for line in f:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if ":" not in s:
            continue
        k, v = s.split(":", 1)
        if k.strip() == key:
            val = v.strip()
            break

print(val)
PY
}

[[ $# -eq 1 ]] || { usage; exit 2; }

CONFIG_FILE="$1"
[[ -f "$CONFIG_FILE" ]] || die "config not found: $CONFIG_FILE"

REPO="$(yaml_get "$CONFIG_FILE" project_dir)"
BASE_REF="$(yaml_get "$CONFIG_FILE" target_release)"
PATCH_DATASET_DIR="$(yaml_get "$CONFIG_FILE" patch_dataset_dir)"

[[ -n "$REPO" ]] || die "missing project_dir in $CONFIG_FILE"
[[ -n "$BASE_REF" ]] || die "missing target_release in $CONFIG_FILE"
[[ -n "$PATCH_DATASET_DIR" ]] || die "missing patch_dataset_dir in $CONFIG_FILE"

PATCH_DATASET_DIR="${PATCH_DATASET_DIR%/}"
PATCH_FILE="${PATCH_DATASET_DIR}/patch.txt"

REPRO_SYZ="${PATCH_DATASET_DIR}/repro/repro.syz"
REPRO_C="${PATCH_DATASET_DIR}/repro/repro.c"
KERNEL_CONFIG="${PATCH_DATASET_DIR}/repro/kernel.config"
KERNEL_CONFIG_RUNTIME="${PATCH_DATASET_DIR}/repro/kernel.config.runtime"
SIG_RE="${SCRIPT_DIR}/signature.re"
QEMU_IMG="/home/lcj/stretch-img/bullseye.img"
QEMU_SSH_KEY="/home/lcj/stretch-img/bullseye.id_rsa"

if [[ -f "$KERNEL_CONFIG_RUNTIME" ]]; then
  KERNEL_CONFIG="$KERNEL_CONFIG_RUNTIME"
fi

[[ -n "$REPO" ]] || die "missing repo"
[[ -n "$BASE_REF" ]] || die "missing base ref"
[[ -n "$PATCH_FILE" ]] || die "missing patch path"
[[ -n "$ROOT_DIR" ]] || die "missing root dir"
[[ -f "$PATCH_FILE" ]] || die "patch not found: $PATCH_FILE"
[[ -f "$DETECT_SCRIPT" ]] || die "detect script not found: $DETECT_SCRIPT"
[[ -f "$ORACLE_RUNNER" ]] || die "oracle runner not found: $ORACLE_RUNNER"
[[ -f "$KERNEL_CONFIG" ]] || die "kernel.config not found: $KERNEL_CONFIG"
[[ -f "$SIG_RE" ]] || die "sig-re not found: $SIG_RE"
[[ -f "$QEMU_IMG" ]] || die "qemu image not found: $QEMU_IMG"
[[ -f "$QEMU_SSH_KEY" ]] || die "qemu ssh key not found: $QEMU_SSH_KEY"

if [[ -f "$REPRO_C" ]]; then
  :
else
  REPRO_C=""
fi

if [[ -f "$REPRO_SYZ" ]]; then
  :
else
  REPRO_SYZ=""
fi

if [[ -z "$REPRO_C" && -z "$REPRO_SYZ" ]]; then
  die "both repro.c and repro.syz are missing under ${PATCH_DATASET_DIR}/repro"
fi

mkdir -p "$ROOT_DIR"
mkdir -p "$CCACHE_DIR"

if ! command -v ccache >/dev/null 2>&1; then
  die "ccache not found in PATH"
fi

export CCACHE_DIR
export CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-20G}"
export CCACHE_COMPRESS="${CCACHE_COMPRESS:-1}"
export CCACHE_COMPILERCHECK="${CCACHE_COMPILERCHECK:-content}"
export CC="ccache gcc"
export CXX="ccache g++"
export HOSTCC="ccache gcc"
export HOSTCXX="ccache g++"

ORACLE_ARGS+=("--sig-re" "$SIG_RE")
if [[ -n "$REPRO_SYZ" ]]; then
  ORACLE_ARGS+=("--repro-syz" "$REPRO_SYZ")
fi
if [[ -n "$REPRO_C" ]]; then
  ORACLE_ARGS+=("--repro-c" "$REPRO_C")
fi
ORACLE_ARGS+=("--kernel-config" "$KERNEL_CONFIG")
ORACLE_ARGS+=("--qemu-img" "$QEMU_IMG")
ORACLE_ARGS+=("--qemu-ssh-key" "$QEMU_SSH_KEY")

BASE_DIR="${ROOT_DIR}/compare_patch_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "$BASE_DIR"

COMPARE_LOG="${BASE_DIR}/compare.log"
: > "$COMPARE_LOG"

ccache -z >/dev/null 2>&1 || true

find_run_dir() {
  local label="$1"
  local stage_dir="${BASE_DIR}/${label}"

  if [[ ! -d "$stage_dir" ]]; then
    return 0
  fi

  find "$stage_dir" -mindepth 1 -maxdepth 1 -type d -name 'run_*' | sort | tail -n 1
}

emit_stage_summary_kv() {
  local label="$1"
  local run_dir=""
  local stage_json=""

  run_dir="$(find_run_dir "$label")"
  if [[ -z "${run_dir:-}" || ! -d "$run_dir" ]]; then
    return 0
  fi

  stage_json="${run_dir}/stage_status.json"
  if [[ ! -f "$stage_json" ]]; then
    return 0
  fi

  python3 - "$label" "$stage_json" <<'PY'
import json
import sys

label = sys.argv[1]
path = sys.argv[2]
try:
    data = json.load(open(path, "r", encoding="utf-8"))
except Exception:
    sys.exit(0)

overall = data.get("overall", {}) if isinstance(data, dict) else {}
stages = data.get("stages", {}) if isinstance(data, dict) else {}

def out(k, v):
    print(f"{label}_{k}={v}")

out("run_dir", data.get("work_dir", ""))
out("failure_stage", overall.get("failure_stage", ""))
out("failure_reason", overall.get("failure_reason", ""))
out("result", overall.get("result", ""))
out("exit_code", overall.get("exit_code", ""))

for stage_key in ["patch_apply", "kernel_build", "qemu_boot", "reproduce"]:
    st = stages.get(stage_key, {}) if isinstance(stages, dict) else {}
    out(f"{stage_key}_status", st.get("status", ""))
    out(f"{stage_key}_log", st.get("log", ""))
    out(f"{stage_key}_focus_log", st.get("focus_log", ""))
    if stage_key == "reproduce":
        out("reproduce_userspace_log", st.get("userspace_log", ""))
PY
}

run_one() {
  local label="$1"
  local patch="$2"
  local outdir="${BASE_DIR}/${label}"
  mkdir -p "$outdir"

  local stage_log="${outdir}/oracle.stdout_stderr.log"
  : > "$stage_log"

  local -a cmd
  cmd=(
    bash "$ORACLE_RUNNER"
    --repo "$REPO"
    --target-ref "$BASE_REF"
    --root-dir "$outdir"
    "${ORACLE_ARGS[@]}"
  )

  if [[ "$USE_WORKTREE" -eq 1 ]]; then
    cmd+=(--use-worktree)
  fi

  if [[ -n "$patch" ]]; then
    cmd+=(--apply-patch "$patch")
  fi

  {
    echo "===== [${label}] START $(date -Is) patch=${patch:-<none>} ====="
    echo "[*] cmd: ${cmd[*]}"
  } >> "$stage_log"

  set +e
  (
    "${cmd[@]}"
  ) >>"$stage_log" 2>&1
  local rc=$?
  set -e

  {
    echo "===== [${label}] END $(date -Is) rc=${rc} ====="
    echo
  } >> "$stage_log"

  cat "$stage_log" >> "$COMPARE_LOG"
  echo "$rc" > "${outdir}/oracle_exit_code"
}

detect_one() {
  local label="$1"
  local outdir="${BASE_DIR}/${label}"
  local detect_log="${outdir}/detect.stdout_stderr.log"
  local run_dir=""
  local log_file=""

  : > "$detect_log"

  run_dir="$(find_run_dir "$label")"

  if [[ -z "${run_dir:-}" || ! -d "$run_dir" ]]; then
    echo "missing run_* dir under $outdir" >> "$detect_log"
    cat "$detect_log" >> "$COMPARE_LOG"
    echo "125" > "${outdir}/detect_exit_code"
    echo "inconclusive" > "${outdir}/detect_verdict"
    return 0
  fi

  log_file="${run_dir}/userspace.log"

  if [[ ! -f "$log_file" ]]; then
    echo "missing userspace.log: $log_file" >> "$detect_log"
    cat "$detect_log" >> "$COMPARE_LOG"
    echo "125" > "${outdir}/detect_exit_code"
    echo "inconclusive" > "${outdir}/detect_verdict"
    return 0
  fi

  {
    echo "[*] detect log file: $log_file"
  } >> "$detect_log"

  set +e
  python3 "$DETECT_SCRIPT" "$log_file" >>"$detect_log" 2>&1
  local rc=$?
  set -e

  echo "$rc" > "${outdir}/detect_exit_code"

  if [[ "$rc" -eq 1 ]]; then
    echo "crash" > "${outdir}/detect_verdict"
  elif [[ "$rc" -eq 0 ]]; then
    echo "clean" > "${outdir}/detect_verdict"
  else
    echo "inconclusive" > "${outdir}/detect_verdict"
  fi

  cat "$detect_log" >> "$COMPARE_LOG"
}

append_userspace() {
  local label="$1"
  local run_dir=""
  local log_file=""

  run_dir="$(find_run_dir "$label")"
  log_file="${run_dir}/userspace.log"

  echo "===== [${label}] USERSPACE LOG =====" >> "$LLM_EVIDENCE"
  if [[ -n "${run_dir:-}" && -f "$log_file" ]]; then
    cat "$log_file" >> "$LLM_EVIDENCE"
  else
    echo "<missing userspace.log>" >> "$LLM_EVIDENCE"
  fi
  echo >> "$LLM_EVIDENCE"
}

append_stage_logs() {
  local label="$1"
  local run_dir=""
  run_dir="$(find_run_dir "$label")"

  echo "===== [${label}] STAGE LOG POINTERS =====" >> "$LLM_EVIDENCE"
  if [[ -z "${run_dir:-}" || ! -d "$run_dir" ]]; then
    echo "<missing run dir>" >> "$LLM_EVIDENCE"
    echo >> "$LLM_EVIDENCE"
    return 0
  fi

  local f
  for f in stage_status.json patch_apply.log build.log build.focus.log qemu-console.log run.log userspace.log oracle.meta.log; do
    local p="${run_dir}/${f}"
    if [[ -f "$p" ]]; then
      echo "$f=$p" >> "$LLM_EVIDENCE"
    fi
  done
  echo >> "$LLM_EVIDENCE"

  if [[ -f "${run_dir}/build.focus.log" ]]; then
    echo "===== [${label}] build.focus.log =====" >> "$LLM_EVIDENCE"
    cat "${run_dir}/build.focus.log" >> "$LLM_EVIDENCE"
    echo >> "$LLM_EVIDENCE"
  fi

  for f in patch_apply.log build.log qemu-console.log run.log; do
    local p="${run_dir}/${f}"
    if [[ -f "$p" ]]; then
      echo "===== [${label}] ${f} (tail) =====" >> "$LLM_EVIDENCE"
      tail -n 160 "$p" >> "$LLM_EVIDENCE"
      echo >> "$LLM_EVIDENCE"
    fi
  done
}

ORACLE_RC_BEFORE=""
ORACLE_RC_AFTER="SKIPPED"
DETECT_RC_BEFORE=""
DETECT_RC_AFTER="SKIPPED"
VERDICT_BEFORE=""
VERDICT_AFTER="SKIPPED"

FINAL_RESULT="FAILED"
FINAL_EXIT=1

BEFORE_CACHE_DIR="${PATCH_DATASET_DIR}/repro/before_cache"
BEFORE_BZIMAGE_CACHE="${BEFORE_CACHE_DIR}/bzImage"
BEFORE_BZIMAGE_REF="${BEFORE_CACHE_DIR}/base_ref"
BEFORE_BZIMAGE_CFG_MD5="${BEFORE_CACHE_DIR}/config_md5"

_current_cfg_md5="$(md5sum "$KERNEL_CONFIG" 2>/dev/null | awk '{print $1}')"

CACHED_BZIMAGE=""
if [[ -f "$BEFORE_BZIMAGE_CACHE" && -f "$BEFORE_BZIMAGE_REF" && -f "$BEFORE_BZIMAGE_CFG_MD5" ]]; then
  _cached_ref="$(cat "$BEFORE_BZIMAGE_REF")"
  _cached_md5="$(cat "$BEFORE_BZIMAGE_CFG_MD5")"
  if [[ "$_cached_ref" == "$BASE_REF" && "$_cached_md5" == "$_current_cfg_md5" ]]; then
    CACHED_BZIMAGE="$BEFORE_BZIMAGE_CACHE"
    log "before bzImage cache HIT (ref=$BASE_REF)"
  else
    log "before bzImage cache MISS (ref mismatch or config changed)"
  fi
else
  log "before bzImage cache MISS (no cache files)"
fi

if [[ -n "$CACHED_BZIMAGE" ]]; then
  run_one_with_bzimage() {
    local label="$1"
    local patch="$2"
    local bzimage="$3"
    local outdir="${BASE_DIR}/${label}"
    mkdir -p "$outdir"

    local stage_log="${outdir}/oracle.stdout_stderr.log"
    : > "$stage_log"

    local -a cmd
    cmd=(
      bash "$ORACLE_RUNNER"
      --repo "$REPO"
      --target-ref "$BASE_REF"
      --root-dir "$outdir"
      --pre-built-bzimage "$bzimage"
      "${ORACLE_ARGS[@]}"
    )

    if [[ "$USE_WORKTREE" -eq 1 ]]; then
      cmd+=(--use-worktree)
    fi

    if [[ -n "$patch" ]]; then
      cmd+=(--apply-patch "$patch")
    fi

    {
      echo "===== [${label}] START $(date -Is) patch=${patch:-<none>} bzimage=${bzimage} ====="
      echo "[*] cmd: ${cmd[*]}"
    } >> "$stage_log"

    set +e
    (
      "${cmd[@]}"
    ) >>"$stage_log" 2>&1
    local rc=$?
    set -e

    {
      echo "===== [${label}] END $(date -Is) rc=${rc} ====="
      echo
    } >> "$stage_log"

    cat "$stage_log" >> "$COMPARE_LOG"
    echo "$rc" > "${outdir}/oracle_exit_code"
  }

  run_one_with_bzimage before "" "$CACHED_BZIMAGE"
else
  run_one before ""
fi
detect_one before

if [[ -z "$CACHED_BZIMAGE" ]]; then
  _before_run_dir="$(find_run_dir before)"
  if [[ -n "${_before_run_dir:-}" ]]; then
    _before_bz="${_before_run_dir}/out/arch/x86/boot/bzImage"
    if [[ -f "$_before_bz" ]]; then
      mkdir -p "$BEFORE_CACHE_DIR"
      cp "$_before_bz" "$BEFORE_BZIMAGE_CACHE"
      echo "$BASE_REF" > "$BEFORE_BZIMAGE_REF"
      echo "$_current_cfg_md5" > "$BEFORE_BZIMAGE_CFG_MD5"
      log "before bzImage cached to $BEFORE_BZIMAGE_CACHE"
    fi
  fi
fi

ORACLE_RC_BEFORE="$(cat "${BASE_DIR}/before/oracle_exit_code")"
DETECT_RC_BEFORE="$(cat "${BASE_DIR}/before/detect_exit_code")"
VERDICT_BEFORE="$(cat "${BASE_DIR}/before/detect_verdict")"

if [[ "$VERDICT_BEFORE" == "inconclusive" ]]; then
  FINAL_RESULT="INCONCLUSIVE"
  FINAL_EXIT=125
elif [[ "$VERDICT_BEFORE" != "crash" ]]; then
  FINAL_RESULT="FAILED"
  FINAL_EXIT=1
else
  run_one after "$PATCH_FILE"
  detect_one after

  ORACLE_RC_AFTER="$(cat "${BASE_DIR}/after/oracle_exit_code")"
  DETECT_RC_AFTER="$(cat "${BASE_DIR}/after/detect_exit_code")"
  VERDICT_AFTER="$(cat "${BASE_DIR}/after/detect_verdict")"

  if [[ "$VERDICT_AFTER" == "inconclusive" ]]; then
    FINAL_RESULT="INCONCLUSIVE"
    FINAL_EXIT=125
  elif [[ "$VERDICT_AFTER" == "clean" ]]; then
    FINAL_RESULT="FIXED"
    FINAL_EXIT=0
  else
    FINAL_RESULT="FAILED"
    FINAL_EXIT=1
  fi
fi

{
  echo "oracle_before=$ORACLE_RC_BEFORE oracle_after=$ORACLE_RC_AFTER"
  echo "detect_before=$DETECT_RC_BEFORE detect_after=$DETECT_RC_AFTER"
  echo "verdict_before=$VERDICT_BEFORE verdict_after=$VERDICT_AFTER"
  emit_stage_summary_kv before
  emit_stage_summary_kv after
  echo "RESULT=$FINAL_RESULT"
  echo
  echo "===== ccache stats ====="
  ccache -s 2>/dev/null || true
} > "${BASE_DIR}/summary.txt"

cat "${BASE_DIR}/summary.txt" >> "$COMPARE_LOG"

LLM_EVIDENCE="${BASE_DIR}/llm_evidence.txt"
: > "$LLM_EVIDENCE"

append_userspace before
append_stage_logs before
if [[ -d "${BASE_DIR}/after" ]]; then
  append_userspace after
  append_stage_logs after
fi

for _stage_dir in "${BASE_DIR}/before" "${BASE_DIR}/after"; do
  if [[ -d "$_stage_dir" ]]; then
    find "$_stage_dir" -maxdepth 2 -type d -name "out" -exec rm -rf {} + 2>/dev/null || true
  fi
done
log "Cleaned up out/ directories under ${BASE_DIR}"

echo "RESULT=$FINAL_RESULT"
exit "$FINAL_EXIT"