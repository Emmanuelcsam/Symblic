"""MICA zero-call construction: compiles one explicit integer-affine function family without a model.

What it is for
    When a unit contract declares construction.kind = "affine_integer_v1", the native kernel enumerates the
    bounded coefficients against the unit's examples; only a unique solution is lowered to JavaScript, so the unit
    costs no model call.

Depends on: symblic.spec.sheets (literal helper), source_identity.py. Used by contracts.py and search.py.

Details
    Compile one explicit finite affine fragment to existing native determination.

    The native Run enumerates a bounded coefficient record and checks original unit
    examples with exact arithmetic. Only a unique tuple is lowered to JavaScript.
    This module neither searches the domain itself nor executes arbitrary source.
    Uniqueness is conditional on the declared affine family, coefficient bounds and
    examples; it does not establish prose adequacy or general program correctness.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
import hashlib
from pathlib import Path
import re

from symblic.spec import sheets as SP
from symblic.mica import source_identity as I

VERSION = 1
KIND = "affine_integer_v1"
MAX_PARAMETERS = 4
MAX_EXAMPLES = 32
MAX_COEFFICIENT_TUPLES = 4096
MAX_COEFFICIENT_WIDTH = 129
MAX_ABSOLUTE_BOUND = 1_000_000
MAX_STEPS = 8_000_000
SAFE_INTEGER = 2 ** 53 - 1
_NAME = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]{0,63}\Z")
_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_RESERVED = frozenset(("await break case catch class const continue debugger default delete do else enum export "
    "extends false finally for function if implements import in instanceof interface let new null package "
    "private protected public return static super switch this throw true try typeof var void while with yield "
    "eval arguments").split())
_LOADED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class DeterministicError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def identity():
    problems = I.audit({I.relative_path(__file__): _LOADED_SHA256})
    if problems:
        raise DeterministicError("identity", "Deterministic compiler source changed: " + "; ".join(problems))
    return {"version": VERSION, "sha256": _LOADED_SHA256}


def _refuse(code, message):
    raise DeterministicError(code, message)


def _name(value):
    if type(value) is not str or not _NAME.fullmatch(value) or value in _RESERVED:
        _refuse("identifier", "The affine fragment requires bounded ordinary JavaScript identifiers.")
    return value


def _bound(value, *, parameter=False):
    wanted = {"name", "lo", "hi"} if parameter else {"lo", "hi"}
    if type(value) is not dict or set(value) != wanted:
        _refuse("bounds", "Bounds must contain exact lo/hi and a name only for parameters.")
    low, high = value["lo"], value["hi"]
    if (type(low) is not int or type(high) is not int or low > high
            or max(abs(low), abs(high)) > MAX_ABSOLUTE_BOUND):
        _refuse("bounds", "Bounds must be ordered exact integers within the finite fragment limit.")
    if not parameter and high - low + 1 > MAX_COEFFICIENT_WIDTH:
        _refuse("domain", "An individual coefficient range exceeds its finite bound.")
    return {**({"name": _name(value["name"])} if parameter else {}), "lo": low, "hi": high}


def normalize(value, unit):
    """Validate explicit strategy authority; no inferred coefficients or checks.

    Unsupported declarations raise a typed local error. A caller may choose its
    separate model strategy; this is not proof no program solves the objective.
    """
    if value is None:
        return None
    keys = {"kind", "parameters", "coefficient_bounds", "intercept_bounds"}
    if type(value) is not dict or set(value) - keys - {"version"} or not keys <= set(value):
        _refuse("shape", "Unknown or missing deterministic construction fields.")
    if value["kind"] != KIND or type(value.get("version", VERSION)) is not int or value.get("version", VERSION) != VERSION:
        _refuse("kind", "This compiler supports only affine_integer_v1.")
    if type(unit) is not dict:
        _refuse("unit", "A declared construction unit is required.")
    names, parameters, bounds = unit.get("names"), value["parameters"], value["coefficient_bounds"]
    if type(names) is not list or len(names) != 1:
        _refuse("unit", "Finite affine construction supports exactly one function export.")
    name = _name(names[0])
    if unit.get("setup") != "" or unit.get("uses") != []:
        _refuse("dependency", "Finite affine construction has no setup or helper dependencies.")
    if type(parameters) is not list or not 1 <= len(parameters) <= MAX_PARAMETERS:
        _refuse("parameters", "Finite affine construction requires one to four parameters.")
    parameters = [_bound(row, parameter=True) for row in parameters]
    if len({row["name"] for row in parameters}) != len(parameters) or any(row["name"] == name for row in parameters):
        _refuse("parameters", "Affine parameters must be unique and differ from their export.")
    signature = re.fullmatch(re.escape(name) + r"\s*\(\s*([^()]*)\s*\)", str(unit.get("heading", "")).strip())
    if signature is None or [part.strip() for part in signature.group(1).split(",")] != [row["name"] for row in parameters]:
        _refuse("signature", "Affine parameter declarations must match the exact simple unit signature.")
    if type(bounds) is not list or len(bounds) != len(parameters):
        _refuse("bounds", "Every parameter requires an explicit coefficient bound.")
    bounds = [_bound(row) for row in bounds]
    intercept = _bound(value["intercept_bounds"])
    cardinality = intercept["hi"] - intercept["lo"] + 1
    envelope = max(abs(intercept["lo"]), abs(intercept["hi"]))
    for parameter, bound in zip(parameters, bounds):
        cardinality *= bound["hi"] - bound["lo"] + 1
        envelope += max(abs(parameter["lo"]), abs(parameter["hi"])) * max(abs(bound["lo"]), abs(bound["hi"]))
    if cardinality > MAX_COEFFICIENT_TUPLES:
        _refuse("domain", "The declared coefficient product exceeds 4096 tuples.")
    if envelope > SAFE_INTEGER:
        _refuse("arithmetic", "Some admitted affine evaluation exceeds JavaScript exact integer arithmetic.")
    result = {"version": VERSION, "kind": KIND, "parameters": parameters,
              "coefficient_bounds": bounds, "intercept_bounds": intercept}
    _examples(unit, result)
    return result


def _examples(unit, construction):
    rows = unit.get("examples")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_EXAMPLES:
        _refuse("examples", "The finite affine fragment requires one to 32 declared examples.")
    function = unit["names"][0]
    call = re.compile(re.escape(function) + r"\s*\(\s*([^()]*)\s*\)\s*\Z")
    parameters = construction["parameters"]
    parsed = []
    for row in rows:
        if (type(row) is not list or len(row) != 2 or type(row[0]) is not str
                or type(row[1]) is not str or len(row[0]) > 4000 or len(row[1]) > 100):
            _refuse("examples", "Each affine example must be bounded call/expected JSON text.")
        match = call.fullmatch(row[0].strip())
        if not match:
            _refuse("example_call", "Affine examples support only direct calls with exact integer literals.")
        texts = [part.strip() for part in match.group(1).split(",")]
        if len(texts) != len(parameters) or any(len(text) > 32 or not _INTEGER.fullmatch(text) for text in texts):
            _refuse("example_call", "Affine examples require the declared arity and integer literal arguments.")
        values = [int(text) for text in texts]
        if any(not parameter["lo"] <= value <= parameter["hi"] for parameter, value in zip(parameters, values)):
            _refuse("example_domain", "An affine example lies outside its explicitly declared input domain.")
        expected_text = row[1].strip()
        if not _INTEGER.fullmatch(expected_text) or len(expected_text) > 32:
            _refuse("example_result", "Affine expected values must be JSON exact integers.")
        expected = int(expected_text)
        if abs(expected) > SAFE_INTEGER:
            _refuse("example_result", "Expected affine values must be safe JavaScript integers.")
        parsed.append({"arguments": values, "expected": expected})
    return parsed


def compile_contract(contract):
    """Return inert native source and fixed options, or an explicit unsupported row.

    Only native finite determination executes the coefficient search. The source
    emits code text and cannot call a model, host effect, arbitrary evaluator or
    JavaScript process. MicaRun still checks the code and independent root tests.
    """
    identity()
    try:
        if type(contract) is not dict or contract.get("construction") is None:
            _refuse("undeclared", "No deterministic construction fragment was declared.")
        unit = contract.get("unit")
        construction = normalize(contract["construction"], unit)
        if contract.get("dependency_contract_ids", []) or contract.get("input_artifacts", []) or contract.get("permitted_effects", []):
            _refuse("dependency", "Finite affine construction is pure and has no dependency artifacts.")
        examples = _examples(unit, construction)
    except DeterministicError as error:
        return {"status": "unsupported", "reason": error.code, "error": str(error),
                "scope": "unsupported_in_declared_affine_fragment_not_a_proof_of_impossibility"}
    fields = [f"a{index}: Int in {bound['lo']}..{bound['hi']}"
              for index, bound in enumerate(construction["coefficient_bounds"])]
    intercept = construction["intercept_bounds"]
    fields.append(f"b: Int in {intercept['lo']}..{intercept['hi']}")
    source = ["program Construct a bounded integer affine function.",
              "use profile=verified, context=none, by=kernel, solve=true, retries=0.",
              "ask coefficients: Record {" + ", ".join(fields) + "} " + SP.literal(
                  "Select the unique coefficient tuple satisfying the declared exact examples.") + "."]
    for row in examples:
        terms = [f"(coefficients.a{index} * ({value}))" for index, value in enumerate(row["arguments"])]
        source.append("ensure " + " + ".join([*terms, "coefficients.b"]) + f" = ({row['expected']}) else retry.")
    parameters = construction["parameters"]
    guard = " || ".join(f'(typeof {p["name"]} !== "number" || {p["name"]} % 1 !== 0 || '
                         f'{p["name"]} < {p["lo"]} || {p["name"]} > {p["hi"]})' for p in parameters)
    prefix = ("function " + unit["names"][0] + "(" + ", ".join(p["name"] for p in parameters) + ") {\n"
              "  if (" + guard + ") { throw \"Outside declared affine integer domain\"; }\n  return ")
    pieces = [SP.literal(prefix)]
    for index, parameter in enumerate(parameters):
        if index:
            pieces.append(SP.literal(" + "))
        pieces.extend([SP.literal("("), f"text(coefficients.a{index})", SP.literal(" * " + parameter["name"] + ")")])
    pieces.extend([SP.literal(" + ("), "text(coefficients.b)", SP.literal(");\n}\n")])
    source.extend(["let candidate = " + " + ".join(pieces) + ".", "show candidate."])
    cardinality = intercept["hi"] - intercept["lo"] + 1
    for bound in construction["coefficient_bounds"]:
        cardinality *= bound["hi"] - bound["lo"] + 1
    return {"version": VERSION, "status": "supported", "kind": KIND,
            "source": "\n".join(source) + "\n", "output_binding": "candidate", "construction": copy.deepcopy(construction),
            "options": {"max_steps": MAX_STEPS}, "coefficient_tuples": cardinality,
            "examples": len(examples), "model_calls": 0, "compiler_identity": identity(),
            "scope": "Unique bounded affine coefficients conditional on declared finite examples; JS/root checks remain required.",
            "formal_correctness": "not_established_for_prose_or_arbitrary_javascript"}
