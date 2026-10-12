"""MICA to Symblic: lowers one unit contract to a native Symblic program and runs it with a durable journal.

What it is for
    Each model call MICA makes is a typed `ask` inside a small native Symblic program (planner_source,
    unit_source). This module builds those programs, pins their execution identity, runs them through
    symblic.kernel.run with the contracted-graph call journal (symblic.graph.run), and records what the provider
    observed (usage, model identity) next to each call, refusing replies whose observed model identity contradicts
    the frozen route.

Depends on: symblic.kernel (language, run, execution_pins, json_schema), symblic.graph.run, symblic.js,
symblic.spec, symblic.providers.ollama_call (identity records) and costs.py. Run by search.py and project.py.

Details
    MICA construction calls through the authoritative Symblic interpreter.

    This adapter reuses the contracted-graph call journal. It is not an interpreter,
    provider client, shell executor or effects host. Importing it starts no work.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from contextlib import nullcontext
import fcntl
import hashlib
import json
import os
import re
import threading
from pathlib import Path

from symblic.kernel import language as S
from symblic.kernel import execution_pins as X
from symblic.graph import run as G
from symblic.js import check as JS
from symblic.js import contract as JSC
from symblic.mica import costs as T
from symblic.spec import sheets as SP
from symblic.kernel.run import Run, Store

VERSION = 1
_LOADED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class NativeError(ValueError):
    pass


class _BoundedRun(Run):
    """Pass a trusted host deadline into native checks, including sample threads.

    Parsing, typed asks, candidate selection, repair, effects and replay all remain
    Run's implementation. The only extension is a verification resource scope.
    """
    verification_deadline = None
    cost_emit = None

    def _candidate(self, *args, **kwargs):
        with JS.verification_deadline_scope(self.verification_deadline), JSC.require_complete_scope(), (
                T.measure(self.cost_emit, "verification", "native_candidate_predicates")
                if self.cost_emit is not None else nullcontext()):
            return super()._candidate(*args, **kwargs)


def cost_events(folder):
    """The sealed host-cost events retained in one native attempt folder."""
    rows = G._read(Path(folder) / "mica-host-costs.jsonl", lines=True, missing=True)
    previous = None
    for index, row in enumerate(rows):
        G._unseal(row)
        if row.get("sequence") != index or row.get("previous") != previous:
            raise NativeError("Native cost event chain is incomplete or reordered.")
        previous = row["sha256"]
    return rows


def cost_summary(folder):
    """The combined host-cost summary of one native attempt folder (see costs.py)."""
    return T.summarize(cost_events(folder))


def inspect_attempt(folder):
    """Read and validate retained dispatch state without constructing a worker."""
    directory = Path(folder)
    if any(parent.is_symlink() for parent in (directory, *directory.parents)):
        raise NativeError("Symlinked native attempt refused.")
    G._safe_tree(directory)
    frozen = G._unseal(G._read(directory / "mica-native-pins.json"))
    body = {key: value for key, value in frozen.items() if key != "sha256"}
    class View:
        def path(self, name):
            return str(directory / name)
    calls = G._Calls(View(), None, frozen["route"], True, frozen["limit"],
                     {"mica_native": G._hash(body)}, frozen["source_sha256"], threading.Event())
    result_file = directory / "mica-native-result.json"
    if result_file.exists() or result_file.is_symlink():
        result = G._unseal(G._read(result_file))
        if (("cost_meter" in frozen["identity"] and result.get("host_costs") != cost_summary(directory))
                or result.get("pins_sha256") != G._hash(body) or result.get("calls") != len(calls.intents)
                or calls.uncertain):
            raise NativeError("Native result and retained dispatch evidence disagree.")
    cost_summary(directory)
    return {"status": "unknown" if calls.uncertain else "recorded", "calls": len(calls.intents),
            "pins_sha256": G._hash(body)}


def _identity():
    current = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if current != _LOADED_SHA256 or not _symblic_import_identity["matched"]:
        raise NativeError("Construction adapter changed on disk; use a fresh process.")
    if not G._SOURCE_LOADED or hashlib.sha256(Path(G.__file__).read_bytes()).hexdigest() != G._SOURCE_SHA256:
        raise NativeError("Native call journal implementation changed; start a fresh worker.")
    cost_sha = hashlib.sha256(Path(T.__file__).read_bytes()).hexdigest()
    if not T._symblic_import_identity["matched"] or cost_sha != T._symblic_import_identity["sha256"]:
        raise NativeError("Host cost instrumentation changed; start a fresh process.")
    return {"version": VERSION, "adapter": current, "cost_meter": cost_sha,
            "graph_calls": hashlib.sha256(Path(G.__file__).read_bytes()).hexdigest(),
            "kernel": S.kernel_id()}


def _put_once(folder, name, value):
    path = Path(folder) / name
    sealed = G._seal(value)
    if path.exists() or path.is_symlink():
        existing = G._unseal(G._read(path))
        if existing != sealed:
            raise NativeError("An immutable native construction record changed: " + name)
    else:
        G._write_json(folder, name, sealed)
    return sealed


def route_label(route):
    """The applicator spec for a route ({"provider": "ollama", "model", "node", "local": True}): ollama:MODEL@NODE."""
    if (type(route) is not dict or route.get("provider") != "ollama"
            or route.get("local") is not True
            or any(type(route.get(k)) is not str or not route[k] for k in ("model", "node"))
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", route["node"])
            or route.get("digest") is not None and not re.fullmatch(r"[0-9a-f]{64}", str(route["digest"]))):
        raise NativeError("Construction requires an explicitly selected local model on a node from the inventory.")
    label = "ollama:" + route["model"] + "@" + route["node"]
    app = S.parse_applicator(label)
    if any(app.get(k) != route[k] for k in ("model", "node")) or app.get("engine") != "ollama":
        raise NativeError("Route text does not encode exactly one local applicator.")
    return label


def execute(source, folder, applicators, route, *, limit, output_binding, stop=None,
            inputs=None, options=None):
    """One durable source-pinned native attempt, including native bounded repairs.

    Existing completed outcomes return without generation. An unfinished provider
    intent remains unknown. Native source and options are trusted compiler output;
    candidate text is always data until the existing sandboxed JS checker sees it.
    """
    label = route_label(route)
    return _execute(source, folder, applicators, route, label=label, limit=limit,
                    output_binding=output_binding, stop=stop, inputs=inputs, options=options)


def execute_kernel(source, folder, *, output_binding="candidate", stop=None, options=None):
    """Run a compiled finite construction in the existing kernel, with no provider."""
    return _execute(source, folder, None,
                    {"provider": "kernel", "model": "", "node": "", "local": True, "digest": None},
                    label="kernel", limit=0, output_binding=output_binding, stop=stop, options=options)


def _execute(source, folder, applicators, route, *, label, limit, output_binding,
             stop=None, inputs=None, options=None):
    if type(limit) is not int or not 0 <= limit <= 10000:
        raise NativeError("Invalid native call allocation.")
    if type(output_binding) is not str or not output_binding.isidentifier():
        raise NativeError("An exact native output binding is required.")
    checked = S.check(source, execution_profile="verified")
    if not checked["ok"]:
        raise NativeError("Native compilation refused: " + checked["errors"][0]["message"])
    directory = Path(folder)
    if any(parent.is_symlink() for parent in (directory, *directory.parents)):
        raise NativeError("Symlinked construction workspace refused.")
    G._mkdir_private(directory)
    G._safe_tree(directory)
    fd = os.open(directory / ".mica-native.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        options = dict(options or {})
        if set(options) - {"ollama_limits", "budget", "max_steps", "model_pins"}:
            raise NativeError("Unsupported native construction option.")
        inputs = dict(inputs or {})
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        pins = X.build(source, inputs, {name: X._sha(X._read(name)) for name in X.REQUIRED_FILES})
        frozen = {"version": VERSION, "source": source, "source_sha256": source_hash,
                  "inputs": inputs, "route": route, "limit": limit, "output_binding": output_binding,
                  "options": options, "identity": _identity(), "execution_pins": pins}
        _put_once(directory, "mica-native-pins.json", frozen)
        store = Store(str(directory))
        stop = stop or threading.Event()
        observer = _ProviderEvidence(store, applicators, route)
        calls = G._Calls(store, observer, route, True, limit,
                         {"mica_native": G._hash(frozen)}, source_hash, stop, fence=getattr(stop, "fence", None))
        result_path = directory / "mica-native-result.json"
        if result_path.exists() or result_path.is_symlink():
            result = G._unseal(G._read(result_path))
            if result.get("pins_sha256") != G._hash(frozen) or result.get("host_costs") != cost_summary(directory):
                raise NativeError("Native result belongs to another frozen attempt.")
            if calls.uncertain:
                raise NativeError("Completed result has an unresolved call intent.")
            return result
        if calls.uncertain:
            return {"status": "unknown", "failure": "UNRESOLVED_EFFECT", "calls": len(calls.intents),
                    "error": "Provider delivery has no durable outcome; automatic redispatch is blocked.",
                    "pins_sha256": G._hash(frozen), "output": None, "host_costs": cost_summary(directory)}
        G._write_file(directory, "program.sym", source.encode())
        native = _BoundedRun(source, inputs=inputs, applicators=calls,
                     options={**options, "profile": "verified", "side_effects": False,
                              "by": label, "parallel": 1, "max_calls": limit,
                              "execution_pins": pins, "stop": stop}, folder=str(directory))
        calls.runner = native
        native.verification_deadline = getattr(stop, "monotonic_deadline", None)
        cost_lock = threading.Lock()
        def emit_cost(kind, **fields):
            with cost_lock:
                rows = cost_events(directory)
                G._append(store, "mica-host-costs.jsonl", G._seal({
                    "sequence": len(rows), "previous": rows[-1]["sha256"] if rows else None,
                    "kind": kind, **fields}))
        native.cost_emit = emit_cost
        with JS.verification_deadline_scope(native.verification_deadline), JSC.require_complete_scope():
            report = native.execute()
        value = native.kernel.env.lookup(output_binding)
        output = value.value if report["status"] == "done" and value is not None else None
        if output is not None and type(output) is not str:
            raise NativeError("Construction output is not exact text.")
        status = "unknown" if calls.uncertain else ("stopped" if stop.is_set() and report["status"] != "done" else report["status"])
        if status == "done" and output is None:
            status = "failed"
        failure = None
        error_kind = (report.get("error") or {}).get("kind")
        if status == "failed" and error_kind in ("resource", "unavailable", "version"):
            status, failure = "blocked", "VERIFICATION_UNKNOWN"
        elif status == "failed" and error_kind == "internal":
            status, failure = "blocked", "INTERNAL_ERROR"
        elif status == "failed" and error_kind in ("budget", "context"):
            status, failure = "exhausted", "RESOURCE_EXHAUSTION"
        elif status == "failed" and any(item.get("reply", {}).get("refused") is True
                and item["reply"].get("ok") is False for item in calls.intents.values()):
            # A retained launcher refusal is no model-quality verdict. The graph
            # outcome is authoritative; measurement records or error wording alone
            # cannot establish refusal. Preserve all actual intents and other costs.
            status, failure = "blocked", "VERIFICATION_UNKNOWN"
        result = {"version": VERSION, "pins_sha256": G._hash(frozen), "status": status,
                  **({"failure": failure} if failure else {}),
                  "output": output, "calls": len(calls.intents), "native_report": report,
                  "error": calls.failure or report.get("error"),
                  "journal": "graph-calls.jsonl", "scope": "encoded_native_checks",
                  "provider_evidence": observer.records(), "host_costs": cost_summary(directory)}
        # Uncertainty is an observation of the standing intent, not a terminal
        # outcome which could authorize further attempts or alternative plans.
        if status not in ("unknown", "stopped"):
            return _put_once(directory, "mica-native-result.json", result)
        return result
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class _ProviderEvidence:
    """Keep supplied measurement fields the historical graph wrapper omits.

    This never supplies an outcome to recovery. The graph journal remains the
    dispatch authority; a measurement without its outcome cannot permit replay.
    """
    def __init__(self, store, apps, route):
        self.store, self.apps, self.route = store, apps, route

    def records(self):
        rows = G._read(self.store.path("mica-provider-evidence.jsonl"), lines=True, missing=True)
        for row in rows:
            G._unseal(row)
        return rows

    def call(self, request):
        reply = self.apps.call(request)
        if type(reply) is dict:
            observed = {key: reply[key] for key in ("usage", "model_identity", "ms", "model", "node", "ok", "refused") if key in reply}
            G._append(self.store, "mica-provider-evidence.jsonl",
                      G._seal({"version": 1, "request_key": request["key"], "observed": observed}))
            from symblic.providers import ollama_call as B
            identity = B.check(reply.get("model_identity"))
            conflicting = "model_identity" in reply and (identity is None or identity["status"] == "drift"
                or identity["provider"] != "ollama" or identity["model"] != self.route["model"]
                or (identity["node"] != self.route["node"] and not (
                    reply.get("ok") is not True and identity["status"] == "unavailable"
                    and identity["node"] is None))
                or (identity["status"] == "observed" and self.route.get("digest") is not None
                    and identity["digest"].removeprefix("sha256:") != self.route["digest"]))
            # A failed delivery with no manifest observation is not observed
            # weight drift. Retain its provider failure (for example timeout).
            # Successful answers still require the exact pinned observation.
            missing_pin = reply.get("ok") is True and self.route.get("digest") is not None and not (
                identity and identity["status"] == "observed"
                and identity["digest"].removeprefix("sha256:") == self.route["digest"])
            if conflicting or missing_pin:
                return {"ok": False, "fatal": True, "error": "Observed model identity conflicts with the frozen route or weights.",
                        "model": self.route["model"], "node": self.route["node"]}
        return reply


def planner_source(prompt, route, *, context_chars=None, schema=None):
    """The model proposes JSON text; independent host validation grants no effects."""
    label = route_label(route)
    if context_chars is not None and (type(context_chars) is not int or not 256 <= context_chars <= 262144):
        raise NativeError("Planner context must be an exact bounded character allowance.")
    budget = f", budget={context_chars}" if context_chars is not None else ""
    declared = ''
    if schema is not None:
        from symblic.kernel import json_schema as J
        frozen_schema = J.admit(schema)
        declared = ' schema ' + json.dumps(json.dumps(frozen_schema, ensure_ascii=False, sort_keys=True, separators=(',', ':')), ensure_ascii=False)
    return ("program Propose a construction graph.\n"
            "use profile=verified, context=none, by=" + json.dumps(label) +
            ", retries=0" + budget + ".\n"
            "ask proposal: Code json" + declared + " " + SP.literal(prompt) + ".\n"
            "show proposal.\n")


def unit_source(contract, dependencies, route, *, retries, context_chars, requirements=None, exports=None):
    """Lower a validated contract and exact dependency code to native typed ask."""
    unit = contract["unit"]
    label = route_label(route)
    card = {"contract": contract, "dependencies": dependencies,
            "authoritative_requirements": requirements or [], "caller_export_signatures": exports or [],
            "instruction": "Implement exactly the named JavaScript function declarations. Put any internal helpers inside them. "
                           "Use supplied helpers; do not redefine them. "
                           "Return one fenced js block. The examples are checks, not output code."}
    text = json.dumps(card, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    # Native capsule packing separately includes all system/schema overhead.
    if len(text) > context_chars:
        raise NativeError("Complete contract and required dependency context exceed the context budget.")
    source = ["program Construct a checked unit.",
              "use profile=verified, context=none, by=" + json.dumps(label) +
              f", route=search, samples=1, rounds=1, retries={retries}, budget={context_chars}.",
              "let contract_card = " + SP.literal(text) + ".",
              "ask candidate: Code js \"Implement this bounded construction contract.\" from contract_card."]
    pieces = ([unit["setup"]] if unit["setup"] else []) + [d["code"] for d in dependencies]
    native_pieces = [SP.literal(piece) for piece in pieces] + ["candidate"]
    cases = "[" + ", ".join("[" + SP.literal(c) + ", " + SP.literal(e) + "]" for c, e in unit["examples"]) + "]"
    from symblic.spec.build import _literal
    surface = {"version": 1, "exports": {name: "function" for name in unit["names"]}}
    source += ["let declarations = js_declarations_check(candidate, " + _literal(surface) + ").",
               "ensure declarations.passed else retry because declarations.report.",
               "let checked_candidate = js_test([" + ", ".join(native_pieces) + "], " + cases + ").",
               "ensure checked_candidate.passed else retry because checked_candidate.report.",
               "show candidate."]
    return "\n".join(source) + "\n"
