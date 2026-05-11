#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOM'
Usage: run_oracle.sh
  --repo PATH
  --target-ref REF
  [--use-worktree]
  [--apply-patch PATCH.txt]
  [--pre-built-bzimage PATH]
  --sig-re PATH
  [--repro-syz PATH]
  [--repro-c PATH]
  --kernel-config PATH
  --qemu-img PATH
  --qemu-ssh-key PATH
  --root-dir PATH
  [--jobs N]
  [--qemu-ram SIZE]
  [--qemu-smp N]
  [--base-ssh-port N]
  [--port-scan-range N]
  [--qemu-max-tries N]
  [--kcmdline-extra STRING]
  [--repro-iters N]

Notes:
- At least one of --repro-c or --repro-syz must be provided.
- If both are provided, run C repro first, then syz repro.
- syz repro requires `syz-execprog` and `syz-executor` in guest PATH.

Exit code:
  0  : PASS (signature NOT hit)
  1  : FAIL (signature hit)
  2  : USAGE / missing args
  125: INCONCLUSIVE (build/boot/ssh/scp/repro/patch apply issues)
EOM
}

die() { echo "[!] $*" >&2; exit 2; }

log() {
  if [[ -n "${WORK_DIR:-}" ]]; then
    echo "[*] $*" >> "$WORK_DIR/oracle.meta.log"
  fi
}

REPO=""
TARGET_REF=""
SIG_RE=""
REPRO_SYZ=""
REPRO_C=""
KERNEL_CONFIG=""
QEMU_IMG=""
QEMU_SSH_KEY=""
ROOT_DIR=""

USE_WORKTREE=0
APPLY_PATCH=""
PRE_BUILT_BZIMAGE=""
JOBS="$(nproc)"
QEMU_RAM="2G"
QEMU_SMP="2"
BASE_SSH_PORT="13200"
PORT_SCAN_RANGE="2000"
QEMU_MAX_TRIES="8"
KCMDLINE_EXTRA="net.ifnames=0 biosdevname=0"
REPRO_ITERS="10"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="$2"
      shift 2
      ;;
    --target-ref)
      TARGET_REF="$2"
      shift 2
      ;;
    --use-worktree)
      USE_WORKTREE=1
      shift
      ;;
    --apply-patch)
      APPLY_PATCH="$2"
      shift 2
      ;;
    --pre-built-bzimage)
      PRE_BUILT_BZIMAGE="$2"
      shift 2
      ;;
    --sig-re)
      SIG_RE="$2"
      shift 2
      ;;
    --repro-syz)
      REPRO_SYZ="$2"
      shift 2
      ;;
    --repro-c)
      REPRO_C="$2"
      shift 2
      ;;
    --kernel-config)
      KERNEL_CONFIG="$2"
      shift 2
      ;;
    --qemu-img)
      QEMU_IMG="$2"
      shift 2
      ;;
    --qemu-ssh-key)
      QEMU_SSH_KEY="$2"
      shift 2
      ;;
    --root-dir)
      ROOT_DIR="$2"
      shift 2
      ;;
    --jobs)
      JOBS="$2"
      shift 2
      ;;
    --qemu-ram)
      QEMU_RAM="$2"
      shift 2
      ;;
    --qemu-smp)
      QEMU_SMP="$2"
      shift 2
      ;;
    --base-ssh-port)
      BASE_SSH_PORT="$2"
      shift 2
      ;;
    --port-scan-range)
      PORT_SCAN_RANGE="$2"
      shift 2
      ;;
    --qemu-max-tries)
      QEMU_MAX_TRIES="$2"
      shift 2
      ;;
    --kcmdline-extra)
      KCMDLINE_EXTRA="$2"
      shift 2
      ;;
    --repro-iters)
      REPRO_ITERS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 2
      ;;
    *)
      die "unknown arg $1"
      ;;
  esac
done

[[ -n "$REPO" ]] || die "missing --repo"
[[ -n "$TARGET_REF" ]] || die "missing --target-ref"
[[ -n "$SIG_RE" ]] || die "missing --sig-re"
[[ -n "$KERNEL_CONFIG" ]] || die "missing --kernel-config"
[[ -n "$QEMU_IMG" ]] || die "missing --qemu-img"
[[ -n "$QEMU_SSH_KEY" ]] || die "missing --qemu-ssh-key"
[[ -n "$ROOT_DIR" ]] || die "missing --root-dir"
[[ "$REPRO_ITERS" =~ ^[0-9]+$ ]] || die "--repro-iters must be a non-negative integer"

