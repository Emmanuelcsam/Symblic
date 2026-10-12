# symblic/sandbox: a launcher for untrusted programs

`landlock.py` starts a program with kernel-enforced restrictions that an ordinary (unprivileged) user can
apply on Linux, before the program runs:

- **Landlock filesystem rules**: system directories read-only, the program's own install read/exec, the
  directories you name read-write, nothing else. The rest of your home directory is simply not there.
- **Landlock scoping** (ABI 6+): the program cannot signal processes outside the sandbox.
- **Landlock network rules** (`--net-connect PORTS`, ABI 4+): TCP connect only to the listed ports, bind denied,
  plus a seccomp filter that closes the ways around those rules (MPTCP, TCP Fast Open, exotic socket families,
  io_uring).
- **No Unix sockets** (`--no-unix`): a seccomp filter makes `socket(AF_UNIX)` fail.
- **no_new_privs** and a new session; the caller passes a minimal environment.

```
python3 symblic/sandbox/landlock.py [--ro P]... [--rx P]... [--rw P]... [--cwd D] \
        [--require] [--no-unix] [--net-connect PORTS] [--net-bind-ephemeral] -- CMD ARG...
```

Use `--require` whenever the program is untrusted: without Landlock it then refuses to run (exit status 125)
instead of running with a warning.

## Who uses it

- `symblic/js/check.py` and `symblic/js/contract.py` run `node` under it (with `--require --no-unix
  --net-connect 1`, i.e. no network at all) to test model-written JavaScript.
- The autogen tools (`symblic/autogen`) run agent CLIs and model-written test scripts under it.

The file is standard-library Python and self-contained, because the JavaScript adapter copies it into a fresh
scratch directory and runs the copy. Its bytes are part of the kernel identity through the JavaScript
adapter's asset hash.

## Limits

- Linux only (x86_64 and aarch64 system-call numbers), Landlock ABI 1 or newer for the filesystem rules
  (Linux 5.13+), ABI 4 (Linux 6.7+) for network rules, ABI 6 for signal scoping.
- Landlock mediates TCP `connect()`/`bind()`, not UDP: DNS and other UDP traffic are not blocked by
  `--net-connect`.
- It restricts what a process can reach. It does not limit CPU or memory (see
  `symblic/kernel/process_limits.py`), and it is not a container or a virtual machine.

The design notes in the module explain why bubblewrap and `preexec_fn` were not used.

There is no separate test folder: the sandbox is exercised by `tests/js` (every JavaScript check runs inside it)
and by the autogen tests.
