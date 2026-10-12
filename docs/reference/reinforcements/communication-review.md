# Symblic spec self-sufficiency replication

Date: 2026-10-02. Author: `symrein-replication`. This replaces the originally
assigned communication-review topic with the requested bounded replication.

**Finding:** the spec plus its examples sufficed for exact arithmetic, transitive
family logic and two repeatable drawings on this checkout. A cube **data record**
needed two corrections: a reserved builtin name and ambiguous nested-list length
syntax. A typed ask could be checked and previewed, but the CLI's `fake` applicator
was unavailable. Kernel fixtures validated the record and postcondition; they do
not establish that model-reply parsing or ensure retries work.

## Protocol and exposure

- Checkout tested: `913dcf8887e477383ae0458f44721206f32eb5a3`;
  Symblic reports version `2.0`; system Python `3.11.2`, `x86_64`, one cluster node.
- Language-authoring sources: [SPEC.md](../SPEC.md) and examples
  01 (not included in this repository),
  [02](../../../examples/02-flower-formal.sym),
  03 (not included in this repository),
  04 (not included in this repository), and
  [10](../../../examples/10-kernel-identity.sym).
  Spec SHA-256: `82fb6a583cec1209be33f9726e68c5f4f1cbc7a268abfe05c704c84405724205`.
- Read the required `CLAUDE.md`, working agreement, complete Automation Studio /
  Symblic contract and [PRIOR-ART.md](../PRIOR-ART.md). The survey supplied context,
  not program answers; this report neither repeats nor independently verifies its
  literature or measurement claims. No external research was needed for this task.
- **Incidental exposure:** the mandatory context pack printed source-file
  descriptions, symbol names/signatures and test-file descriptions, including
  `SymblicError`, `Applicators.__init__`, `_dec`, `kernel_run`, `FakeApps` and
  benchmark entrypoint names. It also printed an existing cross-node identity
  claim. No implementation bodies, parser code, tests, benchmark answers,
  builtin catalog, prior Symblic result artifacts or private run histories were inspected.
  CLI help, checker diagnostics, previews and these new synthetic outputs were
  inspected after writing the initial programs. The generic `bin/devcheck` wrapper
  was read to select the repository check. This is not a completely blind trial.
- All five initial `.sym` files below were written into a temporary directory
  **before any checker, CLI help or execution**. They remained unchanged. All
  corrections and fixtures were separate files. Only this document is committed.
- Each Symblic validation invocation ran sequentially with a 10-second CPU limit,
  20-second wall timeout and affinity to one available CPU. Every execution used
  its own temporary run folder. Kernel programs used `--by kernel`; the record ask
  explicitly named `fake`. No model/API calls, services, power settings, live site,
  benchmark or other agents were used. The unavailable-fake attempt did record
  one failed applicator attempt in its own synthetic run (`asks=1`, `calls=1`);
  that counter is not evidence of a real model call.

## Initial versus corrected outcomes

`check` is a planning/checking result, not proof of successful execution. All
successful kernel executions below reported `asks=0`, `calls=0`.

| Case | Initial check | Initial execution / preview | Corrections and final outcome |
|---|---|---|---|
| Exact arithmetic | Exit 0 | `done`; all three assertions pass | None |
| Typed record + ensure | Exit 0; ask classified `closed` | Preview exit 0, intended schema; explicit fake run exit 1, unavailable applicator | Original remains preview-only; three separate kernel fixtures test acceptance, ensure rejection and type rejection |
| Transitive family | Exit 0 | `done`; exactly Ben, Cleo, Dov, Eli | None |
| Flower + polygon | Exit 0 | `done`; two SVG outputs | None; a second fresh execution produced identical bytes |
| Cube data | Exit 1: `cube` is a builtin function name | Original not executed after failed check | Rename: check passes, execution fails on inner-list length. Named `Face` type: check and execution pass |

These are five deliberately selected authoring cases, not a random sample. Do not
turn the counts into a general success rate or statistical determinism claim.

## 1. Exact arithmetic — initial and final `01-arithmetic.sym`

```sym
program Exact arithmetic replication.
let tenth: Number = 0.1 + 0.2.
let third: Number = 1 / 3.
let combined: Number = (7 / 9 + 2 / 9) * 18.
assert tenth = 0.3.
assert third * 3 = 1.
assert combined = 18.
show [tenth, third, combined] as "exact results".
```

Observed output: `[0.3, 1/3 (≈0.333333333333), 18]`; run fingerprint
`1e38b822408abbd6`. The assertions verify the decimal sum and rational identity,
not merely an approximate display. CLI JSON represents the first two output
values as display strings, **not** the `{"#q":"p/q"}` canonical objects described
in spec §3. The spec needs to distinguish canonical hashing from display/report
serialization; no arithmetic correction was necessary.