[[ -f "$SIG_RE" ]] || die "sig-re not found: $SIG_RE"
[[ -f "$KERNEL_CONFIG" ]] || die "kernel-config not found: $KERNEL_CONFIG"
[[ -f "$QEMU_IMG" ]] || die "qemu-img not found: $QEMU_IMG"
[[ -f "$QEMU_SSH_KEY" ]] || die "qemu-ssh-key not found: $QEMU_SSH_KEY"

if [[ -z "$REPRO_C" && -z "$REPRO_SYZ" ]]; then
  die "at least one of --repro-c or --repro-syz must be provided"
fi

if [[ -n "$REPRO_C" && ! -f "$REPRO_C" ]]; then
  die "repro-c not found: $REPRO_C"
fi
if [[ -n "$REPRO_SYZ" && ! -f "$REPRO_SYZ" ]]; then
  die "repro-syz not found: $REPRO_SYZ"
fi

if [[ -n "${APPLY_PATCH:-}" && "$USE_WORKTREE" -ne 1 ]]; then
  die "--apply-patch requires --use-worktree (to avoid dirtying main repo)"
fi
if [[ -n "${APPLY_PATCH:-}" && ! -f "$APPLY_PATCH" ]]; then
  die "patch not found: $APPLY_PATCH"
fi
if [[ -n "${PRE_BUILT_BZIMAGE:-}" && ! -f "$PRE_BUILT_BZIMAGE" ]]; then
  die "pre-built bzimage not found: $PRE_BUILT_BZIMAGE"
fi

WORK_DIR="$ROOT_DIR/run_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "$WORK_DIR"
: > "$WORK_DIR/oracle.meta.log"

STAGE_STATUS_FILE="$WORK_DIR/stage_status.json"
PATCH_APPLY_LOG="$WORK_DIR/patch_apply.log"
BUILD_LOG="$WORK_DIR/build.log"
BUILD_FOCUS_LOG="$WORK_DIR/build.focus.log"
QEMU_CONSOLE_LOG="$WORK_DIR/qemu-console.log"
RUN_LOG="$WORK_DIR/run.log"
USERSPACE_LOG="$WORK_DIR/userspace.log"
ORACLE_META_LOG="$WORK_DIR/oracle.meta.log"

STAGE_PATCH_APPLY_STATUS="skipped"
STAGE_BUILD_STATUS="pending"
STAGE_QEMU_BOOT_STATUS="pending"
STAGE_REPRO_STATUS="pending"
FAILURE_STAGE=""
FAILURE_REASON=""

REASON_GIT_APPLY_FAILED="git_apply_failed"
REASON_KERNEL_BUILD_FAILED="kernel_build_failed"
REASON_QEMU_SSH_NOT_READY="qemu_ssh_not_ready"
REASON_QEMU_USERSPACE_NOT_REACHED="qemu_userspace_not_reached"
REASON_REPRO_SCP_FAILED="repro_scp_failed"
REASON_REPRO_RUNTIME_MISSING="repro_runtime_missing"
REASON_REPRO_EXEC_FAILED="repro_exec_failed"
REASON_SIGNATURE_HIT="signature_hit"

write_stage_status() {
  local overall_exit_code="$1"
  local overall_result="$2"
  cat >"$STAGE_STATUS_FILE" <<EOF
{
  "work_dir": "$WORK_DIR",
  "overall": {
    "exit_code": $overall_exit_code,
    "result": "$overall_result",
    "failure_stage": "$FAILURE_STAGE",
    "failure_reason": "$FAILURE_REASON"
  },
  "stages": {
    "patch_apply": {
      "status": "$STAGE_PATCH_APPLY_STATUS",
      "log": "$PATCH_APPLY_LOG"
    },
    "kernel_build": {
      "status": "$STAGE_BUILD_STATUS",
      "log": "$BUILD_LOG",
      "focus_log": "$BUILD_FOCUS_LOG"
    },
    "qemu_boot": {
      "status": "$STAGE_QEMU_BOOT_STATUS",
      "log": "$QEMU_CONSOLE_LOG"
    },
    "reproduce": {
      "status": "$STAGE_REPRO_STATUS",
      "log": "$RUN_LOG",
      "userspace_log": "$USERSPACE_LOG"
    }
  },
  "logs": {
    "oracle_meta": "$ORACLE_META_LOG"
  }
}
EOF
}

