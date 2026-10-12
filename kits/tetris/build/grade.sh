#!/usr/bin/env bash
# grade.sh RUN_FOLDER [OUT.html]
#
# Save the tetris.html a spec build assembled and grade it with the strict harness (../harness/harness.mjs, headless
# Chromium through Playwright). RUN_FOLDER is the folder of a build run (`tools/symblic run BUILD.sym --dir
# RUN_FOLDER`, or `build/dryrun.py --dir RUN_FOLDER OUT.html`). The page is the full value from the run's state.json.
# Writes OUT.html (default RUN_FOLDER/tetris.html) and the grade next to it as OUT.grade.json, and exits with the
# harness's code: 0 only when every required check passes.
#
# Needs python3, Node.js 22 (`node` on PATH, or NODE=/path/to/node) and Playwright with Chromium (see
# ../harness/harness.mjs; PLAYWRIGHT_MODULE may name an installed playwright/index.mjs).
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
run="${1:?usage: grade.sh RUN_FOLDER [OUT.html]}"
[ -f "$run/state.json" ] || { echo "no state.json in $run: give the folder of a build run" >&2; exit 2; }
out="${2:-$run/tetris.html}"
python3 - "$run" "$out" <<'PY'
import json, sys
run, out = sys.argv[1], sys.argv[2]
with open(f'{run}/state.json', encoding='utf-8') as fh:
    st = json.load(fh)
o = next((o for o in st.get('outputs') or [] if o.get('label') == 'tetris.html'), None)
if not o or not isinstance(o.get('value'), str):
    sys.exit(f'no tetris.html output in {run} (status {st.get("status")})')
with open(out, 'w', encoding='utf-8') as fh:
    fh.write(o['value'])
print('saved', out, len(o['value']), 'characters')
PY
node="${NODE:-node}"
command -v "$node" >/dev/null || { echo "node not found: install Node.js 22 or set NODE" >&2; exit 2; }
exec nice -n 10 "$node" "$here/../harness/harness.mjs" "$out" "${out%.html}.grade.json"