## 2. Typed record — initial `02-record.sym`

```sym
program Typed record replication.
define Parcel as Record {count: Int in 1..5, color: one of {blue, gold}, sealed: Bool}.
ask parcel: Parcel "Return count 3, color blue, sealed true." by fake with effort=low, votes=1, retries=1, tools=none
ensure parcel.count = 3 and parcel.color = "blue" and parcel.sealed else retry because "the parcel must contain three blue items and be sealed".
show parcel as "validated parcel".
```

The predetermined synthetic answer was:

```json
{"answer":{"count":3,"color":"blue","sealed":true}}
```

Preview stopped at the ask, with no known bindings, and emitted this schema:

```json
{"type":"object","properties":{"answer":{"type":"object","properties":{"count":{"type":"integer","minimum":1,"maximum":5},"color":{"type":"string","enum":["blue","gold"]},"sealed":{"type":"boolean"}},"required":["count","color","sealed"],"additionalProperties":false}},"required":["answer"],"additionalProperties":false}
```

The safe `--by fake` execution failed at line 3:

```text
no applicator gave a valid answer for parcel (fake is not an available applicator here)
```

Spec §6 names `fake (tests)` but supplies no callable fake interface or CLI answer
injection recipe. CLI `--help` lists only `--by`, `--input`, `--dir`, `--json` and
four commands. `--input` is documented for `given`, not injecting ask replies.
I did not inspect tests or implementation to discover a hidden harness.

**Separate fixture, not a repaired ask:** substitute the fake answer's payload
as a typed kernel binding and change `else retry` to `else fail` because no ask
exists to retry. This validates only type acceptance and the postcondition:

```sym
program Typed record replication.
define Parcel as Record {count: Int in 1..5, color: one of {blue, gold}, sealed: Bool}.
let parcel: Parcel = {count: 3, color: "blue", sealed: true}.
ensure parcel.count = 3 and parcel.color = "blue" and parcel.sealed else fail because "the parcel must contain three blue items and be sealed".
show parcel as "validated parcel".
```

| Fixture change | Check | Execution |
|---|---|---|
| Good payload above | Exit 0 | Exit 0, `done`, fingerprint `59677fea02db5a85` |
| Change `count: 3` to `count: 2` | Exit 0 | Exit 1, `kind=check`, line 4: `ensure failed: parcel.count = 3 and parcel.color = "blue" and parcel.sealed — the parcel must contain three blue items and be sealed` |
| Change `count: 3` to `count: 6` | Exit 0 | Exit 1, `kind=type`, line 0: `parcel.count must be between 1 and 5, got 6` |

Untested: JSON-envelope parsing, coercion of model replies, feedback delivery,
retry anchoring/counts, consensus and real applicators. A runnable documented fake
adapter would close this replication gap without requiring a model call.

## 3. Transitive family — initial and final `03-family.sym`

```sym
program Transitive family replication.
fact parent(ada, ben), parent(ben, cleo), parent(cleo, dov), parent(ada, eli).
rule ancestor(X, Y) if parent(X, Y).
rule ancestor(X, Z) if parent(X, Y) and ancestor(Y, Z).
let descendants = query ancestor(ada, Who).
assert "ben" in descendants and "cleo" in descendants and "dov" in descendants and "eli" in descendants.
assert len(descendants) = 4.
assert not ("ada" in descendants).
show descendants as "Ada descendants".
```

Observed descendants: `["ben", "cleo", "dov", "eli"]`; all assertions pass;
run fingerprint `b6df6bc565b54372`. Dov requires a three-edge path. The assertions
also reject an extra self-ancestor and check the total count. Facts are authored
explicitly, so this does not test translation of a story into relations.

The spec statement table explains facts/rules but omits `query` syntax and result
shape; example 04 supplies `let descendants = query ancestor(ada, Who)` and string
membership. That was enough here. Ordering, duplicates, ground queries and
multi-variable query results need explicit documentation before independent
implementations can agree on behavior. This case does not test those variations.

## 4. Flower and polygon — initial and final `04-drawings.sym`

```sym
program Deterministic drawings replication.
let design = {petals: 7, color: "violet", center: "gold", shape: "pointed", layers: 2,
              length: 4 / 5, width: 1 / 2, rotation: 0, leaves: 2, stem: true,
              size: 256, background: "white", center_size: 1 / 5}.
draw flower(design) as "flower.svg".
draw polygon(sides=5, color="teal", size=256) as "pentagon.svg".
show [hash(flower(design)), hash(polygon(sides=5, color="teal", size=256))] as "drawing fingerprints".
```