extract_build_focus() {
  : > "$BUILD_FOCUS_LOG"

  local pattern='error:|fatal error:|undefined reference|collect2:|ld:|No rule to make target|missing separator|错误'
  local first_line=""

  {
    echo "===== Build Failure Focus ====="
    echo "source_log=$BUILD_LOG"
    echo
    echo "[primary_error_matches]"
    grep -nE "$pattern" "$BUILD_LOG" | head -n 80 || true
    echo
  } >> "$BUILD_FOCUS_LOG"

  first_line="$(grep -nE "$pattern" "$BUILD_LOG" | head -n 1 | cut -d: -f1 || true)"
  if [[ -n "$first_line" ]]; then
    local start=$((first_line > 80 ? first_line - 80 : 1))
    local end=$((first_line + 140))
    {
      echo "[first_root_error_context lines ${start}-${end}]"
      sed -n "${start},${end}p" "$BUILD_LOG"
    } >> "$BUILD_FOCUS_LOG"
  else
    {
      echo "[fallback_make_failures]"
      grep -nE 'make(\[[0-9]+\])?: \*\*\*|Compilation[[:space:]]+FAILED|error:|fatal error:|错误' "$BUILD_LOG" | head -n 160 || true
    } >> "$BUILD_FOCUS_LOG"
  fi
}

SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
-o GlobalKnownHostsFile=/dev/null -o PasswordAuthentication=no \
-o ConnectTimeout=3 -o ServerAliveInterval=5 -o ServerAliveCountMax=3 \
-o LogLevel=ERROR -o RequestTTY=no"

WORKTREE_DIR=""
CURRENT_PIDFILE=""

setup_worktree() {
  WORKTREE_DIR="$WORK_DIR/src"
  log "creating git worktree: $WORKTREE_DIR ($TARGET_REF)"
  git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1 || die "not a git repo: $REPO"
  git -C "$REPO" fetch --all --tags >/dev/null 2>&1 || true
  git -C "$REPO" worktree prune >/dev/null 2>&1 || true
  git -C "$REPO" worktree add -f "$WORKTREE_DIR" "$TARGET_REF" || die "failed to create worktree"
}

cleanup_worktree() {
  if [[ -n "${WORKTREE_DIR:-}" && -d "$WORKTREE_DIR" ]]; then
    log "removing git worktree: $WORKTREE_DIR"
    git -C "$REPO" worktree remove -f "$WORKTREE_DIR" >/dev/null 2>&1 || true
  fi
}

apply_patch_if_needed() {
  local src="$1"
  [[ -n "${APPLY_PATCH:-}" ]] || { STAGE_PATCH_APPLY_STATUS="skipped"; return 0; }

  log "applying patch: $APPLY_PATCH"
  : > "$PATCH_APPLY_LOG"

  if ! git -C "$src" apply --index "$APPLY_PATCH" >>"$PATCH_APPLY_LOG" 2>&1; then
    STAGE_PATCH_APPLY_STATUS="failed"
    FAILURE_STAGE="patch_apply"
    FAILURE_REASON="$REASON_GIT_APPLY_FAILED"
    echo "INCONCLUSIVE: patch apply failed (see $PATCH_APPLY_LOG)"
    return 125
  fi

  STAGE_PATCH_APPLY_STATUS="passed"

  return 0
}

stop_qemu() {
  local pidfile="$1"
  [[ -f "$pidfile" ]] || return 0

  local pid=""
  pid="$(cat "$pidfile" 2>/dev/null || true)"

  if [[ -z "${pid:-}" ]]; then
    rm -f "$pidfile" >/dev/null 2>&1 || true
    return 0
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    for _ in {1..40}; do
      kill -0 "$pid" >/dev/null 2>&1 || break
      sleep 0.1
    done
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi

  rm -f "$pidfile" >/dev/null 2>&1 || true
}

cleanup() {
  set +e
  if [[ -n "${CURRENT_PIDFILE:-}" ]]; then
    stop_qemu "$CURRENT_PIDFILE" || true
  fi
  cleanup_worktree || true
  set -e
}
trap cleanup EXIT INT TERM

pick_free_port() {
  for ((i=0;i<PORT_SCAN_RANGE;i++)); do
    p=$((BASE_SSH_PORT + RANDOM % 200 + i))
    ss -ltn | grep -q ":$p " || { echo "$p"; return; }
  done
  return 1
}

