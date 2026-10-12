# symblic/js: checking model-written JavaScript

When a program asks a model for code (`ask f: Code js ...`), the kernel does not trust the answer: it runs the
code against examples the program wrote, in a sandbox, and only an answer that passes is accepted. This package
is that test oracle. It never runs model code anywhere except inside the sandbox described below.

| File | What it is |
| --- | --- |
| `check.py` | The `js_test(source, cases)` and `js_run(source, call)` builtins: run JavaScript in a fresh V8 context per case, in a sandboxed `node` child, and compare JSON results. |
| `contract.py` | The `js_declarations_check(source, contract)` builtin: parse (never run) a script and check that it declares exactly the promised top-level names and kinds, with passive initializers only. |
| `normalize.py` | Deterministic repair of a small model's answer for one named unit (`Code js unit NAME reusing A, B`): picks the right fenced block, restores a dropped `function` keyword, cuts copies of helpers the file already has. Code does the repair, never a model. |
| `runner.js` | The node child of `check.py`. |
| `contract_runner.js` | The parse-only node child of `contract.py`. |
| `normalize.js` | The parse-only node child of `normalize.py`. |
| `acorn.js`, `acorn-LICENSE.txt` | [Acorn](https://github.com/acornjs/acorn) 8.8.1, the JavaScript parser, vendored unchanged under the MIT licence. Its SHA-256 is pinned in `check.py` and `contract.py`. |

## How a check runs

1. The runner, the parser, the sandbox launcher (`symblic/sandbox/landlock.py`) and the resource limiter
   (`symblic/kernel/process_limits.py`) are read once per process and copied into a fresh, empty scratch
   directory. The repository itself is never visible to the child.
2. `node` starts under the limiter (CPU time, 2 GiB address space, 256 MiB V8 heap) inside the Landlock sandbox:
   read-only system directories, node's own install read/exec, the scratch directory as the only writable place,
   no TCP (connect allowed only to port 1, bind denied), no Unix sockets, no new privileges, a scrubbed
   environment.
3. Each case runs in a fresh V8 context built from a null-prototype object, with string code generation off,
   `Math.random` throwing and `Date` fixed. Only JSON text comes back. Each case has a 3 second limit.

A timeout, exhausted memory or a missing runtime makes a check **inconclusive**, never a failure and never a
pass: such an observation cannot reject a candidate or trigger a model repair. A timed-out case is observed
again once the machine is calm, because 3 seconds of wall time on a busy machine is little CPU time.

## Requirements

- **Linux** with Landlock network rules (ABI 4, Linux 6.7 or newer). On other systems `available()` is false and
  every check reports `unavailable`.
- **Node.js**, found as `$SYMBLIC_NODE`, else the newest `~/.nvm/versions/node/*/bin/node`, else `node` on
  `PATH`. Developed and tested with Node 22.

The adapter version, the hashes of these assets and the Node version are part of the kernel identity
(`symblic.kernel.language.kernel_id`): a different JavaScript engine may give different results, so results are
only compared under the same identity.

## What it does not do

It decides whether code gives the expected JSON for the program's examples, nothing more: not that the code is
correct for other inputs, safe to run elsewhere, or what the author intended. The sandbox protects the machine
running the check; it is not meant to make the code itself safe to deploy.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/js -t .
```

Tests that need Node.js and Landlock skip on machines without them.
