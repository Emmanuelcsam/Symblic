# Portable verified programs, format 2

The portable export runs pure Symblic programs in a bounded, isolated CPython child on Linux x86_64 and ARM64. It includes the authoritative native source registry, captured libraries and an independently specified conformance corpus. Exporting a target profile declares what runtime must be used; executing verification on that runtime provides the evidence.

A program can use exact arithmetic, conditionals, finite loops, typed values, records, sets, comprehensions, pure functions, finite Datalog, proofs, quantities and bundled library imports. Native `ask`, effects, providers, JavaScript execution and solver backends are refused. This is a finite pure execution profile, not the complete hosted Symblic environment, a WASM implementation or a Windows release.

## Build, check and run

```sh
python3 -B symblic/portable/export.py runtime > runtime.json
python3 -B symblic/portable/export.py build --source-root . --output new-export.zip
python3 -B symblic/portable/export.py verify new-export.zip --manifest-sha256 HASH_PRINTED_BY_BUILD
python3 -B symblic/portable/export.py run new-export.zip example.sym --manifest-sha256 HASH_PRINTED_BY_BUILD --inputs-json inputs.json
```

For example, `example.sym` can contain:

```symblic
given n: Int.
for i in 1..n do
  let square = i * i.
end.
show square.
```

With `inputs.json` containing `{"n":4}`, the result is `[1,4,9,16]`. Each iteration has its own scope and the loop lifts `square` into a list after completion. Every run first checks the bundled corpus, then forces the verified profile, records source/input hashes and returns the actual result. A failed assertion stays a failure.

To build for another supported machine, capture `runtime` there and pass its exact file:

```sh
python3 -B symblic/portable/export.py build --source-root . --target-runtime target-runtime.json --output target.zip
```

The supported envelope is CPython 3.11–3.13, little-endian Linux on x86_64 or aarch64. Patch version, Unicode version and the complete runtime profile must match the manifest exactly. A declaration of support is not a measurement of every patch release. Format 1 archives retain verification compatibility; executing user programs requires format 2.

## Measured portability

On 2026-10-06 the completed resource-handling source snapshot (`f2920e4834b7233ca11719618c34693992fc7ebfe2a054c6be7b9571361d818b`) passed all **16 corpus cases** and the user program above on these actual machines:

| Machine | CPython | Architecture | Unicode |
| --- | --- | --- | --- |
| the host | 3.12.3 | x86_64 | 15.0.0 |
| node-i | 3.13.5 | x86_64 | 15.1.0 |
| ARM single-board node | 3.13.5 | aarch64 | 15.1.0 |

All three runs returned `[1,4,9,16]` for the same source and input hashes, with zero model calls, network calls, store activity or subprocess activity inside the verified runner. The full corpus plus user program took 13.59 s on the host, 5.98 s on the ARM node and 3.23 s on node-i in this serial check. These are elapsed observations under the current load, including verification and imports, not comparative hardware benchmarks.

An earlier source snapshot (`a23d573a42a7423fd1970b062bbc81bf0a1b1f0e0bcae58e03a056c80915d2ca`) also passed on node-a with CPython 3.11.2 / Unicode 14.0.0, the host 3.12.3 and the ARM node 3.13.5. The completed snapshot was not rerun on 3.11.2: node-a had insufficient admitted spare capacity, so the final check used node-i. Support for 3.11 is retained, but the older receipt does not verify the changed source on that runtime.

The corpus covers rational arithmetic, typed set distinctions, Unicode string identity, Datalog reachability, a captured library, a deliberate failing assertion, branches, loop collection, implication and biconditional truth tables, quantifiers, recursion, empty record/set distinction, negative division, comprehensions, a checked proof and unit conversion. Its independently specified outputs agreed across all three runtimes. This is evidence for those observations, not a proof that arbitrary programs behave identically everywhere. Native kernel identities remain different when Python, Unicode or backend identities differ; host locks cannot silently resume under a portable identity.

Save verification JSON and compare it explicitly:

```sh
python3 -B symblic/portable/export.py compare host.json worker.json arm.json
```

Comparison requires the same source suite, corpus and internally consistent observation hashes, successful checks and zero external activity. Receipts are local integrity evidence, not authenticated statements from remote machines.

## Integrity and bounds

Builds are reproducible: sorted members, fixed timestamps/modes and exact bytes. A source change during capture refuses. The manifest records the authoritative registry's exact required Python modules, assets and libraries, plus the runner and corpus. The child-process resource limiter is captured in the runtime identity. No histories, settings, credentials, installed third-party packages or private stores are copied. Output archives must be new files. Retain the printed manifest SHA separately; hashes do not establish that untrusted Python source is safe.

Verification checks exact membership, file sizes and hashes, safe regular-file paths, duplicates and the externally supplied manifest hash before execution. The child uses `python -I -S -B`, a scrubbed environment, one allowed CPU, 512 MiB address space, 20 CPU seconds and 60 wall seconds. Audit guards allow bundled and standard-library reads and refuse mutation, sockets and subprocesses. CPython builds that use the entropy-device fallback may read only the exact `/dev/urandom` Linux character device (major 1, minor 9) for opaque execution IDs; aliases, descriptor paths, other devices and writes remain refused. There is no run folder, effect host or provider budget. First-party imports must come from the extracted bundle.

User source is limited to 256 KiB, request JSON to 512 KiB, kernel execution to 200,000 steps, and output to 128 entries/1 MiB. Unsupported statements are rejected recursively, including nested asks. These guards cover trusted pinned native code; they are not an adversarial Python sandbox. The CLI reports failed or refused execution rather than treating resource exhaustion as a successful answer.

All twelve focused isolated tests passed against the same completed source snapshot (96.13 s). They cover reproducible builds, registry membership, real corpus/user execution, tampering, unsafe paths and members, runtime mismatch, unsupported/nested statements, input/output limits and comparison mismatch. Test artifacts use temporary directories and no model or live service.
