#!/usr/bin/env sh
set -eu
task_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$task_script_dir/job_apply.py" "$@"
