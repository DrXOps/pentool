#!/usr/bin/env bash
# ailog.sh — pretty-print pentool AI audit trail (JSONL → readable logs)
# Usage: ailog.sh [file]     — view file (default: ~/.pentool/ai/audit.jsonl)
#        ailog.sh -f [file]  — tail -f (follow) mode
#        ailog.sh -h         — help
#        ailog.sh | less -R  — pipe to less for paging

set -euo pipefail

MODE="page"
FILE="${HOME}/.config/pentool/logs/ai_audit.jsonl"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--follow)
            MODE="follow"
            shift
            ;;
        -h|--help)
            echo "Usage:"
            echo "  ailog.sh              — show $HOME/.pentool/ai/audit.jsonl (paged)"
            echo "  ailog.sh -f           — follow (tail -f) mode"
            echo "  ailog.sh <path>       — show custom file"
            echo "  ailog.sh -f <path>    — follow custom file"
            echo "  ailog.sh | less -R    — pipe to less with color"
            exit 0
            ;;
        *)
            FILE="$1"
            shift
            ;;
    esac
done

if [[ ! -f "$FILE" ]]; then
    echo "Error: $FILE not found" >&2
    exit 1
fi

case "$MODE" in
    follow)
        tail -f "$FILE" | python3 -u -c '
import json, sys, shutil
from datetime import datetime

term_w = shutil.get_terminal_size((80, 24)).columns

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        sys.stdout.write(line + "\n")
        continue

    ts_raw = obj.get("ts", "?")
    ts = ts_raw
    try:
        dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        ts = dt.strftime("%Y-%m-%d %H:%M:%S")
    except:  # noqa: E722
        pass

    task = obj.get("task", "?")
    req = obj.get("request", {})
    rsp = obj.get("response", {})
    error = rsp.get("error")

    sep = "─" * min(term_w, 80)
    print(f"\n\033[1;36m━{task} @ {ts} {sep}\033[0m")

    sys_preview = req.get("system_prompt_preview", "") or ""
    ctx_preview = req.get("context_preview", "") or ""
    ctx_full = req.get("context_full_truncated", False)

    if sys_preview:
        preview = sys_preview[:term_w * 4]
        print(f"\033[1;33m▶ System:\033[0m {preview}")
        if len(sys_preview) > len(preview):
            print("  \033[2m… (truncated)\033[0m")

    if ctx_preview:
        preview = ctx_preview[:term_w * 3]
        print(f"\033[1;33m▶ Context:\033[0m {preview}")
        if ctx_full:
            print("  \033[2m… (context truncated)\033[0m")

    if error and error != "null":
        print(f"\033[1;31m✖ Error: {error}\033[0m")
    else:
        raw = rsp.get("raw", "")
        parsed = rsp.get("parsed")
        if parsed:
            print(f"\033[1;32m✓ Response:\033[0m {json.dumps(parsed, indent=2, ensure_ascii=False)}")
        elif raw and raw != "null":
            print(f"\033[1;32m✓ Raw:\033[0m {raw[:term_w * 6]}")

    print()
'
        ;;
    page)
        python3 -c '
import json, sys, shutil
from datetime import datetime

term_w = shutil.get_terminal_size((80, 24)).columns

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        sys.stdout.write(line + "\n")
        continue

    ts_raw = obj.get("ts", "?")
    ts = ts_raw
    try:
        dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        ts = dt.strftime("%Y-%m-%d %H:%M:%S")
    except:  # noqa: E722
        pass

    task = obj.get("task", "?")
    req = obj.get("request", {})
    rsp = obj.get("response", {})
    error = rsp.get("error")

    sep = "─" * min(term_w, 80)
    print(f"\n\033[1;36m━{task} @ {ts} {sep}\033[0m")

    sys_preview = req.get("system_prompt_preview", "") or ""
    ctx_preview = req.get("context_preview", "") or ""
    ctx_full = req.get("context_full_truncated", False)

    if sys_preview:
        preview = sys_preview[:term_w * 4]
        print(f"\033[1;33m▶ System:\033[0m {preview}")
        if len(sys_preview) > len(preview):
            print("  \033[2m… (truncated)\033[0m")

    if ctx_preview:
        preview = ctx_preview[:term_w * 3]
        print(f"\033[1;33m▶ Context:\033[0m {preview}")
        if ctx_full:
            print("  \033[2m… (context truncated)\033[0m")

    if error and error != "null":
        print(f"\033[1;31m✖ Error: {error}\033[0m")
    else:
        raw = rsp.get("raw", "")
        parsed = rsp.get("parsed")
        if parsed:
            print(f"\033[1;32m✓ Response:\033[0m {json.dumps(parsed, indent=2, ensure_ascii=False)}")
        elif raw and raw != "null":
            print(f"\033[1;32m✓ Raw:\033[0m {raw[:term_w * 6]}")

    print()
' < "$FILE"
        ;;
esac