build_kernel() {
  local out="$WORK_DIR/out"
  mkdir -p "$out"
  local src="${WORKTREE_DIR:-$REPO}"

  : > "$BUILD_LOG"
  cp "$KERNEL_CONFIG" "$out/.config"

  {
    echo "[*] build kernel with:"
    echo "    CC=${CC:-gcc}"
    echo "    HOSTCC=${HOSTCC:-gcc}"
    echo "    CXX=${CXX:-g++}"
    echo "    HOSTCXX=${HOSTCXX:-g++}"
    echo "    JOBS=$JOBS"
    echo "    SRC=$src"
    echo "    OUT=$out"
  } >>"$BUILD_LOG"

  make -C "$src" O="$out" \
    CC="${CC:-gcc}" \
    HOSTCC="${HOSTCC:-gcc}" \
    CXX="${CXX:-g++}" \
    HOSTCXX="${HOSTCXX:-g++}" \
    olddefconfig >>"$BUILD_LOG" 2>&1 || true

  if make -C "$src" O="$out" \
    CC="${CC:-gcc}" \
    HOSTCC="${HOSTCC:-gcc}" \
    CXX="${CXX:-g++}" \
    HOSTCXX="${HOSTCXX:-g++}" \
    -j"$JOBS" bzImage >>"$BUILD_LOG" 2>&1; then
    STAGE_BUILD_STATUS="passed"
    echo "$out/arch/x86/boot/bzImage"
    return 0
  fi

  STAGE_BUILD_STATUS="failed"
  extract_build_focus
  echo "[!] first build failed, trying config fix..." >>"$BUILD_LOG"

  return 1
}

