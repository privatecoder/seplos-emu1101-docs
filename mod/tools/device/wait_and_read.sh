#!/bin/sh
seplos_tool_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
P=${1:?Usage: wait_and_read.sh PORT}
end=$(( $(date +%s) + 180 ))
while [ $(date +%s) -lt $end ]; do
  out=$(python3 -I -B "$seplos_tool_dir/seplos_query.py" "$P" 19200 00 51)
  case "$out" in *"RX ~"*) echo "$out"; echo "== awake $(date +%T)";
    python3 -I -B "$seplos_tool_dir/seplos_query.py" "$P" 19200 00 42 00
    python3 -I -B "$seplos_tool_dir/seplos_query.py" "$P" 19200 00 44 00
    python3 -I -B "$seplos_tool_dir/seplos_query.py" "$P" 19200 00 47
    exit 0;; esac
  sleep 0.5
done
echo "TIMEOUT: no reply within 180 s"
