# Symblic contract audit: bounded offline reinforcement

Audited baseline: **`7b8ab72f7a2b80fe5707b135b27165f564332d86`**, 2026-10-02,
isolated `symrein-contracts` checkout. All code locations and observations below
refer to that baseline, not current live core. The primary agent is changing core
concurrently; recheck each reproduction after integration. No core, benchmark,
API or UI files were edited. No live applicators, benchmarks or services were used.

The useful distinction is between type acceptance, canonical agreement, passing
specified checks, and fresh-run reproducibility. None implies the next. The new
suite has 13 passing tests using synthetic replies, `parallel=1`, and temporary
replay stores. These are counterexamples and regression checks, not model accuracy
measurements or evidence of statistical independence.

## Existing coverage and the added checks

Baseline `tests/kernel/test_symblic.py:278` checks tie winner stability but its final
assertion allows either contested status at a 50% tie. `:315` tests strict mode
only with `agree=0.9`. `:344` tests only one ensure-retry. `:433` shows successful
key grouping, and `:462` proves reuse rather than fresh reproducibility. The
same-fingerprint test at `:293` supplies predetermined matching fake answers;
it cannot establish cross-model identity. Existing field-voting tests at `:583`
and `:600` already cover synthetic records and whole-record fallback; those were
not duplicated. Engine, applicator and review suites cover separate routing and
lifecycle boundaries.

All new test locations are in
[`tests/kernel/test_symblic_reinforcement_contracts.py`](../../../tests/kernel/test_symblic_reinforcement_contracts.py).

| Test location / boundary | What the test establishes | Limit on the claim |
|---|---|---|
| `:40` wrong unanimous answer | Three replies of 7 pass an `Int in 0..10` ask with strict 100% agreement; `assert x = 4 + 4` fails | A failed run can retain the same fingerprint as the unchecked run; check status separately |
| `:56`, `:72` ties | Default strict mode accepts 50%; `agree=0.5001` rejects it; permuting supplied sample arrival order preserves tie selection, including canonical fallback | Strict is a threshold test, not a unanimity or unique-winner requirement; no thread-scheduling claim |
| `:85` NFC | Decomposed/composed text plus normalized line ends merge; circled digits and ordinary digits remain distinct | NFC is not arbitrary semantic equivalence; record keys have a separate policy below |
| `:97`, `:108`, `:116` coercion | Extra record fields and enum spelling variants can disappear before voting; ambiguous normalized enum options reject; Bool cannot count as Int | Canonical agreement does not mean original replies were identical |
| `:123` key equivalence | `x + 1` and `1` agree under evaluation at x=0 but differ at x=2 | One evaluation point does not prove formula equivalence |
| `:136` discarded keys | Two unkeyable replies are discarded without type repairs; one survivor yields agreement=1 under strict mode | Agreement denominator is valid votes, not all requested samples |
| `:148` repair bounds | Two invalid samples each get 1, 2, 3 or 6 attempts at retries=0,1,2,99; repair keys stay distinct | `max_asks` and votes do not count every repair call |
| `:163`, `:178` ensure | One retry recomputes dependent bindings without repeating an earlier unrelated ask; retries=0 fails immediately | Does not certify multi-retry freshness; see R1 |
| `:185` replay/fresh stores | Reopened store makes zero new calls and preserves identity; a fresh store invokes the fake and can disagree | A new store is necessary for this fixture's fresh evidence, not proof of independence of real providers |

Relevant baseline symbols: `symblic.consensus` (`symblic/kernel/language.py:3480`, strict comparison
at `:3505`); `Run._ask_one` (`symblic/kernel/run.py:522`, filtering at `:590`, strict gate
at `:608`); `Run._keyed` (`:636`); `Run._sample` (`:679`); `Run.fingerprint` (`:915`).
`Run._retries` (`:281`) clamps to five; sample repairs and ensure retries have
separate counters. For one ordinary voting round, R retries and V votes allow
up to V(R+1) sample attempts per ask execution. Repeated ensure execution can
multiply that; ultra adds another round. Cache hits can reduce actual calls.

## Confirmed baseline defects: reproductions for the coordinator