wait_ssh_ready() {
  local ssh_port="$1"
  for _ in {1..120}; do
    if ssh -T -p "$ssh_port" -i "$QEMU_SSH_KEY" $SSH_OPTS root@localhost "echo ok" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

USPACE_MARKER_RE='(Welcome to .*Debian GNU/Linux|systemd\[1\]: Started|systemd\[1\]: Reached target|login:|Debian GNU/Linux.*ttyS0)'

extract_userspace_log() {
  local log="$1"
  local out="$2"

  local line
  line="$(grep -nE "$USPACE_MARKER_RE" "$log" | head -n 1 | cut -d: -f1 || true)"
  if [[ -z "$line" ]]; then
    return 1
  fi
  tail -n +"$line" "$log" > "$out"
  return 0
}

signature_hit() {
  local log="$WORK_DIR/userspace.log"
  [[ -f "$log" ]] || return 1
  grep -Eai -f "$SIG_RE" "$log" >/dev/null 2>&1
}

log "WORK_DIR=$WORK_DIR"

if [[ -n "${PRE_BUILT_BZIMAGE:-}" && -z "${APPLY_PATCH:-}" ]]; then
  log "skipping source setup (pre-built bzimage, no patch)"
else
  if [[ "$USE_WORKTREE" -eq 1 ]]; then
    setup_worktree
  else
    log "checkout in-place: $TARGET_REF"
    git -C "$REPO" checkout -f "$TARGET_REF" >/dev/null 2>&1 || die "checkout failed"
  fi
fi

SRC_DIR="${WORKTREE_DIR:-$REPO}"

set +e
apply_patch_if_needed "$SRC_DIR"
patch_rc=$?
set -e
if [[ $patch_rc -ne 0 ]]; then
  STAGE_BUILD_STATUS="skipped"
  STAGE_QEMU_BOOT_STATUS="skipped"
  STAGE_REPRO_STATUS="skipped"
  write_stage_status 125 "INCONCLUSIVE"
  exit 125
fi

bz=""
if [[ -n "${PRE_BUILT_BZIMAGE:-}" ]]; then
  log "using pre-built bzimage: $PRE_BUILT_BZIMAGE"
  bz="$PRE_BUILT_BZIMAGE"
  STAGE_BUILD_STATUS="passed"
  echo "[*] skipped build, using pre-built bzimage: $PRE_BUILT_BZIMAGE" >>"$BUILD_LOG"
else
  bz="$(build_kernel)" || {
    FAILURE_STAGE="kernel_build"
    FAILURE_REASON="$REASON_KERNEL_BUILD_FAILED"
    STAGE_QEMU_BOOT_STATUS="skipped"
    STAGE_REPRO_STATUS="skipped"
    echo "INCONCLUSIVE: build failed (see $BUILD_LOG)" >&2
    write_stage_status 125 "INCONCLUSIVE"
    exit 125
  }
fi

pidfile="/tmp/qemu-oracle-$$.pid"
CURRENT_PIDFILE="$pidfile"

ssh_port="$(pick_free_port)" || exit 125

: > "$QEMU_CONSOLE_LOG"
: > "$RUN_LOG"

{
  echo "[*] repro iterations: $REPRO_ITERS"
  echo "[*] has repro.c: $([[ -n "$REPRO_C" ]] && echo yes || echo no)"
  echo "[*] has repro.syz: $([[ -n "$REPRO_SYZ" ]] && echo yes || echo no)"
} >>"$RUN_LOG"

qemu-system-x86_64 \
  -m "$QEMU_RAM" -smp "$QEMU_SMP" -enable-kvm \
  -kernel "$bz" \
  -append "root=/dev/vda console=ttyS0 rootwait ${KCMDLINE_EXTRA}" \
  -drive file="$QEMU_IMG",if=virtio,snapshot=on \
  -net user,hostfwd=tcp:127.0.0.1:${ssh_port}-:22 \
  -net nic,model=virtio \
  -serial "file:${QEMU_CONSOLE_LOG}" \
  -daemonize -pidfile "$pidfile" -display none

QEMU_CMD=(
  qemu-system-x86_64
  -m "$QEMU_RAM"
  -smp "$QEMU_SMP"
  "${QEMU_ACCEL[@]}"
  -kernel "$bz"
  -append "root=/dev/vda console=ttyS0 rootwait ${KCMDLINE_EXTRA}"
  -drive "file=$QEMU_IMG,if=virtio,snapshot=on"
  -net "user,hostfwd=tcp:127.0.0.1:${ssh_port}-:22"
  -net "nic,model=virtio"
  -serial "file:${QEMU_CONSOLE_LOG}"
  -daemonize
  -pidfile "$pidfile"
  -display none
)

{
  printf '[*] qemu cmd:'
  printf ' %q' "${QEMU_CMD[@]}"
  printf '\n'
} >> "$WORK_DIR/oracle.meta.log"

if ! wait_ssh_ready "$ssh_port"; then
  STAGE_QEMU_BOOT_STATUS="failed"
  STAGE_REPRO_STATUS="skipped"
  FAILURE_STAGE="qemu_boot"
  FAILURE_REASON="$REASON_QEMU_SSH_NOT_READY"
  echo "INCONCLUSIVE: ssh not ready (see $QEMU_CONSOLE_LOG)" >&2
  stop_qemu "$pidfile" || true
  CURRENT_PIDFILE=""
  if [[ -f "$QEMU_CONSOLE_LOG" ]]; then
    extract_userspace_log "$QEMU_CONSOLE_LOG" "$USERSPACE_LOG" || true
  fi
  write_stage_status 125 "INCONCLUSIVE"
  exit 125
fi
STAGE_QEMU_BOOT_STATUS="passed"

set +e
if [[ -n "$REPRO_C" ]]; then
  scp -P "$ssh_port" -i "$QEMU_SSH_KEY" $SSH_OPTS "$REPRO_C" root@localhost:/root/c.c >/dev/null 2>&1
  scp_c_rc=$?
else
  scp_c_rc=0
fi

if [[ -n "$REPRO_SYZ" ]]; then
  scp -P "$ssh_port" -i "$QEMU_SSH_KEY" $SSH_OPTS "$REPRO_SYZ" root@localhost:/root/repro.syz >/dev/null 2>&1
  scp_syz_rc=$?
else
  scp_syz_rc=0
fi
set -e

if [[ $scp_c_rc -ne 0 || $scp_syz_rc -ne 0 ]]; then
  STAGE_REPRO_STATUS="failed"
  FAILURE_STAGE="reproduce"
  FAILURE_REASON="$REASON_REPRO_SCP_FAILED"
  echo "INCONCLUSIVE: scp failed (see $RUN_LOG)" >&2
  stop_qemu "$pidfile" || true
  CURRENT_PIDFILE=""
  write_stage_status 125 "INCONCLUSIVE"
  exit 125
fi

HAS_REPRO_C=0
HAS_REPRO_SYZ=0
[[ -n "$REPRO_C" ]] && HAS_REPRO_C=1
[[ -n "$REPRO_SYZ" ]] && HAS_REPRO_SYZ=1

set +e
ssh -p "$ssh_port" -i "$QEMU_SSH_KEY" $SSH_OPTS root@localhost \
  "REPRO_ITERS=$REPRO_ITERS HAS_REPRO_C=$HAS_REPRO_C HAS_REPRO_SYZ=$HAS_REPRO_SYZ bash -s" >>"$RUN_LOG" 2>&1 <<'EOSSH'
set -eu

if [ "$HAS_REPRO_C" -eq 1 ]; then
  gcc /root/c.c -O2 -pthread -o /root/c
  i=1
  while [ "$i" -le "$REPRO_ITERS" ]; do
    echo "[*] running C repro iteration $i/$REPRO_ITERS"
    timeout 60 /root/c
    rc=$?
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ]; then
      echo "[!] C repro failed at iteration $i (exit code $rc)"
      break
    fi
    i=$((i + 1))
  done
