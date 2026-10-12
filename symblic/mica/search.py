"""MICA core: the bounded construction search (MicaRun) that turns a checked request into a JavaScript artifact.

What it is for
    Given a validated request (objective, requirements, exported function signatures, public tests, budget) and an
    inventory of local models, MicaRun asks a model for a contract graph (a decomposition into small units),
    validates it, constructs each unit through native Symblic asks (or a deterministic constructor, or a rechecked
    library component), checks every unit with its examples, assembles the program, and runs the original public
    acceptance tests. Failed branches may be repaired or replaced within the budget. Six modes (direct, static,
    decompose_on_failure, capability, search, mica) switch these factors on and off for experiments.

Status: measured machinery. Every decision and call is journaled and can be replayed; tested with fake applicators.
Real local-model runs in the original system exhausted their budgets without an accepted artifact, so no
construction success is claimed (see README.md).

Depends on: symblic.kernel (language, json_schema), symblic.graph.run (the durable call journal), symblic.js
(the JavaScript checker), symblic.spec.contracts and the other symblic.mica modules. Run by cli.py, project.py,
forge.py and promote.py.

Details
    Bounded contract-assembly search over the existing Symblic runtime.

    Models propose plans and source. Code validates graphs, runs independent checks,
    preserves immutable attempts, and decides adoption. No worker starts on import.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import concurrent.futures
import fcntl
import json
import os
import threading
import time
import uuid
from pathlib import Path

from symblic.kernel import language as S
from symblic.graph import run as D
from symblic.js import check as JS
from symblic.js import contract as JSC
from symblic.spec import contracts as SC
from symblic.mica import contracts as C
from symblic.mica import native as N
from symblic.mica import routing as R
from symblic.mica import library as L
from symblic.mica import deterministic as K
from symblic.mica import refinement as F
from symblic.mica import calibration as H
from symblic.mica import bundle as B
from symblic.mica import costs as T
from symblic.mica import strategy as Q
from symblic.kernel import json_schema as J

from symblic.mica import source_identity as I

# The modules whose exact source a construction result depends on. Their digests (keyed by repository path, for
# example 'symblic/mica/search.py') go into every run manifest; a change after import refuses to run.
_CORE_MODULES = ("symblic.mica.search", "symblic.mica.contracts", "symblic.mica.native", "symblic.mica.routing",
                 "symblic.mica.library", "symblic.mica.deterministic", "symblic.mica.refinement",
                 "symblic.mica.calibration", "symblic.mica.bundle", "symblic.mica.costs", "symblic.mica.strategy",
                 "symblic.kernel.json_schema")
# Run records written before the package layout named the cost meter by its old flat file name.
_COST_SOURCES = ("symblic/mica/costs.py", "symblic_mica_costs.py")


def _core_sources():
    """{repository path: sha256 of the bytes on disk} for every core module."""
    modules = __import__('sys').modules
    return {I.relative_path(modules[name].__file__): I.file_sha256(modules[name].__file__) for name in _CORE_MODULES}


_CORE_SOURCES = _core_sources()
VERSION = 1
MODES = ("direct", "static", "decompose_on_failure", "capability", "search", "mica")


class MicaError(ValueError):
    """A construction refused before or during a run (invalid input, changed code, unsafe path)."""


def _put(root, name, value):
    return N._put_once(root, name, value)


def _read(root, name):
    return D._unseal(D._read(Path(root) / name))


def _exists(root, name):
    path = Path(root) / name
    return path.exists() or path.is_symlink()


def verify_host_costs(report, folder, runtime=None):
    """Check terminal measurements against their retained, sealed cost journals.

    A planned receipt is a snapshot and may predate later explicit execution.
    Older uninstrumented results have no cost claim to validate here.
    """
    root = Path(folder)
    if runtime is None and _exists(root, "mica-manifest.json"):
        runtime = _read(root, "mica-manifest.json").get("identity", {})
    required = any(name in (runtime or {}).get("sources", {}) for name in _COST_SOURCES)
    if "host_costs" not in report:
        if required:
            raise MicaError("Instrumented construction result is missing its cost summary.")
        return
    if report.get("status") in ("planned", "unknown", "stopped"):
        return  # In-progress snapshot; later explicit execution can add journal rows.
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise MicaError("Redirected cost journal refused.")
    view = MicaRun.__new__(MicaRun)
    view.root = root
    summaries = [T.summarize(view._events_locked())]
    D._safe_listing(root / "attempts", 5000)
    for path in sorted((root / "attempts").iterdir()):
        if path.is_symlink() or not path.is_dir():
            raise MicaError("Invalid cost attempt directory.")
        summaries.append(N.cost_summary(path))
    if report["host_costs"] != T.combine(summaries):
        raise MicaError("Construction cost summary differs from its retained journals.")


def implementation_identity():
    """The construction implementation a result depends on; refuses when any core module changed since import."""
    problems = I.audit(_CORE_SOURCES)
    try:
        current = _core_sources()
    except I.IdentityError:
        current = None
    if problems or current != _CORE_SOURCES:
        raise MicaError("MICA source and executing implementation differ; start a fresh worker.")
    return {"version": VERSION, "kernel": S.kernel_id(), "sources": current,
            "spec_contracts": SC.VERSION, "javascript": JS.VERSION,
            "module_compiler": B._module_runtime(None)}


def verify_result_artifacts(result, request, runtime):
    """Read-only linkage checks shared by branch recovery and final-result readers."""
    if result.get('status') != 'done':
        return
    request = C.normalize_request(request)
    manifest = result.get('manifest')
    if manifest is None or result.get('checks', {}).get('passed') is not True:
        raise MicaError('Completed construction is missing its assembly or checks.')
    SC.verify_manifest(manifest, runtime_identity=runtime)
    if result.get('output') != manifest['output']:
        raise MicaError('Completed output differs from its accepted assembly.')
    bundle, receipt = result.get('bundle'), result.get('module_checks')
    if request['artifact_format'] == 'javascript_script':
        if bundle is not None or receipt is not None:
            raise MicaError('A script result cannot substitute a module artifact.')
        return
    if bundle is None or type(receipt) is not dict:
        raise MicaError('Completed module construction is missing its bundle or checks.')
    B.verify_bundle(bundle, runtime_identity=runtime)
    if bundle['request'] != request or bundle['spec_manifest'] != manifest:
        raise MicaError('Module bundle is detached from the original request or accepted assembly.')
    cases = B._cases(bundle)
    rows = receipt.get('module_checks')
    if (receipt.get('bundle_sha256') != bundle['sha256'] or receipt.get('status') != 'passed'
            or receipt.get('scope') != B.SCOPE or receipt.get('runtime_status') != 'completed'
            or receipt.get('stage') != 'strict_module_examples' or receipt.get('passed') is not True
            or receipt.get('total') != len(cases) or type(rows) is not list or len(rows) != len(cases)):
        raise MicaError('Module execution receipt is missing or detached from this bundle.')
    for case, row in zip(cases, rows):
        if (type(row) is not dict or any(row.get(k) != case[k] for k in ('scope', 'unit_id', 'call', 'expected'))
                or row.get('passed') is not True or type(row.get('observation')) is not dict
                or row['observation'].get('ok') is not True):
            raise MicaError('Module receipt does not cover every original case.')
        try:
            if not JS.same(JS._parse(row['observation']['value']), JS._parse(case['expected'])):
                raise ValueError('different value')
        except (ValueError, TypeError, KeyError):
            raise MicaError('Module receipt value does not support its recorded grade.') from None


def proposal_to_plan(request, proposal, ident="plan"):
    """Expand a small model proposal into the explicit, fail-closed contract IR."""
    if type(proposal) is not dict or set(proposal) - {"units", "assumptions"}:
        raise MicaError("Plan proposal must contain units and optional assumptions only.")
    if type(proposal.get("units")) is not list:
        raise MicaError("Plan proposal has no units list.")
    by_export = {}
    for unit in proposal["units"]:
        required = {"id", "names", "heading", "body", "uses", "examples", "requirements"}
        if type(unit) is not dict or not required <= set(unit) or set(unit) - required - {"construction", 'output_path'}:
            raise MicaError("Every unit must declare id, names, heading, body, uses, examples and requirements.")
        if type(unit["names"]) is not list or type(unit["uses"]) is not list:
            raise MicaError("Unit names and uses must be lists.")
        for name in unit["names"]:
            if type(name) is not str or name in by_export:
                raise MicaError("Unit exports must have unique text names.")
            by_export[name] = unit["id"]
    contracts = []
    for unit in proposal["units"]:
        if 'output_path' in unit and request.get('artifact_format', 'javascript_script') != 'javascript_modules':
            raise MicaError('Explicit unit output paths require module artifact format.')
        if any(name not in by_export for name in unit["uses"]):
            raise MicaError("Every used helper must be a declared dependency export.")
        contracts.append({**({"construction": unit["construction"]} if "construction" in unit else {}),
                          **({'output_artifacts': [unit['output_path']]} if 'output_path' in unit else {}),
                          "contract_id": unit["id"], "parent_contract_id": "root",
                          "root_requirement_ids": unit["requirements"], "objective": unit["body"],
                          "dependency_contract_ids": sorted({by_export[name] for name in unit["uses"]}),
                          "unit": {key: unit[key] for key in ("names", "heading", "body", "uses", "examples")}
                          | {"setup": ""},
                          "verification_obligations": [{"kind": "unit_examples", "requirement_ids": unit["requirements"]}]})
    return C.validate_plan(request, {"version": 1, "id": ident,
                                    "assumptions": proposal.get("assumptions", []), "contracts": contracts})


def direct_plan(request):
    """The one-unit plan of the `direct` mode: the whole program as a single contract."""
    names = [item["name"] for item in request["exports"]]
    return proposal_to_plan(request, {"units": [{"id": "whole", "names": names,
        "heading": ", ".join(item["signature"] for item in request["exports"]),
        "body": request["objective"] + "\n" + "\n".join(item["text"] for item in request["requirements"]),
        "uses": [], "examples": [[item["call"], item["expected"]] for item in request["tests"]],
        "requirements": [item["id"] for item in request["requirements"]]}], "assumptions": []}, "direct")


def proposal_schema(request, *, refinement=False):
    """Bounded provider wire shape; full graph/authority checks still decide adoption."""
    if refinement and request['budget']['max_units'] < 2:
        raise C.ContractError('RESOURCE_EXHAUSTION', 'The original unit budget cannot admit a refinement helper.')
    text = {'type': 'string'}
    def obj(fields):
        return {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}
    def array(items, minimum=0, maximum=None):
        return {'type': 'array', 'items': items, 'minItems': minimum,
                **({'maxItems': maximum} if maximum is not None else {})}
    names = array(text, maximum=128)
    bound = {'type': 'integer', 'minimum': -K.MAX_ABSOLUTE_BOUND, 'maximum': K.MAX_ABSOLUTE_BOUND}
    limits = obj({'lo': bound, 'hi': bound})
    construction = {'kind': {'const': K.KIND},
        'parameters': array(obj({'name': text, 'lo': bound, 'hi': bound}), 1, K.MAX_PARAMETERS),
        'coefficient_bounds': array(limits, 1, K.MAX_PARAMETERS), 'intercept_bounds': limits}
    construction_schema = {'anyOf': [{'type': 'null'}, obj(construction), obj({**construction, 'version': {'const': K.VERSION}})]}
    unit = {'id': text, 'names': array(text, 1, 128), 'heading': text, 'body': text,
            'uses': names, 'examples': array(array(text, 2, 2), 0 if refinement else 1, 256), 'requirements': array(text, 1, 128)}
    variants = [obj(unit), obj({**unit, 'construction': construction_schema})]
    if not refinement and request.get('artifact_format') == 'javascript_modules':
        variants.extend([obj({**unit, 'output_path': text}),
                         obj({**unit, 'construction': construction_schema, 'output_path': text})])
    units = array({'anyOf': variants}, 2 if refinement else 1, request['budget']['max_units'])
    return J.admit({'anyOf': [obj({'units': units}), obj({'units': units, 'assumptions': names})]})


def plan_prompt(request, *, feedback=None, previous=None, depth=0):
    """The planner prompt (JSON text) asking a model for a decomposition of `request` into units."""
    guide = {"role": "Design an executable decomposition for small local models.",
             "objective": request["objective"], "requirements": request["requirements"],
             "exports": request["exports"], "public_acceptance": request["tests"],
             "artifact_format": request.get('artifact_format', 'javascript_script'),
             "allowed_outputs": request['allowed_outputs'],
             "max_units": request["budget"]["max_units"], "depth": depth,
             "output_format": {"top_level_keys": ["assumptions", "units"],
                 "assumptions": "array of explicit task-specific assumptions; empty when none",
                 "units": "nonempty array of objects with the following fields",
                 "unit_fields": {"id": "unique identifier", "names": "array of function names this unit defines",
                     "heading": "exact function signature(s)", "body": "precise task-specific behavior, including boundary/error cases",
                     "uses": "array of exact function names exported by other units; empty if independent",
                     "examples": "nonempty array of [JavaScript call expression, expected JSON text] pairs derived from the task",
                     "requirements": "nonempty array of exact original requirement IDs",
                     "output_path": "optional for javascript_modules only: an exact allowed_outputs path after the first entry; omitted defaults to units/<id>.js",
                     "construction": "optional declared deterministic strategy from the catalogue below; omit otherwise"}},
             "deterministic_catalogue": {
                 "affine_integer_v1": {"when": "One independent integer affine function with an explicitly bounded input domain in the requirements.",
                     "fields": {"kind": "affine_integer_v1",
                         "parameters": "1..4 objects with name, lo, hi; exact integer input bounds",
                         "coefficient_bounds": "one {lo,hi} integer coefficient range per parameter",
                         "intercept_bounds": "{lo,hi} integer constant range"},
                     "limits": "At most 4096 coefficient tuples and 32 direct integer-literal examples; no dependencies.",
                     "meaning": "Native exhaustive determination must find one unique tuple in this declared family; independent checks still apply."}},
             "rules": ["Return one raw JSON object without a fence or wrapper, no source code or commands.",
                       "The response itself has only assumptions and units. Do not echo this prompt or its schema descriptions.",
                       "Create real task-specific function names, requirements and examples; no placeholder sample program.",
                       "Preserve every root requirement and the exact public export signatures.",
                       "Every unit needs nonempty executable JavaScript example expressions and expected JSON text.",
                       "Examples are proposals; original independent acceptance remains authoritative.",
                       "Use exact top-level function declarations; nest internal helpers. Declare every helper dependency by name in uses.",
                       "No cyclic task dependencies, filesystem operations, tools, deployment, network, or hidden state.",
                       "For javascript_modules the first allowed_outputs path is the generated public entry, never a unit. Assign each additional declared path to exactly one unit using output_path. These are artifact labels, never file access authority.",
                       "Avoid implementation bodies, reference answers, and unneeded global project context.",
                       "Mutually recursive functions belong in one compound unit.",
                       "Different models can need different unit sizes; a larger graph has overhead.",
                       "Start with a few coherent units and concise complete descriptions; failed units can be subdivided later. Avoid repeating the whole objective in every unit.",
                       "Use the deterministic catalogue when its stated domain matches the requirements; never narrow the required input domain to fit a tool.",
                       "A proposed deterministic family is not a correctness proof and cannot remove root checks."]}
    if feedback is not None:
        guide["verified_failure"] = feedback
        guide["repair_instruction"] = "Repair the decomposition or subdivide the failing concern. Keep the root requirements fixed."
    if previous is not None:
        guide["previous_units"] = [{"id": u["contract_id"], "names": u["unit"]["names"],
                                    "body": u["unit"]["body"], "uses": u["unit"]["uses"],
                                    "examples": u["unit"]["examples"],
                                    "requirements": u["root_requirement_ids"]} for u in previous["contracts"]]
    return ("Design the requested program's dependency graph. Return ONLY one raw JSON object, without a fence or wrapper, which "
            "has the keys assumptions and units. Read the supplied requirements and create actual task-specific units. "
            "Do not reproduce this input envelope or the schema descriptions. The output_format below describes "
            "the response fields; it is not an answer to copy.\n\nInput data (not the response):\n" +
            json.dumps(guide, ensure_ascii=False, sort_keys=True))


def failure_class(result):
    """A stable failure category (MODEL_TIMEOUT, TEST_FAILURE, RESOURCE_EXHAUSTION, ...) for a failed result."""
    if result.get("failure") in ("VERIFICATION_UNKNOWN", "RESOURCE_EXHAUSTION", "INTERNAL_ERROR"):
        return result["failure"]
    if result.get("status") == "unknown":
        return "UNRESOLVED_EFFECT"
    err = result.get("error") or {}
    kind = err.get("kind", "") if isinstance(err, dict) else ""
    text = json.dumps(err).lower()
    if kind == "internal":
        return "INTERNAL_ERROR"
    if kind in ("version", "capability", "flow"):
        return "INVALID_CONTRACT"
    if "budget" in text or "exhaust" in text or kind in ("context", "resource"):
        return "RESOURCE_EXHAUSTION"
    if any(marker in text for marker in ("timeout", "timed out", "ran out of time", "curl exit 28")):
        return "MODEL_TIMEOUT"
    if kind == "syntax":
        return "SYNTAX_ERROR"
    if kind == "type":
        return "TYPE_ERROR"
    if kind in ("check", "assert", "ensure") or "test" in text:
        return "TEST_FAILURE"
    return "MODEL_OUTPUT_ERROR"


class MicaRun:
    """One bounded search, with native per-call journaling and deterministic assembly.

    The caller injects an applicators object and an explicit inventory, never a
    model-selected executor. A run owns its directory; concurrent resume waits.
    """
    def __init__(self, request, folder, applicators, inventory, stop=None, *, library=None, calibration=None):
        self.request = C.normalize_request(request)
        self.root = Path(folder)
        self.apps = applicators
        self.inventory = R.normalize_inventory(inventory)
        self.stop = stop or threading.Event()
        self.uncertain = threading.Event()
        self._meter_active = False
        self.lock = threading.RLock()
        self.budget_lock = threading.Lock()
        self.node_locks = {row["node"]: threading.Lock() for row in self.inventory}
        self.budget = self.request["budget"]
        self.calibration = H.normalize(calibration, D._hash(implementation_identity())) if calibration is not None else None
        self.observations = list(self.calibration['observations']) if self.calibration else []
        self.started_monotonic = time.monotonic()
        self.components = {}
        self.escalation = {}
        self.strategy_routes = None
        self.library = L.ComponentLibrary(library) if library is not None else None

    def _measure(self, category, label, function, *args, **kwargs):
        if not self._meter_active:
            return function(*args, **kwargs)
        return T.call(self._event, category, label, function, *args, **kwargs)

    def _events(self):
        with self.lock:
            return self._events_locked()

    def _events_locked(self):
        path = self.root / "mica-events.jsonl"
        rows = D._read(path, lines=True, missing=True)
        previous = None
        for index, row in enumerate(rows):
            D._unseal(row)
            if row.get("sequence") != index or row.get("previous") != previous:
                raise MicaError("Construction event chain is incomplete or reordered.")
            previous = row["sha256"]
        return rows

    def _event(self, kind, **fields):
        with self.lock:
            rows = self._events()
            body = {"sequence": len(rows), "previous": rows[-1]["sha256"] if rows else None,
                    "kind": kind, **fields}
            D._append(StoreProxy(self.root), "mica-events.jsonl", D._seal(body))

    def _allocations(self):
        allocated, settled = {}, set()
        for row in self._events():
            if row["kind"] == "reserve":
                if row["attempt"] in allocated:
                    raise MicaError("Duplicate construction allocation.")
                allocated[row["attempt"]] = row["limit"]
            elif row["kind"] == "settled":
                if (row["attempt"] in settled or row["attempt"] not in allocated
                        or type(row["calls"]) is not int or not 0 <= row["calls"] <= allocated[row["attempt"]]):
                    raise MicaError("Invalid construction allocation settlement.")
                allocated[row["attempt"]] = row["calls"]
                settled.add(row["attempt"])
        return allocated

    def _remaining(self):
        return self.budget["max_calls"] - sum(self._allocations().values())

    def _deadline_expired(self):
        start = _read(self.root, "mica-manifest.json")["started_ms"] / 1000
        now = time.time()
        return (now < start or now - start >= self.budget["wall_seconds"]
                or time.monotonic() - self.started_monotonic >= self.budget["wall_seconds"])

    def _expired(self):
        return self.stop.is_set() or self._deadline_expired()

    def _guard(self):
        if self._deadline_expired():
            return {"status": "exhausted", "calls": 0, "failure": "RESOURCE_EXHAUSTION",
                    "error": "Original construction deadline exhausted."}
        if self.stop.is_set():
            return {"status": "stopped", "calls": 0, "error": "Construction stopped."}
        return None

    def _check_deadline(self, deadline_ms=None):
        root = _read(self.root, "mica-manifest.json")["started_ms"] + self.budget["wall_seconds"] * 1000
        end = min(root, deadline_ms) if deadline_ms is not None else root
        computed = min(time.monotonic() + max(0, end / 1000 - time.time()),
                       self.started_monotonic + self.budget['wall_seconds'])
        return min(computed, getattr(self.stop, 'monotonic_deadline', computed))

    def _native(self, ident, source, route, binding, requested, *, deadline_ms=None, wall_seconds=None, planning=False):
        allowance = self.budget["wall_seconds"] if wall_seconds is None else wall_seconds
        if allowance < 30:
            return {"status": "failed", "calls": 0, "failure": "RESOURCE_EXHAUSTION",
                    "error": "Native provider admission requires a 30-second time slot; this unit allows less."}
        if deadline_ms is not None and time.time() * 1000 >= deadline_ms:
            return self._guard() or {"status": "failed", "calls": 0, "failure": "RESOURCE_EXHAUSTION",
                                    "error": "Original unit deadline exhausted."}
        with self.budget_lock:
            original = next((e for e in self._events() if e["kind"] == "reserve" and e["attempt"] == ident), None)
            allocation = original["limit"] if original else None
            if original and original.get("route") != route:
                raise MicaError("A reserved attempt changed its selected route.")
            if allocation is None:
                if self._expired():
                    return {"status": "exhausted" if self._deadline_expired() else "stopped", "calls": 0,
                            "error": "Construction stopped or original wall-time allowance exhausted."}
                allocation = min(requested, self._remaining())
                if allocation <= 0:
                    return {"status": "exhausted", "calls": 0, "error": "Construction call budget exhausted."}
                self._event("reserve", attempt=ident, limit=allocation, route=route)
        path = self.root / "attempts" / ident
        # The fixed per-attempt limits are frozen; they do not reset on resume.
        limits = {"num_predict": 4096, "num_ctx": 16384,
                  "timeout_seconds": min(900 if planning else 300, allowance),
                  "total_timeout_seconds": allowance}
        # Only one model attempt per physical node in this construction run.
        # The provider still decides whether a call can run now (other processes may share the hosts).
        with self.node_locks[route["node"]]:
            if self.uncertain.is_set() and not _exists(path, "mica-native-result.json"):
                return {"status": "unknown", "calls": 0, "failure": "UNRESOLVED_EFFECT",
                        "error": "Another attempt has an unresolved delivery; new dispatch is blocked."}
            bounded_stop = DeadlineStop(self.stop, deadline_ms) if deadline_ms is not None else self.stop
            result = N.execute(source, path, self.apps, route, limit=allocation,
                               output_binding=binding, stop=bounded_stop, options={"ollama_limits": limits})
            if result["status"] != "unknown" and deadline_ms is not None and time.time() * 1000 >= deadline_ms:
                result = {**result, "status": "failed", "failure": "RESOURCE_EXHAUSTION",
                          "error": "Original unit deadline exhausted."}
            if result["status"] == "unknown":
                self.uncertain.set()
        if result["status"] not in ("unknown", "stopped"):
            settled = [e for e in self._events() if e["kind"] == "settled" and e["attempt"] == ident]
            if not settled:
                self._event("settled", attempt=ident, calls=result["calls"], status=result["status"])
        return result

    def _routes(self, contract, mode):
        inventory = []
        for row in self.inventory:
            row = dict(row)
            if row["digest"] is None:
                observed = [v for v in self.observations if v["model"] == row["model"]
                            and v["node"] == row["node"] and v["digest"] is not None and not v["cached"]
                            and not v["observation_id"].startswith('cal/')]
                if observed:
                    row["digest"] = observed[-1]["digest"]
            inventory.append(row)
        if mode in ("capability", "mica"):
            ranked = self._measure("scheduler", "empirical_model_ranking", R.rank_models, contract, inventory, self.observations)
            rows = [r.get("model", r) if isinstance(r.get("model"), dict) else r.get("route", r) for r in ranked]
        else:
            # Eligibility constraints apply in every ablation. An ablation may
            # change ranking, never provider or contract authority.
            eligible = self._measure("scheduler", "eligible_model_filter", R.rank_models, contract, inventory, [])
            keys = {(r["model"], r["node"], r.get("digest")) for r in eligible}
            rows = [r for r in inventory if (r["model"], r["node"], r.get("digest")) in keys]
        return [{"id": row.get("id", "worker"), "provider": "ollama", "model": row["model"],
                 "node": row["node"], "local": True, "digest": row.get("digest")} for row in rows]

    def _selected(self, ident, proposed):
        reservation = next((e for e in self._events() if e["kind"] == "reserve" and e["attempt"] == ident), None)
        return reservation["route"] if reservation else proposed

    def _propose(self, index, mode, previous=None, feedback=None, *, strategy=None):
        name = f"plan-{index:03}.json"
        if _exists(self.root, name):
            saved = _read(self.root, name)
            return saved["plan"], saved.get("failure")
        target = (feedback or {}).get("contract") if previous else None
        scoped = target and any(c["contract_id"] == target for c in previous["contracts"])
        try:
            prompt = (F.refine_prompt(self.request, previous, target, feedback) if scoped else
                      plan_prompt(self.request, feedback=feedback, previous=previous,
                                  depth=strategy['depth'] if strategy is not None else index))
        except C.ContractError as exc:
            return None, {"status": "exhausted", "failure": "RESOURCE_EXHAUSTION", "error": str(exc)}
        if len(prompt) > self.budget["context_chars"]:
            return None, {"status": "blocked", "failure": "INVALID_CONTRACT", "error": "Planner context exceeds declared budget."}
        routes = self._routes({"objective": self.request["objective"], "model_eligibility": {"task_class": "planning"}}, mode)
        if not routes:
            return None, {"status": "blocked", "failure": "RESOURCE_EXHAUSTION", "error": "No eligible local planner."}
        # Planner selection is recorded and bounded; larger workers are allowed,
        # and their planning cost stays in the same end-to-end budget.
        proposed_route = strategy['planner'] if strategy is not None else routes[index % len(routes)]
        if proposed_route not in routes:
            raise MicaError('Selected strategy planner is not eligible.')
        route = self._selected(f"planner-{index:03}", proposed_route)
        if strategy is not None and route != proposed_route:
            raise MicaError('Reserved planner route differs from the frozen strategy.')
        source = N.planner_source(prompt, route, context_chars=self.budget["context_chars"], schema=proposal_schema(self.request, refinement=bool(scoped)))
        result = self._native(f"planner-{index:03}", source, route, "proposal", 1, planning=True)
        plan, lineage = None, None
        if result["status"] == "done":
            try:
                proposal = D._decode(result["output"].encode())
                if scoped:
                    refined = self._measure("scheduler", "refinement_admission", F.apply_refinement, self.request, previous, target, proposal, f"plan{index}")
                    plan, lineage = refined["plan"], refined["lineage"]
                else:
                    plan = self._measure("scheduler", "proposal_admission", proposal_to_plan, self.request, proposal, f"plan{index}")
                failure = None
            except (ValueError, KeyError, TypeError) as exc:
                failure = {"status": "failed", "failure": "INVALID_CONTRACT", "error": str(exc)[:1500]}
        else:
            failure = {"status": result["status"], "failure": failure_class(result), "error": result.get("error")}
        self._observe(f"planner-{index:03}", {"content_hash": C.digest(self.request),
                      "model_eligibility": {"task_class": "planning"}}, route, result, accepted=plan is not None)
        if result["status"] not in ("unknown", "stopped"):
            _put(self.root, name, {"plan": plan, "failure": failure, "lineage": lineage,
                                   "planner_attempt": f"planner-{index:03}"})
        return plan, failure

    def _escalation_routes(self, contract, mode):
        failed = {(o["model"], o["node"]) for o in self.observations
                  if o["contract_hash"] == contract["content_hash"] and o["status"] != "success" and not o["cached"]
                  and not o["observation_id"].startswith('cal/')}
        return [r for r in self._routes(contract, mode) if (r["model"], r["node"]) not in failed]

    def _sheet_plan(self, plan):
        by_id = {u["contract_id"]: u for u in plan["contracts"]}
        sheet = {"title": "MICA checked construction", "intro": "", "shared": "",
                 "units": [by_id[i]["unit"] for i in plan["order"]],
                 "template": {"file": self.request["allowed_outputs"][0], "text": "/*UNITS*/", "note": ""}}
        return SC.plan(sheet)

    def _scoped_facts(self, contract):
        return {"requirements": [r for r in self.request["requirements"]
                                  if r["id"] in contract["root_requirement_ids"]],
                "exports": [e for e in self.request["exports"] if e["name"] in contract["unit"]["names"]]}

    def _component_contract_hash(self, contract, native_contract_sha256):
        # Spending/routing policy is reapplied on this run. It is not a property
        # of source semantics, so a smaller call allowance can still reuse code.
        semantic = {key: value for key, value in contract.items() if key not in
                    ("content_hash", "resource_budget", "failure_policy", "model_eligibility")}
        return D._hash({"mica": semantic, "native": native_contract_sha256, **self._scoped_facts(contract)})

    def _unit_checks(self, code, contract, deps, deadline_ms):
        guard = self._guard()
        if guard:
            return {**guard, "passed": False}
        if time.time() * 1000 >= deadline_ms:
            return {"passed": False, "failure": "RESOURCE_EXHAUSTION", "report": "Original unit deadline exhausted."}
        surface = self._measure("verification", "unit_surface:"+contract["contract_id"], JSC.check, code, {"version": 1, "exports": {name: "function" for name in contract["unit"]["names"]}},
                            deadline=self._check_deadline(deadline_ms))
        if not surface["passed"]:
            guard = self._guard()
            if guard:
                return {**guard, 'passed': False}
            if surface.get('status') in ('budget', 'error'):
                return {**surface, 'status': 'blocked', 'failure': 'VERIFICATION_UNKNOWN'}
            return {**surface, "failure": "INTERFACE_FAILURE"}
        pieces = ([contract["unit"]["setup"]] if contract["unit"]["setup"] else []) + [d["code"] for d in deps] + [code]
        checked = self._measure("verification", "unit_examples:"+contract["contract_id"], JS.test, pieces, contract["unit"]["examples"], deadline=self._check_deadline(deadline_ms))
        if time.time() * 1000 >= deadline_ms:
            return {**checked, "passed": False, "failure": "RESOURCE_EXHAUSTION", "report": "Original unit deadline exhausted."}
        return checked

    def _prepare_unit(self, plan, index, ident, contract, row, deps, runtime, mode, used_nodes):
        attempt = f"build-{index:03}-{ident}"
        state_file = attempt + ".json"
        old = _read(self.root / "unit-states", state_file) if _exists(self.root / "unit-states", state_file) else None
        state = {"attempt": attempt, "contract_sha256": contract["content_hash"],
                 "started_ms": old["started_ms"] if old else int(time.time() * 1000)}
        _put(self.root / "unit-states", state_file, state)
        deadline_ms = state["started_ms"] + contract["resource_budget"]["wall_seconds"] * 1000
        facts = self._scoped_facts(contract)
        # Complete dependency artifact identity avoids collisions when a helper's
        # contract changes but it happens to emit exactly the previous code.
        contract_hash = self._component_contract_hash(contract, row["contract_sha256"])
        dependency_hashes = [d["artifact_sha256"] for d in deps]
        key = L.identity(contract_hash, dependency_hashes, runtime)
        job = {"ident": ident, "attempt": attempt, "contract": contract, "row": row, "deps": deps,
               "key": key, "contract_hash": contract_hash, "dependency_hashes": dependency_hashes,
               "deadline_ms": deadline_ms, "route": None, "ready": None, "source": None}
        choices = list(self.components.get(key, []))
        if self.library is not None:
            choices += self.library.candidates(key, runtime=runtime)
        for token in choices:
            checked = self._unit_checks(token["code"], contract, deps, deadline_ms)
            if checked.get('failure') in ('VERIFICATION_UNKNOWN', 'RESOURCE_EXHAUSTION') or checked.get('status') in ('blocked', 'stopped', 'exhausted'):
                job['ready'] = {'status': checked.get('status', 'blocked'), 'calls': 0,
                                'failure': checked.get('failure', 'VERIFICATION_UNKNOWN'),
                                'error': checked.get('report', checked.get('error'))}
                return job
            if checked.get("passed"):
                original = token.get("decision") if token.get("origin_attempt") == attempt else None
                job["ready"] = {"status": "done", "output": token["code"], "calls": original["calls"] if original else 0,
                                "reuse": original["reused"] if original else True, "original_decision": original}
                job["route"] = original["route"] if original else None
                return job
        guard = self._guard()
        if guard:
            job["ready"] = guard
            return job
        if contract.get("construction"):
            compiled = K.compile_contract(contract)
            if compiled["status"] == "supported":
                job["kernel"] = compiled
        routes = ([self.strategy_routes[ident]] if self.strategy_routes is not None and self.strategy_routes[ident]
                  else [] if self.strategy_routes is not None else self.escalation.get(ident, self._routes(contract, mode)))
        route = next((r for r in routes if r["node"] not in used_nodes), routes[0] if routes else None)
        route = self._selected(attempt, route)
        if self.strategy_routes is not None and route != self.strategy_routes[ident]:
            raise MicaError('Reserved unit route differs from the frozen strategy.')
        job["route"] = route
        if route:
            used_nodes.add(route["node"])
            try:
                job["source"] = N.unit_source(contract, deps, route, retries=contract["failure_policy"]["retries"],
                    context_chars=contract["resource_budget"]["context_chars"], **facts)
            except N.NativeError as exc:
                job["model_refusal"] = {"status": "failed", "calls": 0, "failure": "RESOURCE_EXHAUSTION", "error": str(exc)}
        elif "kernel" not in job:
            job["ready"] = {"status": "blocked", "calls": 0, "failure": "RESOURCE_EXHAUSTION",
                            "error": ("Cached component failed checks and no eligible worker is available." if choices
                                      else "No checked reusable component or eligible local worker.")}
        return job

    def _construct_unit(self, job):
        if job["ready"] is not None:
            return job["ready"]
        contract = job["contract"]
        guard = self._guard()
        if guard:
            return guard
        if "kernel" in job:
            compiled = job["kernel"]
            result = N.execute_kernel(compiled["source"], self.root / "attempts" / (job["attempt"] + "-kernel"),
                output_binding=compiled["output_binding"], options=compiled["options"],
                stop=DeadlineStop(self.stop, job["deadline_ms"]))
            if result["status"] != "unknown" and time.time() * 1000 >= job["deadline_ms"]:
                return {**result, "status": "failed", "failure": "RESOURCE_EXHAUSTION", "strategy": "native_finite",
                        "error": "Original unit deadline exhausted during finite construction."}
            if result["status"] in ("done", "stopped", "unknown"):
                return {**result, "strategy": "native_finite", "construction_scope": compiled.get("scope")}
            job["kernel_failure"] = {"status": result["status"], "error": result.get("error")}
            if contract["failure_policy"]["action"] == "stop":
                return {**result, "strategy": "native_finite"}
        if "model_refusal" in job:
            return job["model_refusal"]
        if job["route"] is None:
            return {"status": "failed", "calls": 0, "failure": "VERIFICATION_UNKNOWN",
                    "error": "Finite construction did not find a unique solution and no local fallback is eligible."}
        result = self._native(job["attempt"], job["source"], job["route"], "candidate",
            min(contract["resource_budget"]["max_calls"], contract["failure_policy"]["retries"] + 1),
            deadline_ms=job["deadline_ms"], wall_seconds=contract["resource_budget"]["wall_seconds"])
        return {**result, "strategy": "local_model", "kernel_failure": job.get("kernel_failure")}

    def _build(self, plan, index, mode):
        guard = self._guard()
        if guard:
            return guard
        spec = self._measure("assembly", "native_sheet_plan", self._sheet_plan, plan)
        by_id = {u["contract_id"]: u for u in plan["contracts"]}
        by_export = {name: c for c in plan["contracts"] for name in c["unit"]["names"]}
        spec_by_contract = {by_export[u["exports"][0]]["contract_id"]: u for u in spec["units"]}
        artifacts, decisions = {}, []
        runtime = implementation_identity()
        for layer in plan["layers"]:
            for offset in range(0, len(layer), self.budget["max_workers"]):
                guard = self._guard()
                if guard:
                    return {**guard, "decisions": decisions}
                batch = layer[offset:offset + self.budget["max_workers"]]
                jobs, used_nodes = [], set()
                for ident in batch:
                    contract, row = by_id[ident], spec_by_contract[ident]
                    deps = []
                    for dep in row["closure"]:
                        parent = next(r for r in spec["units"] if r["id"] == dep)
                        parent_contract = by_export[parent["exports"][0]]
                        deps.append({"unit_id": dep, "code": artifacts[dep]["code"],
                            "code_sha256": artifacts[dep]["code_sha256"], "artifact_sha256": artifacts[dep]["sha256"],
                            "contract": parent_contract, **self._scoped_facts(parent_contract)})
                    jobs.append(self._prepare_unit(plan, index, ident, contract, row, deps, runtime, mode, used_nodes))
                # Preflight every card before dispatch; expected context refusals
                # are structured outcomes and cannot abandon parallel receipts.
                for job in jobs:
                    if (job["ready"] is None and "model_refusal" not in job and "kernel" not in job
                            and job["route"] is not None and job["attempt"] not in self._allocations() and not self._expired()):
                        contract = job["contract"]
                        limit = min(contract["resource_budget"]["max_calls"], contract["failure_policy"]["retries"] + 1, self._remaining())
                        if limit > 0:
                            self._event("reserve", attempt=job["attempt"], limit=limit, route=job["route"])
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(jobs))) as pool:
                    futures = [pool.submit(self._construct_unit, job) for job in jobs]
                    outcomes = [future.result() for future in futures]
                failures = []
                for job, outcome in zip(jobs, outcomes):
                    contract, row, deps, key = (job[k] for k in ("contract", "row", "deps", "key"))
                    if outcome["status"] not in ("unknown", "stopped") and job["attempt"] in self._allocations():
                        if not any(e["kind"] == "settled" and e["attempt"] == job["attempt"] for e in self._events()):
                            self._event("settled", attempt=job["attempt"], calls=outcome["calls"], status=outcome["status"])
                    route = None if outcome.get("strategy") == "native_finite" else job["route"]
                    decision = outcome.get("original_decision") or {
                        "contract": job["ident"], "attempt": job["attempt"], "status": outcome["status"],
                        "calls": outcome["calls"], "reused": outcome.get("reuse", False), "route": route,
                        "strategy": outcome.get("strategy", "component_reuse"), "kernel_failure": outcome.get("kernel_failure")}
                    decisions.append(decision)
                    if outcome["status"] != "done":
                        self._observe(job["attempt"], contract, route, outcome, accepted=False)
                        failures.append({"status": outcome["status"], "failure": outcome.get("failure", failure_class(outcome)),
                                         "contract": job["ident"], "error": outcome.get("error")})
                        continue
                    code = outcome["output"]
                    checked = self._unit_checks(code, contract, deps, job["deadline_ms"])
                    if (not outcome.get("original_decision")
                            and checked.get('failure') not in ('VERIFICATION_UNKNOWN', 'RESOURCE_EXHAUSTION')
                            and checked.get('status') not in ('stopped', 'blocked', 'exhausted')):
                        self._observe(job["attempt"], contract, route, outcome, accepted=checked.get("passed") is True)
                    if not checked.get("passed"):
                        failures.append({"status": checked.get("status", "failed") if checked.get("status") in ("exhausted", "stopped", 'blocked') else "failed",
                                         "failure": checked.get("failure", "TEST_FAILURE"), "contract": job["ident"],
                                         "error": checked.get("report", checked.get("error"))})
                        continue
                    artifacts[row["id"]] = SC.record_artifact(spec, row["id"], code, artifacts,
                        runtime_identity=runtime, checks=[{"scope": "exact_function_surface_and_encoded_unit_examples", "passed": True,
                                                          "subject_sha256": SC.code_hash(code)}])
                    _put(self.root / "decisions", job["attempt"] + ".json", decision)
                    token = {"key": key, "code": code, "artifact": artifacts[row["id"]], "assurance": "TESTED",
                             "runtime": runtime, "origin_attempt": job["attempt"], "decision": decision}
                    name = key + "-" + SC.code_hash(code) + ".json"
                    if not _exists(self.root / "components", name):
                        _put(self.root / "components", name, token)
                        self.components.setdefault(key, []).append(token)
                    if self.library is not None:
                        self.library.publish(contract_sha256=job["contract_hash"],
                            dependency_hashes=job["dependency_hashes"], runtime=runtime, code=code)
                if failures:
                    failure = next((f for f in failures if f["status"] == "unknown"),
                                   next((f for f in failures if f["status"] == "stopped"),
                                   next((f for f in failures if f['status'] in ('blocked', 'exhausted')), failures[0])))
                    policy = by_id[failure["contract"]]["failure_policy"]["action"]
                    return {**failure, "decisions": decisions, "failures": failures, "failure_policy": policy}
        guard = self._guard()
        if guard:
            return {**guard, "decisions": decisions}
        manifest = self._measure("assembly", "artifact_manifest", SC.artifact_manifest, spec, artifacts, runtime_identity=runtime)
        output = manifest["output"]
        surface = self._measure("verification", "assembled_surface", JSC.check, output["text"], {"version": 1, "exports": {
            name: "function" for contract in plan["contracts"] for name in contract["unit"]["names"]}},
            deadline=self._check_deadline())
        if not surface["passed"]:
            guard = self._guard()
            if guard:
                return {**guard, 'decisions': decisions}
            if surface.get('status') in ('budget', 'error'):
                return {'status': 'blocked', 'failure': 'VERIFICATION_UNKNOWN', 'error': surface['report'], 'decisions': decisions}
            return {"status": "failed", "failure": "INTERFACE_FAILURE", "error": surface["report"], "decisions": decisions}
        for contract in plan["contracts"]:
            guard = self._guard()
            if guard:
                return {**guard, "decisions": decisions}
            checked = self._measure("verification", "integration:"+contract["contract_id"], JS.test, ([contract["unit"]["setup"]] if contract["unit"]["setup"] else []) + [output["text"]],
                              contract["unit"]["examples"], deadline=self._check_deadline())
            if not checked.get("passed"):
                return self._guard() or {"status": "failed", "failure": "INTEGRATION_FAILURE", "contract": contract["contract_id"],
                        "error": checked.get("report"), "decisions": decisions}
        root_checks = self._measure("verification", "root_acceptance", JS.test, output["text"], [[t["call"], t["expected"]] for t in self.request["tests"]],
                              deadline=self._check_deadline())
        guard = self._guard()
        if guard:
            return {**guard, "decisions": decisions}
        if not root_checks.get("passed"):
            return {"status": "failed", "failure": "INTEGRATION_FAILURE", "error": root_checks.get("report"),
                    "decisions": decisions, "checks": root_checks}
        if any(r["acceptance"] == "PROVEN" for r in self.request["requirements"]):
            return {"status": "blocked", "failure": "VERIFICATION_UNKNOWN", "decisions": decisions,
                    "error": "Finite refinement receipts do not prove emitted JavaScript implements prose requirements.", "checks": root_checks}
        extra = {}
        if self.request['artifact_format'] == 'javascript_modules':
            try:
                bundle = self._measure("assembly", "module_compile", B.compile_bundle, self.request, plan, artifacts, runtime_identity=runtime,
                                          spec_plan=spec, deadline=self._check_deadline())
                module_checks = self._measure("verification", "actual_module_bundle", B.check_bundle, bundle, deadline=self._check_deadline())
            except B.BundleError as exc:
                guard = self._guard()
                if guard:
                    return {**guard, 'decisions': decisions}
                inconclusive = exc.code in ('budget', 'unsupported', 'version')
                return {"status": "blocked" if inconclusive else "failed",
                        "failure": "VERIFICATION_UNKNOWN" if inconclusive else "INTEGRATION_FAILURE",
                        "error": str(exc), "decisions": decisions, "checks": root_checks}
            if not module_checks['passed']:
                guard = self._guard()
                if guard:
                    return {**guard, 'decisions': decisions}
                inconclusive = module_checks['status'] in ('unsupported', 'inconclusive')
                return {"status": "blocked" if inconclusive else "failed",
                        "failure": "VERIFICATION_UNKNOWN" if inconclusive else "INTEGRATION_FAILURE",
                        "error": 'Actual module bundle did not pass its independent checks.',
                        "decisions": decisions, "checks": root_checks, "module_checks": module_checks}
            extra = {'bundle': bundle, 'module_checks': module_checks}
        guard = self._guard()
        if guard:
            return {**guard, 'decisions': decisions}
        return {"status": "done", "output": output, "manifest": manifest, "checks": root_checks, **extra,
                "decisions": decisions, "assurance": "TESTED", "formal_correctness": "not_established"}

    def _audit_native(self):
        """No later uncertain parallel unit may hide behind an earlier retry."""
        D._safe_listing(self.root / "attempts", 5000)
        uncertain = []
        for path in sorted((self.root / "attempts").iterdir()):
            if _exists(path, "mica-native-pins.json"):
                inspection = N.inspect_attempt(path)
                if inspection["status"] == "unknown":
                    uncertain.append(path.name)
            elif not path.is_dir() or path.is_symlink() or any(path.iterdir()):
                raise MicaError("Unpinned native attempt data requires inspection.")
        return uncertain

    def plan(self, mode="mica"):
        """Freeze a checked proposal using the same budget and manifest as execution."""
        return self.execute(mode, plan_only=True)

    def _strategy_decision(self, index, mode, initial_plans, *, phase='choice'):
        """Reconstruct a choice from its exact pre-dispatch event prefix.

        Later observations cannot rerank a pending/resumed attempt. All graph
        authority and eligible routes are recomputed from frozen root controls;
        an edited/resealed receipt therefore cannot grant another worker/effect.
        """
        history, plans, known = [], [], set()
        def admit(plan, depth):
            if plan is None:
                return
            admitted = C.validate_plan(self.request, plan)
            if admitted['content_hash'] not in known:
                known.add(admitted['content_hash'])
                plans.append({'plan': admitted, 'depth': depth})
        if len(initial_plans or []) > self.budget['max_candidates']:
            raise MicaError('Explicit alternatives exceed the original candidate bound.')
        for plan in initial_plans or []:
            admit(plan, 0)
        for i in range(index):
            prior = _read(self.root, f'strategy-{i:03}.json')
            branch = _read(self.root, f'branch-{i:03}.json')
            if (branch.get('strategy_sha256') != prior['sha256'] or
                    branch.get('root_request_sha256') != C.digest(self.request)):
                raise MicaError('A branch is detached from its original strategy.')
            choice = prior['selected']
            if choice is None:
                raise MicaError('A branch follows an empty strategy frontier.')
            build_choice = (_read(self.root, f'strategy-{i:03}-build.json')['selected']
                            if choice['kind'] != 'build' and _exists(self.root, f'strategy-{i:03}-build.json') else None)
            applied = build_choice or choice
            if applied['kind'] == 'build' and (branch['plan'] or {}).get('content_hash') != applied['plan_sha256']:
                raise MicaError('A strategy branch substituted another graph.')
            admit(branch['plan'], choice['depth'])
            history.append({'choice': choice, 'build_choice': build_choice, 'plan': branch['plan'], 'result': branch['result']})
        if phase == 'build':
            primary = _read(self.root, f'strategy-{index:03}.json')['selected']
            saved_plan = _read(self.root, f'plan-{index:03}.json')
            if primary is None or primary['kind'] == 'build' or saved_plan.get('failure') is not None:
                raise MicaError('Build strategy has no admitted expansion.')
            expanded = C.validate_plan(self.request, saved_plan['plan'])
            # Recover the proposal from its existing native receipt and replay
            # only the pure admission step, including unchanged wrapper authority.
            native = _read(self.root / 'attempts' / f'planner-{index:03}', 'mica-native-result.json')
            proposal = D._decode(native['output'].encode())
            if primary['kind'] == 'refine':
                parent = next(r['plan'] for r in plans if r['plan']['content_hash'] == primary['parent_plan_sha256'])
                expected = F.apply_refinement(self.request, parent, primary['trigger']['contract'], proposal,
                                              f'plan{index}')['plan']
            else:
                expected = proposal_to_plan(self.request, proposal, f'plan{index}')
            if native['status'] != 'done' or expanded != expected:
                raise MicaError('Expanded graph differs from its native proposal and original authority.')
            plans = [{'plan': expanded, 'depth': primary['depth']}]
        name = f'strategy-{index:03}' + ('-build' if phase == 'build' else '') + '.json'
        saved = _read(self.root, name) if _exists(self.root, name) else None
        events = self._events()
        count = saved['event_prefix']['count'] if saved else len(events)
        if type(count) is not int or not 0 <= count <= len(events):
            raise MicaError('Strategy event prefix is missing or invalid.')
        prefix = events[:count]
        prefix_pin = {'count': count, 'head': prefix[-1]['sha256'] if prefix else None}
        observations = (list(self.calibration['observations']) if self.calibration else []) + [
            e['observation'] for e in prefix if e['kind'] == 'observation']
        decision = Q.decide(self.request, plans, history, self.inventory, observations, mode, index,
                            build_only=phase == 'build')
        decision.update(event_prefix=prefix_pin, inventory_sha256=R.digest(self.inventory),
                        history_sha256=D._hash(history))
        if saved and {k: v for k, v in saved.items() if k != 'sha256'} != decision:
            raise MicaError('Retained strategy differs from its frozen controls and observations.')
        receipt = saved or _put(self.root, name, decision)
        anchors = [e for e in events if e['kind'] == 'strategy_choice' and e.get('file') == name]
        if anchors:
            if (len(anchors) != 1 or anchors[0].get('decision_sha256') != receipt['sha256'] or
                    anchors[0].get('event_prefix') != prefix_pin or anchors[0]['sequence'] < count):
                raise MicaError('Strategy choice differs from its pre-dispatch ledger anchor.')
        else:
            # A crash can separate the immutable file write from its anchor.
            # Only bookkeeping may follow that prefix before we finish anchoring;
            # dispatch/observation/effect history in the gap is never guessed safe.
            if saved and any(e['kind'] not in ('cost_started', 'cost_finished') for e in events[count:]):
                raise MicaError('Unanchored strategy has later execution evidence.')
            self._event('strategy_choice', file=name, decision_sha256=receipt['sha256'], event_prefix=prefix_pin)
        return receipt, {row['plan']['content_hash']: row['plan'] for row in plans}

    def _strategy_audit(self, mode, initial_plans):
        if mode not in ('mica', 'search'):
            return None
        allowed = {f'strategy-{i:03}{suffix}.json' for i in range(self.budget['max_candidates']) for suffix in ('', '-build')}
        for anchor in (e for e in self._events() if e['kind'] == 'strategy_choice'):
            if anchor.get('file') not in allowed or not _exists(self.root, anchor['file']):
                raise MicaError('A strategy ledger anchor lost its bounded decision file.')
        rows, missing = [], False
        for index in range(self.budget['max_candidates']):
            if not _exists(self.root, f'strategy-{index:03}.json'):
                missing = True
                continue
            if missing:
                raise MicaError('Retained strategy sequence has a gap.')
            decision, _ = self._strategy_decision(index, mode, initial_plans)
            selected = decision['selected']
            build = None
            if _exists(self.root, f'strategy-{index:03}-build.json'):
                build, _ = self._strategy_decision(index, mode, initial_plans, phase='build')
            applied = build['selected'] if build else selected
            if _exists(self.root, f'branch-{index:03}.json'):
                branch = _read(self.root, f'branch-{index:03}.json')
                if (branch.get('strategy_sha256') != decision['sha256'] or
                        branch.get('root_request_sha256') != C.digest(self.request) or
                        branch.get('depth') != (selected['depth'] if selected else index) or
                        branch.get('parent_plan') != (selected.get('parent_plan_sha256') if selected else None) or
                        branch.get('trigger') != (selected.get('trigger') if selected else None) or
                        (build and branch.get('build_strategy_sha256') != build['sha256']) or
                        (applied and applied['kind'] == 'build' and
                         (branch['plan'] or {}).get('content_hash') != applied['plan_sha256'])):
                    raise MicaError('Retained branch differs from its selected strategy.')
                verify_result_artifacts(branch['result'], self.request, implementation_identity())
            rows.append({'file': f'strategy-{index:03}.json', 'sha256': decision['sha256'],
                         'choice_id': selected['id'] if selected else None,
                         'kind': selected['kind'] if selected else None})
            if build:
                rows.append({'file': f'strategy-{index:03}-build.json', 'sha256': build['sha256'],
                             'choice_id': applied['id'] if applied else None, 'kind': 'build'})
        return {'version': Q.VERSION, 'scope': Q.SCOPE, 'decisions': rows}

    def execute(self, mode="mica", initial_plans=None, *, plan_only=False):
        """Run (or resume) the construction in `mode`; returns the sealed result report. Exclusive per folder."""
        if mode not in MODES:
            raise MicaError("Unknown construction strategy.")
        if any(parent.is_symlink() for parent in (self.root, *self.root.parents)):
            raise MicaError("Symlinked construction workspace refused.")
        D._mkdir_private(self.root)
        D._safe_listing(self.root, 1024)
        for name in ("attempts", "components", "unit-states", "decisions"):
            D._mkdir_private(self.root / name)
        fd = os.open(self.root / ".mica.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        timer = None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            old = _read(self.root, "mica-manifest.json") if _exists(self.root, "mica-manifest.json") else None
            manifest = {"version": VERSION, "request": self.request, "inventory": self.inventory,
                        "run_id": old['run_id'] if old else uuid.uuid4().hex,
                        "mode": mode, "initial_plans": initial_plans or [], "identity": implementation_identity(),
                        "library": str(self.library.root) if self.library else None,
                        "calibration": self.calibration,
                        "started_ms": old["started_ms"] if old else int(time.time() * 1000)}
            _put(self.root, "mica-manifest.json", manifest)
            self._meter_active = True
            uncertain = self._audit_native()
            strategy_audit = self._strategy_audit(mode, initial_plans)
            if _exists(self.root, "mica-result.json"):
                existing = _read(self.root, "mica-result.json")
                if uncertain or existing.get("manifest_sha256") != D._hash(manifest):
                    raise MicaError("Result is detached from the frozen construction request.")
                verify_result_artifacts(existing, self.request, implementation_identity())
                verify_host_costs(existing, self.root, manifest["identity"])
                if strategy_audit is not None and existing.get('strategy') != strategy_audit:
                    raise MicaError('Completed report is detached from its retained strategy decisions.')
                return existing
            self.observations = (list(self.calibration['observations']) if self.calibration else []) + [
                e["observation"] for e in self._events() if e["kind"] == "observation"]
            R.summarize(self.observations)
            if uncertain:
                self.uncertain.set()
                return self._report({"status": "unknown", "failure": "UNRESOLVED_EFFECT",
                    "error": "Retained attempts have unresolved deliveries: " + ", ".join(uncertain)}, [], terminal=False)
            remaining_seconds = max(0, manifest["started_ms"] / 1000 + self.budget["wall_seconds"] - time.time())
            timer = threading.Timer(remaining_seconds, self.stop.set)
            timer.daemon = True
            timer.start()
            for path in (self.root / "components").glob("*.json"):
                token = D._unseal(D._read(path))
                if token["runtime"] != implementation_identity() or token["artifact"]["code_sha256"] != SC.code_hash(token["code"]):
                    raise MicaError("Component runtime or code identity changed.")
                self.components.setdefault(token["key"], []).append(token)
            previous, feedback, attempts = None, None, []
            count = 1 if mode in ("direct", "static", "capability") else self.budget["max_candidates"]
            for index in range(count):
                self.escalation = {}
                self.strategy_routes = None
                strategy, strategy_plans = (self._measure('scheduler', 'strategy_frontier', self._strategy_decision,
                    index, mode, initial_plans) if mode in ('mica', 'search') else (None, {}))
                choice = strategy['selected'] if strategy else None
                build_strategy = None
                branch_name = f"branch-{index:03}.json"
                if _exists(self.root, branch_name):
                    row = _read(self.root, branch_name)
                    if row.get("root_request_sha256") != C.digest(self.request):
                        raise MicaError("Branch belongs to another root request.")
                    if strategy and row.get('strategy_sha256') != strategy['sha256']:
                        raise MicaError('Branch is detached from its selected strategy.')
                    plan, result = row["plan"], row["result"]
                    verify_result_artifacts(result, self.request, implementation_identity())
                else:
                    failed_contract = next((c for c in (previous or {}).get("contracts", [])
                                            if c["contract_id"] == (feedback or {}).get("contract")), None)
                    policy = failed_contract["failure_policy"]["action"] if failed_contract else None
                    alternatives = self._escalation_routes(failed_contract, mode) if failed_contract else []
                    escalate = policy == "escalate" or (policy == "refine_or_escalate" and alternatives and index % 2 == 1)
                    if strategy is not None:
                        if choice is None:
                            plan, error = None, {'status': 'exhausted', 'failure': 'RESOURCE_EXHAUSTION',
                                                 'error': 'Bounded strategy frontier is exhausted.'}
                        elif choice['kind'] == 'build':
                            plan, error = strategy_plans[choice['plan_sha256']], None
                            self.strategy_routes = choice['routes']
                        else:
                            parent = strategy_plans.get(choice['parent_plan_sha256'])
                            plan, error = self._propose(index, mode, parent if choice['kind'] == 'refine' else None,
                                                       choice['trigger'], strategy=choice)
                            if error is None:
                                build_strategy, _ = self._measure('scheduler', 'strategy_worker_assignment',
                                    self._strategy_decision, index, mode, initial_plans, phase='build')
                                applied = build_strategy['selected']
                                if applied is None:
                                    error = {'status': 'exhausted', 'failure': 'RESOURCE_EXHAUSTION',
                                             'error': 'No bounded worker assignment for the admitted graph.'}
                                else:
                                    self.strategy_routes = applied['routes']
                    elif initial_plans and index < len(initial_plans):
                        plan, error = self._measure("scheduler", "explicit_plan_admission", C.validate_plan, self.request, initial_plans[index]), None
                    elif escalate:
                        plan, error = previous, None
                        self.escalation[failed_contract["contract_id"]] = alternatives
                    elif index == 0 and mode in ("direct", "decompose_on_failure"):
                        try:
                            plan, error = direct_plan(self.request), None
                        except C.ContractError as exc:
                            plan, error = None, {"status": "blocked", "failure": "VERIFICATION_UNKNOWN",
                                                "error": str(exc)}
                    elif index > self.budget["max_depth"]:
                        plan, error = None, {"status": "exhausted", "failure": "RESOURCE_EXHAUSTION",
                                             "error": "Decomposition depth exhausted."}
                    else:
                        plan, error = self._propose(index, mode, previous, feedback)
                    if plan_only:
                        return self._report(error or {"status": "planned", "plan": plan,
                            "assurance": "validated_contract_graph_not_implemented"}, attempts, terminal=False)
                    try:
                        result = error or self._build(plan, index, mode)
                    except (JS.JsError, C.ContractError, N.NativeError, K.DeterministicError) as exc:
                        uncertain = self._audit_native()
                        result = ({"status": "unknown", "failure": "UNRESOLVED_EFFECT",
                                   "error": "A concurrent attempt has no durable outcome."} if uncertain else
                                  self._guard() or {"status": "blocked", "failure": "VERIFICATION_UNKNOWN",
                                                    "error": type(exc).__name__ + ": " + str(exc)[:1500]})
                    if result["status"] in ("unknown", "stopped"):
                        if result["status"] == "stopped" and self._deadline_expired():
                            result = {**result, "status": "exhausted", "failure": "RESOURCE_EXHAUSTION",
                                      "error": "Original construction deadline exhausted."}
                        else:
                            return self._report(result, attempts, terminal=False)
                    _put(self.root, branch_name, {"plan": plan, "result": result,
                         **({'strategy_sha256': strategy['sha256']} if strategy else {}),
                         **({'build_strategy_sha256': build_strategy['sha256']} if build_strategy else {}),
                         "depth": choice['depth'] if choice else index,
                         "parent_plan": (choice.get('parent_plan_sha256') if choice else None) if strategy else
                                        (previous.get("content_hash") if previous else None),
                         "trigger": (choice.get('trigger') if choice else None) if strategy else feedback,
                         "root_request_sha256": C.digest(self.request)})
                attempts.append({"branch": index, "plan_sha256": plan.get("content_hash") if plan else None,
                                 "status": result["status"], "failure": result.get("failure"),
                                 "decisions": result.get("decisions", [])})
                if (result["status"] in ("done", "unknown", "blocked", "exhausted")
                        or result.get("failure_policy") == "stop"):
                    break
                previous = plan or previous
                feedback = {k: result[k] for k in ("failure", "contract", "error", "failure_policy") if k in result}
            else:
                result = {"status": "exhausted", "failure": "RESOURCE_EXHAUSTION", "error": "Alternative plan budget exhausted."}
            return self._report(result, attempts, terminal=result["status"] != "unknown")
        finally:
            self._meter_active = False
            if timer is not None:
                timer.cancel()
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _observe(self, ident, contract, route, result, *, accepted):
        """Retain host-decided outcomes; absent weight observations stay absent."""
        if route is None or result.get("status") == "stopped" or not result.get("calls"):
            return
        if not accepted and failure_class(result) in ('VERIFICATION_UNKNOWN', 'RESOURCE_EXHAUSTION', 'INTERNAL_ERROR'):
            return  # A verifier/resource refusal supplies cost evidence, not a model correctness grade.
        previous = next((r for r in self.observations if r["observation_id"] == ident), None)
        if previous is not None:
            return
        records = result.get("provider_evidence", [])
        values = [row["observed"] for row in records]
        from symblic.providers import ollama_call as B
        identities = [B.check(v.get("model_identity")) for v in values]
        sha = None
        if identities and all(v and v["status"] == "observed" and v["provider"] == "ollama"
                              and v["model"] == route["model"] and v["node"] == route["node"] for v in identities):
            digests = {v["digest"].removeprefix("sha256:") for v in identities}
            if len(digests) == 1:
                sha = digests.pop()
        counters = {}
        for field in ("input_tokens", "output_tokens", "latency_ms"):
            readings = [v.get("ms") if field == "latency_ms" else (v.get("usage") or {}).get(field) for v in values]
            counters[field] = sum(readings) if (len(readings) == result.get("calls") and readings
                                and all(type(x) is int and x >= 0 for x in readings)) else None
        kind = failure_class(result)
        status = ("success" if accepted else "unknown" if result.get("status") == "unknown" else
                  "timeout" if kind == "MODEL_TIMEOUT" else "refused" if result.get("status") == "blocked" else "failed")
        observation = {"observation_id": ident, "engine": "ollama", "model": route["model"], "node": route["node"],
                       "digest": sha, "task_class": contract["model_eligibility"]["task_class"], "status": status,
                       "contract_hash": contract["content_hash"], "checker_hash": D._hash(implementation_identity()),
                       "calls": result.get("calls", 0), "cached": result.get("reuse", False), **counters}
        R.summarize([observation])
        self._event("observation", observation=observation)
        self.observations.append(observation)

    def _report(self, result, attempts, terminal):
        reservations = sum(self._allocations().values())
        evidence, calls, host_costs = [], 0, [T.summarize(self._events())]
        for path in sorted((self.root / "attempts").iterdir()):
            if not path.is_dir() or path.is_symlink():
                raise MicaError("Invalid native attempt directory.")
            host_costs.append(N.cost_summary(path))
            journal = D._read(path / "graph-calls.jsonl", lines=True, missing=True)
            calls += sum(D._unseal(row).get("kind") == "intent" for row in journal)
            rows = D._read(path / "mica-provider-evidence.jsonl", lines=True, missing=True)
            evidence.extend(D._unseal(row)["observed"] for row in rows)
        # No-provider runs have exactly zero provider tokens. Partially reported
        # measurements retain a known subtotal but cannot masquerade as totals.
        measurements = {}
        for field in ("input_tokens", "output_tokens", "latency_ms"):
            values = [v.get("ms") if field == "latency_ms" else (v.get("usage") or {}).get(field) for v in evidence]
            known = [v for v in values if type(v) is int and v >= 0]
            measurements[field] = {"known_sum": sum(known), "known_calls": len(known),
                                   "unknown_calls": max(0, calls - len(known)),
                                   "total": sum(known) if len(known) == calls else None}
        frozen = _read(self.root, "mica-manifest.json")
        # _read preserves the seal; hash the body exactly as it was frozen.
        manifest_body = {k: v for k, v in frozen.items() if k != "sha256"}
        report = {"version": VERSION, **result, "calls": calls, "calls_reserved_or_spent": reservations,
                  "attempts": attempts, "manifest_sha256": D._hash(manifest_body),
                  "request_sha256": C.digest(self.request), "costs": {"provider_calls": calls,
                    "input_tokens": measurements["input_tokens"]["total"],
                    "output_tokens": measurements["output_tokens"]["total"],
                    "provider_ms": measurements["latency_ms"]["total"],
                    "latency_ms": max(0, int(time.time() * 1000) - frozen["started_ms"]),
                    "wall_seconds": max(0, time.time() - frozen["started_ms"] / 1000),
                    "cpu_seconds": None, "memory_bytes": None},
                  "measurements": measurements, "host_costs": T.combine(host_costs), "routing_observations": R.summarize(self.observations),
                  "calibration": {"sha256": self.calibration['sha256'] if self.calibration else None,
                                  "seed_observations": len(self.calibration['observations']) if self.calibration else 0,
                                  "fresh_observations": sum(not o['observation_id'].startswith('cal/') for o in self.observations)},
                  "evidence": {"ledger": "mica-events.jsonl", "native_attempts": "attempts/",
                    "caller_acceptance_sha256": C.digest(self.request["tests"]),
                    "scope": "finite encoded checks; root intent adequacy remains explicit"}}
        strategy = self._strategy_audit(frozen['mode'], frozen['initial_plans'])
        if strategy is not None:
            report['strategy'] = strategy
        if terminal:
            return _put(self.root, "mica-result.json", report)
        return report


class StoreProxy:
    """The existing graph durable append helper only needs a directory/path."""
    def __init__(self, root):
        self.dir = str(root)

    def path(self, name):
        return str(Path(self.dir) / name)


class DeadlineStop:
    """Compose an original unit deadline with the job's existing generation fence."""
    def __init__(self, parent, deadline_ms):
        self.parent, self.deadline_ms = parent, deadline_ms
        self.monotonic_deadline = time.monotonic() + max(0, deadline_ms / 1000 - time.time())
        self.monotonic_deadline = min(self.monotonic_deadline, getattr(parent, 'monotonic_deadline', self.monotonic_deadline))
        if hasattr(parent, "fence"):
            self.fence = parent.fence

    def is_set(self):
        return (self.parent.is_set() or time.time() * 1000 >= self.deadline_ms
                or time.monotonic() >= self.monotonic_deadline)

    def set(self):
        self.parent.set()

    def wait(self, timeout=None):
        remaining = max(0, min(self.deadline_ms / 1000 - time.time(), self.monotonic_deadline - time.monotonic()))
        self.parent.wait(remaining if timeout is None else min(max(0, timeout), remaining))
        return self.is_set()
