#!/usr/bin/env sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'Python 3 is required. On NixOS use: nix run .#install' >&2
  exit 1
fi
exec python3 "$task_root/skill-source/job-apply/scripts/job_apply.py" install "$@"
