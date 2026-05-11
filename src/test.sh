#!/usr/bin/env bash
set -euo pipefail

USPACE_MARKER_RE='syzkaller login: '
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BEFORE_WORK_DIR="${BEFORE_WORK_DIR:-}"
AFTER_WORK_DIR="${AFTER_WORK_DIR:-}"
SIG_RE="${SIG_RE:-${REPO_ROOT}/src/signature.re}"

if [[ -z "$BEFORE_WORK_DIR" || -z "$AFTER_WORK_DIR" ]]; then
  echo "Please set BEFORE_WORK_DIR and AFTER_WORK_DIR before running this script." >&2
  exit 2
fi

extract_userspace_log() {
  local log="$1"
  local marker_re="$2"

  local line
  line="$(grep -nE "$marker_re" "$log" | head -n 1 | cut -d: -f1 || true)"

  [[ -n "$line" ]] || return 1
  tail -n +"$line" "$log"
}

signature_hit() {
  local WORK_DIR="$1"
  local log="$WORK_DIR/qemu-console.log"

  [[ -f "$log" ]] || return 1

  local marker_line
  marker_line="$(grep -nE "$USPACE_MARKER_RE" "$log" | head -n 1 | cut -d: -f1 || true)"
  [[ -n "$marker_line" ]] || return 1

  local tmp
  tmp="$(mktemp)"
  local offset=$((marker_line - 1))

  extract_userspace_log "$log" "$USPACE_MARKER_RE" \
    | nl -ba -w1 -s $'\t' \
    | awk -v off="$offset" -F'\t' '{ printf("%d\t%s\n", $1+off, $2) }' \
    > "$tmp"

  local hits
  hits="$(
    grep -Eai -n \
      -f <(grep -Ev '^\s*$|^\s*#' "$SIG_RE") \
      "$tmp" \
    | head -n 20 || true
  )"

  if [[ -n "$hits" ]]; then
    echo "=== SIGNATURE HIT (userspace-gated) ==="
    echo "work_dir=$WORK_DIR"
    echo "marker_re=$USPACE_MARKER_RE (line $marker_line)"
    echo "sig_re=$SIG_RE"
    echo
    echo "$hits"
    echo "=== END HIT ==="
    rm -f "$tmp"
    return 0
  fi

  rm -f "$tmp"
  return 1
}

echo "===== CHECK BEFORE ====="
if signature_hit "$BEFORE_WORK_DIR"; then
  echo "RESULT: BEFORE = FAIL (signature hit)"
  BEFORE_RC=1
else
  echo "RESULT: BEFORE = PASS (no signature hit)"
  BEFORE_RC=0
fi

echo
echo "===== CHECK AFTER ====="
if signature_hit "$AFTER_WORK_DIR"; then
  echo "RESULT: AFTER = FAIL (signature hit)"
  AFTER_RC=1
else
  echo "RESULT: AFTER = PASS (no signature hit)"
  AFTER_RC=0
fi

echo
echo "===== FINAL VERDICT ====="
if [[ $BEFORE_RC -eq 1 && $AFTER_RC -eq 0 ]]; then
  echo "FIXED"
  exit 0
elif [[ $BEFORE_RC -eq 0 && $AFTER_RC -eq 1 ]]; then
  echo "REGRESSION"
  exit 1
elif [[ $BEFORE_RC -eq 1 && $AFTER_RC -eq 1 ]]; then
  echo "NOT_FIXED"
  exit 1
elif [[ $BEFORE_RC -eq 0 && $AFTER_RC -eq 0 ]]; then
  echo "NO_EFFECT"
  exit 0
else
  echo "INCONCLUSIVE"
  exit 125
fi