fi

if [ "$HAS_REPRO_SYZ" -eq 1 ]; then
  if ! command -v syz-execprog >/dev/null 2>&1; then
    echo "[!] syz-execprog not found in guest PATH"
    exit 125
  fi
  if ! command -v syz-executor >/dev/null 2>&1; then
    echo "[!] syz-executor not found in guest PATH"
    exit 125
  fi

  SYZ_EXEC="$(command -v syz-execprog)"
  SYZ_EXECUTOR="$(command -v syz-executor)"

  if [ ! -f /root/repro.syz ]; then
    echo "[!] /root/repro.syz not found"
    exit 125
  fi
  sed -i 's/\r$//' /root/repro.syz
  sed -i '1s/^\xEF\xBB\xBF//' /root/repro.syz
  grep -v '^[[:space:]]*#' /root/repro.syz > /root/prog.syz

  i=1
  while [ "$i" -le "$REPRO_ITERS" ]; do
    echo "[*] running syz repro iteration $i/$REPRO_ITERS"
    timeout 60 "$SYZ_EXEC" -executor="$SYZ_EXECUTOR" /root/prog.syz
    rc=$?
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ]; then
      echo "[!] syz repro failed at iteration $i (exit code $rc)"
      exit 1
    fi
    i=$((i + 1))
  done
fi
EOSSH
guest_rc=$?
set -e

stop_qemu "$pidfile"
CURRENT_PIDFILE=""

QEMU_LOG="$QEMU_CONSOLE_LOG"

if [[ -f "$QEMU_LOG" ]]; then
  extract_userspace_log "$QEMU_LOG" "$USERSPACE_LOG" || true
fi

if [[ ! -s "$USERSPACE_LOG" ]]; then
  STAGE_REPRO_STATUS="failed"
  FAILURE_STAGE="qemu_boot"
  FAILURE_REASON="$REASON_QEMU_USERSPACE_NOT_REACHED"
  echo "INCONCLUSIVE: userspace not reached (see $QEMU_CONSOLE_LOG)" >&2
  write_stage_status 125 "INCONCLUSIVE"
  exit 125
fi

if [[ $guest_rc -eq 125 ]]; then
  STAGE_REPRO_STATUS="failed"
  FAILURE_STAGE="reproduce"
  FAILURE_REASON="$REASON_REPRO_RUNTIME_MISSING"
  echo "INCONCLUSIVE: guest syzkaller runtime not available (see $RUN_LOG)" >&2
  write_stage_status 125 "INCONCLUSIVE"
  exit 125
fi

if [[ $guest_rc -ne 0 ]]; then
  STAGE_REPRO_STATUS="failed"
  FAILURE_STAGE="reproduce"
  FAILURE_REASON="$REASON_REPRO_EXEC_FAILED"
  echo "INCONCLUSIVE: guest repro execution failed (see $RUN_LOG)" >&2
  write_stage_status 125 "INCONCLUSIVE"
  exit 125
fi
STAGE_REPRO_STATUS="passed"

if signature_hit; then
  FAILURE_STAGE="reproduce"
  FAILURE_REASON="$REASON_SIGNATURE_HIT"
  write_stage_status 1 "FAILED"
  echo "FAIL: signature hit. work_dir=$WORK_DIR"
  exit 1
fi

write_stage_status 0 "PASS"
echo "PASS: no signature hit. work_dir=$WORK_DIR"
exit 0