#!/bin/sh
set -eu
patcher_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
seplos_venv=${SEPLOS_VENV:-"$HOME/.local/share/seplos-oem-patcher/venv"}
case "$seplos_venv" in *:*) printf '%s\n' 'Choose SEPLOS_VENV without a colon; venv rejects colons in its path.' >&2; exit 2;; esac
cd /private/tmp
python3 -I -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
python3 -I -m venv "$seplos_venv"
"$seplos_venv/bin/python" -I -m pip install -r "$patcher_dir/requirements.txt"
printf 'Interpreter: %s/bin/python\n' "$seplos_venv"
