# symblic/inquiry: which check should run next?

**What this package explores.** When a claim has been checked once, what is the next check worth running?
Running the same check again, or asking a different model the same question, does not by itself add
evidence. This package makes "a different kind of check" operational: a candidate method is worth running
only if it would catch a declared fault that no used method catches, or tell apart two declared alternative
explanations that no used method tells apart, within budget and with its dependencies current.

**Status: prototype.** The planner is pure, deterministic and covered by 29 unit tests, all on synthetic
fixtures (`example()` builds one). This repository contains no evaluation of it on real research questions.

## The module

| Module | What it does |
| --- | --- |
| `selection.py` | `plan(assessment)` returns a recommendation and a per-method table; `example()` builds a synthetic assessment; `loads(raw)` reads JSON strictly (no duplicate keys, no floats); `digest`, `scope_digest` and `method_digest` pin records. |

An *assessment* holds one claim, its scope (finite fault fixtures and alternative definitions, each pinned by a
SHA-256), candidate methods (with their acquisition, interpretation and assumption dependencies, admission and
cost), receipts of checks already performed, a budget, and the current support and inquiry status. `plan()`:

1. refuses anything malformed, stale (a receipt recorded against another scope or method revision) or out of
   bounds, with a stable `InquiryError.code` and `.path`;
2. computes the baseline: faults caught and alternative pairs distinguished by the receipts already used;
3. for each method, lists the reasons it is not eligible (`not_authorized`, `unavailable`, `cost_unknown`,
   `over_budget`, `stale_dependencies`, `no_measured_gain`) and what it would newly cover;
4. keeps every eligible method on the Pareto frontier of (new coverage by set inclusion, cost), and picks the
   first by stable ID, with no hidden scalar trade-off;
5. reports dependencies shared between methods. Independence is never assumed.

The output always says `"authorizes_execution": false`. Nothing here runs a method, writes a file or changes
a claim; whoever runs the recommendation must check authorization, budget and pins again.

## Command line

```
python3 -m symblic.inquiry.selection example > assessment.json
python3 -m symblic.inquiry.selection plan assessment.json
```

`plan` reads at most 1 MiB from a regular file (no symlinks, no standard input) and prints JSON; refused input
exits with status 1.

## Outside this package

`integration/host/symblic_inquiry_api.py` is the original host's two HTTP routes (`inquiry/example`,
`inquiry/plan`) around the same functions. It only needs a request handler, but it was mounted behind the
host's access gate, so it is kept with the other host files.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/inquiry -t .
```

Run from the repository root. Pure tests; no files outside temporary directories, no model, no network.

Further reading: `docs/reference/INQUIRY.md`.
