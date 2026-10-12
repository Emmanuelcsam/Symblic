# Provision the optional linear constructor

This is an operator administration tool for the separately pinned solver environment.
`Run` never installs a package, accepts a runtime path from a client, or invokes
this tool. Its fixed operator file is:

`~/.local/share/symblic/linear/runtime.json`

The tool inventories an already installed private environment. It neither runs
its interpreter nor imports Z3. Inventory pins the interpreter bytes, the
reviewed repository worker, and every non-cache file under `z3/` and
`z3_solver-4.15.4.0.dist-info/`. It checks the distribution metadata's declared
version. Actual native library loading/version checking remains a worker check.

On this Python 3.12 host the fixed environment is:

`~/.local/share/symblic/linear/environments/z3-4.15.4.0-py3.12-v1`

The tool derives the Python minor from its trusted system interpreter, requires
that environment's `bin/python` to resolve to `/usr/bin/python3.12`, and derives
its private `lib/python3.12/site-packages`. The bounded `pyvenv.cfg` must have
exactly the reviewed uv fields: `home`, `implementation`, `uv`, `version_info`,
and `include-system-site-packages`. The first two identify the fixed system
CPython location; the Python version must exactly match the trusted interpreter
running this tool, and system site-packages must be `false`. Duplicate keys,
alternate spelling/spacing, unknown fields and a shadow `bin/pyvenv.cfg` refuse.
The inventory records the configuration hash without executing that environment.
There is no path-selection flag. A
Python or dependency upgrade needs a deliberately reviewed versioned environment
and new pins; do not reinstall into an active pinned environment.

## Separate, deliberate installation

These are operator administration commands to run **after release review**, not
commands the runtime executes. Use the existing isolated Python workflow and
retain the command receipts. The observed wrapper currently resolves uv
0.12.20; record the actual version and tool hashes again when provisioning.
The supplied requirements lock is the prior frozen
`z3-solver==4.15.4.0` distribution lock, not a claim to use the latest Z3.

```sh
symblic_host="$HOME/.local/share/symblic/linear"
symblic_env="$symblic_host/environments/z3-4.15.4.0-py3.12-v1"
test ! -e "$symblic_env" || exit 1
umask 077
install -d -m 700 "$symblic_host/environments"
~/agent-upgrades/bin/agent-tool uv venv \
  --no-managed-python --no-python-downloads --python /usr/bin/python3.12 "$symblic_env"
~/agent-upgrades/bin/agent-tool uv pip install \
  --python "$symblic_env/bin/python" --no-deps --require-hashes --link-mode copy \
  -r scripts/symblic-linear-requirements.lock
find "$symblic_env" -type f -exec chmod go-w -- {} +
find "$symblic_env" -type d -exec chmod go-w -- {} +
```

`--link-mode copy` ensures permission cleanup of the new environment does not
modify shared cache hardlinks. `find` does not follow its interpreter symlink.
The inventory requires real operator/root-controlled directories and files that
are not group/other writable; deployed worker/lock assets and the review record
must meet that requirement too. Check the current host inventory before deciding
whether installation is necessary; never replace an active environment in place.

## Review, inventory, then publish

An operator-controlled review JSON has exactly these fields, using **actual hashes
from the accepted release** (the placeholders below deliberately fail validation):

```json
{
  "version": 1,
  "worker_sha256": "<accepted symblic/linear/worker.py SHA-256>",
  "requirements_lock_sha256": "41518b8da95fcc28d044559a06ff0df5d0881bcc14efff5151b7d1eb492f5e7b",
  "package_version": "4.15.4.0"
}
```

```sh
/usr/bin/python3.12 -I -S -B tools/scripts/symblic_linear_provision.py inventory /private/accepted-review.json
/usr/bin/python3.12 -I -S -B tools/scripts/symblic_linear_provision.py publish /private/accepted-review.json
```

Inventory is read-only. Publication is explicit: it uses a bounded file lock,
creates a canonical ASCII runtime file with mode 0600, fsyncs files/directories,
and retains content-addressed versions under `linear/revisions/`. An identical
existing active record is idempotent and is not rewritten. A different one
refuses by default. Deliberate replacement requires its exact current byte hash:

```sh
/usr/bin/python3.12 -I -S -B tools/scripts/symblic_linear_provision.py publish \
  /private/new-accepted-review.json --replace-sha256 EXACT_CURRENT_RUNTIME_SHA256
```

An explicitly supplied replacement hash must match the active record even when
the proposed bytes are identical. A hash cannot replace an absent record; initial
publication omits the flag. The old and new records are retained before the atomic
active-file replacement.
Malformed/noncanonical existing records and symlinks refuse even with a supplied
hash; preserve and inspect them instead of treating them as a normal upgrade.
A failed publication can leave a durable candidate/history or active file; rerun
inventory and inspect status. An exact repeat confirms existing durability.
Cleanup cannot replace the original interrupt or stop exception.

These pins describe trusted-host file identity. They do not attest solver
correctness, malicious-host security, simultaneous filesystem snapshots, or
model weights. A later file change makes the pinned worker checks refuse;
publication itself performs no solver smoke test. Package limits match the fixed
worker: 256 payload files, 40 MB per file, 64 MB total; the provisioning walk also
caps entries at 1024 and depth at 16. Runtime/review JSON is bounded to 64 KiB.
The worker's `-I -S -B` launch and explicit private package loading remain required;
this inventory is not a replacement for those startup controls. File reads refuse
observed type, ownership, permission or content-metadata changes across
pre-open/open/post-read checks. Those checks are not a simultaneous filesystem
snapshot and do not prevent every later host mutation.