These are deliberately outside the passing suite. They record observed baseline
behavior and proposed repairs, not assertions weakened to accommodate defects.
Run snippets with system Python from the checkout. Each uses only a few fake
calls or pure kernel operations.

### R1 — ensure retry budget can be spent replaying the rejected answer

**Baseline `7b8ab72f7a2b80fe5707b135b27165f564332d86`; current-live status unverified.**
`Run.exec_block` (`symblic/kernel/run.py:248`) writes feedback from the rejected value and
condition, but no ensure-attempt identity. `_sample` (`:687`) reuses sample indices;
`_call` (`:710`) returns a cached reply for the same request. After two identical
wrong answers the next repair prompt/key repeats. This also occurs without a disk
store because successful transport replies enter `Store.calls` in memory (`:733`).

```python
from symblic.kernel.run import Run

class Fake:
    def __init__(self):
        self.answers = iter([1, 1, 8])
        self.calls = 0
    def call(self, request):
        self.calls += 1
        return {"ok": True, "json": {"answer": next(self.answers)}}

fake = Fake()
r = Run('ask x: Int "Eight." with effort=low, retries=3\n'
        'ensure x = 8 else retry.\n', applicators=fake,
        options={"by": "fake:a", "parallel": 1}).execute()
print(r["status"], r["asks"], r["calls"], r["cached"], fake.calls)
# Observed: failed 4 2 2 2. The third prepared answer (8) is never requested.
```

Proposed repair: encode a deterministic ensure-attempt identity in request keys,
so attempts differ within a run but replay to the same sequence after restart.
Acceptance: this fixture should reach 8 on its third fresh call, then replay from
a temporary persisted store with no new calls. Do not disable replay globally.

### C1 — canonical type tags collide with ordinary records

**Baseline `7b8ab72f7a2b80fe5707b135b27165f564332d86`; coordinator reports the collision
also persists in current source, but this agent has not inspected live source.**
`symblic.canon` (`symblic/kernel/language.py:1461`, `:1473`) serializes a rational and a literal
record into the same JSON. This is an encoding collision, not a SHA-256 collision.
`from_json` (`:1852`) permits both a JSON fractional number and a literal record
under `Any`; the shared fingerprint then merges their votes.

```python
import symblic as S
from symblic.kernel.run import Run

a = S.coerce(0.5, {"k": "any"})
b = S.coerce({"#q": "1/2"}, {"k": "any"})
print(a == b, S.canon_json(a), S.canon_json(b))
# Observed: False {"#q":"1/2"} {"#q":"1/2"}

class Fake:
    def call(self, request):
        return {"ok": True, "json": {"answer": [0.5, {"#q": "1/2"}][request["sample"]]}}

r = Run('ask x: Any "Value." with effort=low, votes=2\n',
        applicators=Fake(), options={"by": "fake:a", "parallel": 1}).execute()
m = r["bindings"][0]["meta"]
print(r["status"], m["distinct"], m["agreement"])
# Observed: done 1 1.0 despite distinct value types.
```

Proposed repair: use unambiguous type-tagged encodings or escape record tags.
Version the fingerprint format and preserve old recorded identities. Regression
acceptance: these two Any answers remain two groups. Review `#set` and `#svg`
encodings for the same class of issue; they are not separately reproduced here.

### C2 — conflicting record aliases are order-dependent when no exact key exists

**Baseline `7b8ab72f7a2b80fe5707b135b27165f564332d86`; current-live status unverified.**
`symblic.coerce` (`symblic/kernel/language.py:1797`, exact-key preference at `:1799`) builds a normalized-key
dictionary by overwriting earlier entries. Two distinct JSON keys can denote the
same declared field, and neither needs to be an exact match.

```python
import symblic as S
ty = {"k": "record", "fields": [("x", {"k": "int"})]}
print(S.coerce({"X": 1, " x ": 2}, ty))  # {'x': 2}
print(S.coerce({" x ": 2, "X": 1}, ty))  # {'x': 1}
```

The coordinator's newer check `{x:1,X:2}` and its reversal yields x=1 in both
orders. That exact-key-precedence behavior also exists at this baseline and is
not the reproduction above. Recheck the **no exact key** case on current core
before assigning a live defect. Proposed repair: reject conflicting aliases
before normalization, or define a deterministic, documented collision policy.
Acceptance: reversing JSON key order must not change the accepted field value.