Two executions in **different fresh folders**, not replay, both completed with
run fingerprint `cf68ac926d6ed3e7`. Raw SVG strings were compared byte-for-byte.

| Artifact | UTF-8 bytes | SHA-256 of SVG bytes | Symblic drawing fingerprint |
|---|---:|---|---|
| `flower.svg` | 4211 | `2194723b9db588848d068a12d760d7617e87eb4616465ef959bb9da39b6399cf` | `173fd98f1f44df4d` |
| `pentagon.svg` | 223 | `2a5b6f9dd51b42ecc3629c99864f10858e6662565eaae840fde43208357713d9` | `2a963150b18fa391` |

This is local repeatability of one formal parameter record and one polygon, not
cross-machine or cross-model evidence. There was no prose-to-flower translation
or visual-quality evaluation. SHA-256 of bytes differs from the language-level
fingerprint; the report deliberately labels both.

Spec §7 lists parameter names, some ranges and rounding, but omits defaults,
units/normalization for several dimensions, palette mappings and the geometric
construction needed to reproduce the renderer independently. For example, this
run's `background: "white"` produced `fill="#fbfaf6"`, `color: "violet"` produced
`#7b4fb0`, and the polygon's `"teal"` produced `#2a9d8f`. These are observed palette
choices, not CSS-color equivalences specified by the document. A versioned
renderer dependency can supply repeatability without making the prose a complete
independent rendering specification.

## 5. Cube representation — initial `05-cube.sym`

The spec documents records and lists, but no native cube or mesh-rendering
contract. I therefore chose eight vertices and six indexed quadrilateral faces.
Coordinates are unitless; indices follow Symblic's one-based list convention.
This representation asserts no mesh API, CAD export or rendered solid support.

```sym
program Cube data representation replication.
note A unit cube encoded as vertices and face indices; no 3D renderer is specified.
define Point as Record {x: Number, y: Number, z: Number}.
define CubeData as Record {vertices: List of Point length 8, faces: List of List of Int length 6}.
let cube: CubeData = {vertices: [{x: 0, y: 0, z: 0}, {x: 1, y: 0, z: 0},
                               {x: 1, y: 1, z: 0}, {x: 0, y: 1, z: 0},
                               {x: 0, y: 0, z: 1}, {x: 1, y: 0, z: 1},
                               {x: 1, y: 1, z: 1}, {x: 0, y: 1, z: 1}],
                     faces: [[1, 4, 3, 2], [5, 6, 7, 8], [1, 2, 6, 5],
                             [2, 3, 7, 6], [3, 4, 8, 7], [4, 1, 5, 8]]}.
assert len(cube.vertices) = 8.
assert len(cube.faces) = 6.
assert cube.vertices[7].z = 1.
show cube as "unit cube data, not a rendered solid".
```

**Attempt 0:** checker exit 1, `error line 5: cube is a builtin function name`.
This error establishes a reserved name, not the builtin's meaning or 3D capability.
The spec sends builtin discovery to the UI or implementation catalog (§7), outside
this trial's permitted authoring sources.

**Attempt 1:** rename the binding and its references from `cube` to `solid`; make
no other change. Checker exit 0; execution exit 1:

```text
solid.faces[0] has 4 items; the type wants 6..6
```

The diagnostic indicates that `length 6` constrained the **inner** list. Its
`[0]` index and reported source line 0 also differ from the documented one-based
language indexing and provide no useful program source location.

**Attempt 2, final corrected `05-cube-v2.sym`:** introduce a named four-index
`Face`, then constrain the outer list to six faces. The additional `Int in 1..8`
constraint makes the indexing convention explicit. Both check and execution
exit 0; run fingerprint `26f9cd9af791a6e9`.

```sym
program Cube data representation replication.
note A unit cube encoded as vertices and face indices; no 3D renderer is specified.
define Point as Record {x: Number, y: Number, z: Number}.
define Face as List of Int in 1..8 length 4.
define CubeData as Record {vertices: List of Point length 8, faces: List of Face length 6}.
let solid: CubeData = {vertices: [{x: 0, y: 0, z: 0}, {x: 1, y: 0, z: 0},
                               {x: 1, y: 1, z: 0}, {x: 0, y: 1, z: 0},
                               {x: 0, y: 0, z: 1}, {x: 1, y: 0, z: 1},
                               {x: 1, y: 1, z: 1}, {x: 0, y: 1, z: 1}],
                     faces: [[1, 4, 3, 2], [5, 6, 7, 8], [1, 2, 6, 5],
                             [2, 3, 7, 6], [3, 4, 8, 7], [4, 1, 5, 8]]}.
assert len(solid.vertices) = 8.
assert len(solid.faces) = 6.
assert solid.vertices[7].z = 1.
show solid as "unit cube data, not a rendered solid".
```

