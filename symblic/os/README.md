# symblic/os: a prototype operating-system layer driven by Symblic

> **Status: experimental prototype.** The terminal engine and its file and process effects work and
> are tested in temporary folders. The bootable image's guest daemon is a **stub** that answers fixed
> responses, and nothing in the image runs Symblic. This is not an operating system; `roadmap.py`
> lists the 18 layers one would still need, none of them built.
>
> Like all of Symblic, this package was written by AI coding agents working under the direction of
> one person. Treat it as an agent-built prototype.

## What it is, and what it is not

The working core is **`SymblicOSTerminalEngine`** (`terminal_server.py`): give it one instruction and it

- executes it as **one bounded effect** when the instruction is a whole English sentence from a fixed
  list (`intake.py`), for example `Create a text file named "note.txt".`;
- **compiles and checks** it, without running it, when it is Symblic source (`program ...`, `let ...`);
- refuses anything else, with no side effect;
- writes a **receipt** (`receipts.py`) before acting and again when done, so a repeated request returns
  the stored result instead of acting twice, and an interrupted one is reported, never replayed.

It is **not** a shell, not an agent and not a language model: the English intake is plain pattern
matching over complete sentences, and a known command followed by extra words is refused rather than
partly executed. File effects are confined to `<root>/user_files`; processes are limited to a short
registry of executables started without a shell.

## Quick start

```sh
python3 - <<'EOF'
from symblic.os.terminal_server import SymblicOSTerminalEngine
engine = SymblicOSTerminalEngine('/tmp/symblicos-demo')          # any empty folder; the tree is created
for line in ['Create a text file named "note.txt".',
             'Write "hello" to "note.txt"',
             'Read "note.txt".',
             'program Sum.\nlet x = 1 + 2.\nshow x.']:
    event = engine.execute_instruction(line)
    print(event['type'], '|', event['receipt']['stdout'][:60])
EOF
python3 -m symblic.os.acceptance            # the offline smoke suite: 16 checks in a scratch folder
python3 -m symblic.os.terminal_server       # a loopback-only development listener on 127.0.0.1:8990
```

State lives under `SYMBLICOS_ROOT` (default `~/symblicos`); see `paths.py` for the folder tree.

## The sentences the intake understands

Arguments are quoted. A sentence must match one pattern **completely**.

| Intent | Example |
|---|---|
| create_file | `Create a text file named "a.txt".` |
| locate_file | `Find "a.txt".` |
| read_file | `Read "a.txt".` |
| write_file | `Write "text" to "a.txt"` · `Find "a.txt" and inside it write "text"` |
| append_file | `Append "more" to "a.txt"` |
| make_directory / list_directory | `Make directory "d"` · `List files` · `List directory "d"` |
| copy_file / move_file | `Copy "a.txt" to "b.txt"` · `Move "a.txt" to "d"` |
| remove_file | `Delete file "a.txt"` (files only; the sentence itself is the explicit authorization) |
| flush_file | `Save the file.` · `Save file "a.txt"` (fsync) |
| inspect_process / inspect_system / inspect_model | `Inspect processes` · `Inspect system` · `Inspect models` (only with a `model_inventory` callable) |

## Files

| File | What it does | Status |
|---|---|---|
| `terminal_server.py` | The engine, plus a loopback-only JSON development listener (no authentication, no web page). | works; tested |
| `intake.py` | Whole-sentence English → one intent. | works; tested |
| `fs_boundary.py` | Keeps every path inside one root (lexical and symlink escapes refused). | works; tested |
| `file_effects.py` | Atomic, fsynced file effects with digests in the receipt. | works; tested |
| `process_effects.py` | Runs only registered executables (no shell); stops only its own processes. | works; lightly tested |
| `receipts.py` | Receipt schema, atomic storage, an append-only journal. | works; tested |
| `protocol.py` | JSON message helpers and an in-memory request-id binder. | works; tested |
| `compiler_bridge.py` | Checks Symblic source with the kernel's own parser and checker; never runs it. | works; tested |
| `acceptance.py` | An offline smoke suite of the above (scope `isolated_fixture_smoke`). | works; tested |
| `demonstrations.py` | Three scripted demonstrations checked on disk; a model check only if you pass one. | works |
| `release_manifest.py` | A scoped manifest that never marks an unchecked subsystem as verified. | works; tested |
| `security_boundary.py` | The declared attack surface and quick boundary self-checks. | works (a declaration, not an audit) |
| `paths.py`, `service_defs.py` | The folder layout; systemd unit templates (the model unit is a placeholder). | templates only; nothing is installed |
| `image_builder.py` | BusyBox root filesystem, initramfs and ext4 image. | experimental; only the assembly logic is tested, with fakes |
| `guest_daemon.c` | The image's HTTP daemon. | **stub**: fixed answers, ignores instructions |
| `virtual_boot.py` | Boots the image twice in QEMU and records what it observes. | experimental; tested only against a scripted fake VM |
| `roadmap.py` | 18 future layers with acceptance conditions. | design notes only |

### The bootable image, honestly

`image_builder.py` packs BusyBox, a small `/init`, the guest daemon and an inert copy of the Symblic
runtime source (the image has no Python). `virtual_boot.py` boots it in QEMU and checks the daemon
over a forwarded port. Because the daemon is a stub, a passing boot check shows that the image boots and
its network and file system work, and nothing more. The `/init` script does not mount the disk image,
so files written in the guest do not survive a reboot, and `restart_persistence` is expected to be
False. Earlier versions of `virtual_boot.py` reported every check as passed without measuring it; the
code now reports only measured values. The original project's notes record that a later, corrected
guest revision (a real guest service instead of the stub) passed its own 17-check VM acceptance on one
node, but it was never merged into the sources this repository was copied from.

## What moved to `integration/host/`

These modules only ran on the original host and are kept there for reference, each with the reason at
the top of its docstring:

| Module | Why it is host-only |
|---|---|
| `symblicos_model_engine.py` | its model inventory came from the host's agent hub and its calls went through the host's admitted provider path |
| `symblicos_integrations.py` | adapters for programs the host ran beside Symblic; most are stubs that return `simulated` |
| `symblicos_physical_installer.py` | a read-only disk inspection of a node over the host's cluster module; it never installs anything |
| `symblicos_terminal_reference.py` | audits the host dashboard's terminal page, pinned by hash; that page is not in this repository |
| `symblicos_engine.py` | the host web server's `/api/symblicos/` routes for this engine, the task engine and autogen |

## Tests

```sh
DASH_TEST=1 python3 -m unittest discover -s tests/os -t .
```

`tests/os/test_terminal_engine.py` (receipts, deduplication across engine objects, whole-sentence
intake, delete, escapes, no replay, compile-only source, unicode, concurrent appends, the model
inventory, the listener's loopback/Host/Origin/tunnel checks), `test_acceptance.py` (the smoke suite in
a scratch folder with processes, sockets and URLs forbidden; the manifest never promoting an unchecked
claim), `test_image_builder.py` (assembly with fake copies; no compiler or image tool runs) and
`test_virtual_boot.py` (the boot report holds only measured values, against a scripted fake VM). The
tests of the host-only modules are in `tests/integration/`. No test boots a VM, calls a model or opens
a network connection.