## Policy and documentation gaps, not confirmed implementation defects

All observations in this section also refer to baseline
**`7b8ab72f7a2b80fe5707b135b27165f564332d86`**.

- NFC applies to text values, not record keys: `fingerprint({"é":1})` differs from
  `fingerprint({"e\u0301":1})` (`symblic/kernel/language.py:1474`). The spec promises sorted keys,
  not normalized keys. Decide the intended key policy before adding an equality
  regression. Normalizing keys would require collision detection.
- `canon_text` (`symblic/kernel/language.py:1482`) strips outer leading whitespace as well as
  trailing spaces. The spec's shorter wording omits this loss. Avoid claiming
  whitespace-sensitive text identity from these fingerprints.
- `PRIOR-ART.md:703` calls the implementation “RFC 8785 + SHA-256.” Actual
  `canon_json` (`symblic/kernel/language.py:1489`) is a custom semantic encoding; NFC preprocessing,
  tagged rationals, Python key ordering, and 16-hex-character fingerprints are
  not evidence of JCS conformance. [RFC 8785 §3.1 and §3.2.3](https://www.rfc-editor.org/rfc/rfc8785)
  require preserving string data and sorting property names by UTF-16 code units.
  Correct the claim, or separately specify and test a JCS serialization layer.
  [Unicode UAX #15](https://www.unicode.org/reports/tr15/) defines NFC and NFKC as
  distinct normalization forms; the suite deliberately distinguishes them.
  Both official specifications were opened for this audit; no literature accuracy
  figures in PRIOR-ART were remeasured or independently revalidated.
- `run_folder(..., resume=False)` (`symblic/kernel/run.py:1116`) clears only the trace,
  not calls. A “started” run in a reused folder can still be replay. Fresh-run
  evaluation needs a new store and explicit reporting of fresh/cached counts.
  It also needs an independent truth oracle and provider/configuration provenance;
  changing fake responses here is not an independence measurement.

## Verification and integration handoff

- New suite: `python3 -m unittest tests.kernel.test_symblic_reinforcement_contracts -v`
  — **13 passed**.
- Focused checks in a single test process: `python3 -m unittest tests.kernel.test_symblic
  tests.integration.test_symblic_engine tests.providers.test_symblic_apply tests.misc.test_automation_symblic_nodes
  tests.integration.test_symblic_review tests.kernel.test_symblic_reinforcement_contracts`
  — **119 passed**, 6.3 seconds. Logged provider names come from existing fakes.
- `bin/devcheck --no-tests` — **0 blocking, 0 warnings**; tests were executed
  separately above to keep one test process (devcheck's default test dispatcher
  can use multiple workers). Python compilation and built-in secret checks ran.
  Missing tools: ruff, ast-grep, shellcheck and gitleaks; their checks were skipped
  by devcheck. No packages installed in system/service Python.
- `git diff --check` — passed.

Coordinator priority: recheck R1 and C2 against current core, repair C1 with an
explicit encoding-version decision, then run these independent tests and promote
the defect reproductions into intended-behavior tests after core fixes. This pass
does not certify real-model accuracy, fleet placement, cross-platform bit identity,
or the completeness of author-written checks.

## Coordinator verification after integration

The baseline reproductions above remain historical evidence. The coordinator
verified C1, C2 and R1 closed in an immutable newer source snapshot: the rational
and literal record have distinct canonical forms; both orders of conflicting
normalized aliases are rejected; fake answers `[1, 1, 8]` reach acceptance on
three fresh calls with no cached attempts. This does not remove replay support.

Tested source SHA-256 values:
- `symblic/kernel/language.py`: `bc3244f7afd5a4b442243b9b9ce71984e3286711c022cd24e55096dbfc878444`
- `symblic/kernel/run.py`: `0c016ac26bd66430f3beac751a07ea228f34208a7087b0c44fb0aa692d066dd8`

The 13 new contract tests and 10 new offline statistics tests passed together
in one isolated process. They also passed against a later immutable core
snapshot after geometry version 2 was added. These checks use synthetic inputs
and establish these observed boundaries, not real-model correctness.