The returned record contains exactly the listed eight vertices and six faces.
The type checks bound face indices and list lengths; the explicit assertions check
vertex/face counts and a coordinate. They do **not** prove manifoldness, winding,
edge incidence, volume or geometric validity for arbitrary inputs. Native cube
construction/rendering remains unspecified and was not reverse-engineered.

## Precise spec changes for the coordinator

These are proposed documentation changes, not changes made to language/runtime:

1. **Give a runnable offline fake example** (§6/§8): exact command or stable public
   harness interface, answer-envelope injection, per-attempt replies, a passing
   record and a rejected-then-corrected reply. State whether `fake` is test-only
   and unavailable through `tools/symblic`. This is the main incomplete journey.
2. **Document reserved names** (§1/§7): include a versioned builtin signature
   table in the spec or a linked specification appendix. The current redirection
   to implementation/UI leaves even legal variable names undiscoverable here.
   Explain `cube` rather than inferring its behavior from the name.
3. **Define type suffix binding** (§3): show the distinction between an outer list
   length and inner list length, preferably with `define Face as List of Int in
   1..8 length 4` followed by `List of Face length 6`. Explain precedence and
   grouping; no grouping syntax was guessed in this exercise.
4. **Specify `query`** (§2/§7): single- versus multi-variable shape, atom/string
   representation, ordering, duplicate treatment and ground-query behavior.
   Move the minimum executable example into the specification itself.
5. **Publish the renderer contract or explicitly pin its implementation** (§7):
   defaults, units, clamping/error behavior, palette, geometry and serialization
   rules. Parameter names plus rounding do not suffice to reconstruct identical
   SVGs. The observed palette mappings above need a documented interpretation.
6. **Separate representations and checker guarantees** (§3/§8): canonical value,
   CLI display JSON, SVG digest and Symblic fingerprint are distinct. Document
   that successful `check` need not imply type/postcondition success at runtime.
   Add a CLI synopsis; here `check --json` and `preview --json` still printed text.
7. **Clarify diagnostics**: use source locations and language-consistent indices,
   or explicitly identify internal zero-based validation paths. The cube and
   invalid-count failures currently report line 0.

## Reproduction and verification

Copy the five initial code blocks into the indicated filenames in a temporary
folder; keep the original cube file. Copy the corrected cube and record fixture
into separate files. From the pinned checkout, use:

```sh
tools/symblic check /tmp/replication/01-arithmetic.sym --json
tools/symblic run /tmp/replication/01-arithmetic.sym --by kernel --dir /tmp/replication/arithmetic-run --json
tools/symblic preview /tmp/replication/02-record.sym --by kernel --json
tools/symblic run /tmp/replication/02-record.sym --by fake --dir /tmp/replication/fake-run --json
```

The last command is an **expected failure on this checkout**, not a way to inject
an answer. The source's explicit `by fake` also remains visible in the preview;
`--by kernel` sets a default rather than replacing the source's applicator.
For family, drawings, corrected cube and record fixtures use the arithmetic
check/run pattern with their filenames and a fresh `--dir` for every run.
Reproduce the rename-only intermediate cube before the final correction. For
negative record fixtures change only the count value as specified above.

The actual calls were wrapped with Python `subprocess.run(..., timeout=20)`, a
`preexec_fn` setting `resource.setrlimit(resource.RLIMIT_CPU, (10, 10))` and
`os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})`, and
`PYTHONDONTWRITEBYTECODE=1`. Calls were sequential, with no test workers or package
installation. Verification inspected status, values and error kinds, not only
exit codes; drawing equality compared each report's `outputs[i].svg` strings and
computed SHA-256 over their UTF-8 bytes.

Repository verification: `bin/devcheck` passed in 66.1 seconds with 0 blocking,
0 warnings and 0 hints; it selected 0 affected test modules for this document-only
change. Its shellcheck and additional gitleaks checks were skipped because those
tools are absent; no tools were installed. The built-in secrets check passed.
`git diff --cached --check` passed before committing. The isolated CLI checks above
provide the executable evidence; no broad runtime test suite was run.

The bounded outcome supports spec-guided use of these kernel examples. It does
not establish universal determinism, independent implementation compatibility,
real-model correctness or successful fake-driven ensure retries.
