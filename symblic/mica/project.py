"""MICA projects: from a plain objective to a checked request, then to a construction (MicaProject).

What it is for
    When the caller gives only an objective and a budget, a model first proposes requirements, assumptions,
    signatures and public tests (a root proposal, decoded by proposal.py). MicaProject records which parts are
    caller authority and which are model proposals, then runs MicaRun with the same original budget.

Depends on: search.py, native.py, routing.py, contracts.py, costs.py, proposal.py, symblic.graph.run.
Run by cli.py (`plan`/`execute --objective ...`).

Details
    Objective-to-construction orchestration through the native Symblic runtime.

    An objective is caller authority; generated requirements and checks are proposals.
    This layer records that distinction and shares one original call/time budget with
    MicaRun. Importing it is inert. All provider dispatch uses the native call journal.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid

from symblic.graph import run as G
from symblic.mica import search as M
from symblic.mica import costs as T
from symblic.mica import contracts as C
from symblic.mica import native as N
from symblic.mica import routing as R
from symblic.mica import proposal as Q
from symblic.mica import source_identity as I

VERSION = 1
_LOADED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
MANIFEST = "project-manifest.json"
REQUEST = "project-request.json"
RESULT = "project-result.json"
PLAN = "project-plan.json"
ROOT_SPEC_VERSION = 3
ROOT_COVERAGE_VERSION = 2
MAX_OBJECTIVE_CLAUSES = 128
ROOT_INPUT_MARKER = '\nInput data (not the response):\n'


class ProjectError(ValueError):
    pass


def objective_clauses(objective):
    """Exact source spans, in Unicode code points; lexical units, not meaning.

    Split lines and sentence ends conservatively outside quotes/backticks and
    bracketed code. Decimal points never split. No text is normalized or dropped
    other than whitespace between spans; malformed/unclosed quotations stay one
    retained span. An oversized frontier is refused rather than truncated.
    """
    C._text(objective, "objective")
    spans = []; start = 0; i = 0; quote = None; brackets = []
    def append(end):
        nonlocal start
        left, right = start, end
        while left < right and objective[left].isspace():
            left += 1
        while right > left and objective[right - 1].isspace():
            right -= 1
        if right > left:
            text = objective[left:right]
            spans.append({"id": f"O{len(spans) + 1:03}", "start": left, "end": right,
                          "text": text, "text_sha256": C.digest(text)})
            if len(spans) > MAX_OBJECTIVE_CLAUSES:
                raise ProjectError("Objective exceeds the bounded clause frontier; nothing was truncated.")
        start = end
    while i < len(objective):
        ch = objective[i]
        if quote is not None:
            if ch == "\\":
                i += 2; continue
            if objective.startswith(quote, i):
                i += len(quote); quote = None; continue
            i += 1; continue
        if ch == '`':
            quote = '```' if objective.startswith('```', i) else '`'
            i += len(quote); continue
        if ch == '"' or (ch == "'" and (i == 0 or not objective[i - 1].isalnum())):
            quote = ch; i += 1; continue
        if ch in '([{':
            brackets.append(ch)
        elif ch in ')]}' and brackets and brackets[-1] == {')': '(', ']': '[', '}': '{'}[ch]:
            brackets.pop()
        if not brackets:
            sentence_end = ch in '.!?' and (i + 1 == len(objective) or objective[i + 1].isspace())
            abbreviation = ch == '.' and re.search(r'(?:\be\.g\.|\bi\.e\.|\bvs\.|\bMr\.|\bMrs\.|\bDr\.)$', objective[:i + 1])
            if ch in '\r\n' or (sentence_end and not abbreviation):
                append(i + 1)
        i += 1
    append(len(objective))
    return spans


def _concrete_requirements(request):
    # Exact known template phrases are detectable defects. This deliberately is
    # not a language understanding score or a minimum word/test-count heuristic.
    placeholders = {'concrete required behavior', 'required behavior', 'requirement text',
                    'describe required behavior', 'insert requirement here', 'fill in requirement',
                    'todo', 'tbd', 'placeholder', 'string'}
    for requirement in request['requirements']:
        text = requirement['text'].strip()
        canonical = ' '.join(text.lower().split()).rstrip('.!? ')
        if canonical in placeholders or re.fullmatch(r'<[^<>]+>|\{(?:requirement|behavior|text)\}', text, re.I):
            raise ProjectError('Root requirement contains a template placeholder instead of task behavior.')


def required_public_exports(objective):
    """Read only explicit simple signatures under a named public-functions header.

    This narrow declaration format is caller authority, unlike arbitrary prose
    interpretation. No code is executed. Other wording/types are not inferred.
    """
    C._text(objective, 'objective')
    active = False; offset = 0; result = []
    name = r'[A-Za-z_$][A-Za-z0-9_$]*'
    signature = re.compile(r'(?P<name>' + name + r')\s*\(\s*(?P<args>(?:' + name + r'\s*(?:,\s*' + name + r'\s*)*)?)\)')
    for line in objective.splitlines(keepends=True):
        stripped = line.strip()
        if re.fullmatch(r'(?:#{1,6}\s*)?Required public functions(?: and behavior)?\s*:', stripped, re.I):
            active = True
        elif active:
            if stripped.startswith('#') or re.fullmatch(r'[A-Za-z][A-Za-z ]+:', stripped):
                active = False
            else:
                leading = len(line) - len(line.lstrip())
                match = signature.match(line, leading)
                if match:
                    args = [value.strip() for value in match['args'].split(',')] if match['args'].strip() else []
                    if len(set(args)) != len(args):
                        raise ProjectError('Explicit public signature repeats a parameter name.')
                    start, end = offset + match.start(), offset + match.end()
                    row = {'name': match['name'], 'signature': match['name'] + '(' + ','.join(args) + ')',
                           'start': start, 'end': end, 'text': objective[start:end],
                           'origin': 'caller_explicit_signature', 'span_unit': 'Unicode_code_points'}
                    if not any(part['name'] == row['name'] and part['signature'] == row['signature'] for part in result):
                        result.append(row)
                    if len(result) > 128:
                        raise ProjectError('Explicit public signatures exceed the bounded root interface.')
        offset += len(line)
    return result


def root_coverage(objective, request, mapping):
    """Host-checked attribution frontier; model-declared entailment is unproven."""
    request = C.normalize_request(request)
    if request['objective'] != objective:
        raise ProjectError('Coverage cannot change the original objective.')
    _concrete_requirements(request)
    caller_exports = required_public_exports(objective)
    proposed_exports = {row['name']: row['signature'] for row in request['exports']}
    for item in caller_exports:
        # Only insignificant whitespace is canonicalized; parameter names/order
        # and function names remain the caller's declared interface.
        if re.sub(r'\s+', '', proposed_exports.get(item['name'], '')) != item['signature']:
            raise ProjectError('Root proposal omitted or changed an explicitly declared public function signature.')
    clauses = objective_clauses(objective)
    C._bounded(mapping)
    if type(mapping) is not list or not 1 <= len(mapping) <= MAX_OBJECTIVE_CLAUSES:
        raise ProjectError('Objective coverage must be a bounded nonempty clause mapping.')
    requirements = {row['id']: row for row in request['requirements']}
    known = {row['id'] for row in clauses}; assigned = {}; referenced = set()
    for item in mapping:
        if type(item) is not dict or set(item) != {'clause_id', 'requirement_ids'}:
            raise ProjectError('Coverage contains clause_id and requirement_ids only; no proof or origin authority.')
        ident = item['clause_id']
        if type(ident) is not str or ident not in known or ident in assigned:
            raise ProjectError('Coverage contains an unknown or duplicate objective clause.')
        ids = C._strings(item['requirement_ids'], 'coverage_requirements', nonempty=True)
        if not set(ids) <= set(requirements):
            raise ProjectError('Coverage refers to unknown root requirements.')
        assigned[ident] = set(ids); referenced.update(ids)
    if set(assigned) != known or referenced != set(requirements):
        raise ProjectError('Every exact objective clause and every proposed requirement must have a declared coverage mapping.')
    test_coverage = {ident: [index for index, test in enumerate(request['tests']) if ident in test['requirement_ids']]
                     for ident in requirements}
    if any(not indices for indices in test_coverage.values()):
        raise ProjectError('Every mapped requirement must retain at least one public acceptance check.')
    result = {'version': ROOT_COVERAGE_VERSION, 'objective_sha256': C.digest(objective),
              'request_sha256': C.digest(request), 'span_unit': 'Unicode_code_points',
              'caller_exports': caller_exports,
              'export_extraction_scope': 'simple_signatures_under_explicit_required_public_functions_header',
              'clauses': [{**row, 'requirement_ids': [ident for ident in requirements if ident in assigned[row['id']]]}
                          for row in clauses],
              'requirements': [{'id': ident, 'requirement_sha256': C.digest(requirement),
                  'clause_ids': [row['id'] for row in clauses if ident in assigned[row['id']]],
                  'public_test_indices': test_coverage[ident], 'origin': 'model_proposed'}
                  for ident, requirement in requirements.items()],
              'scope': 'exact_objective_spans_and_model_declared_mapping_only',
              'structural_coverage': 'complete', 'semantic_correspondence': 'unassessed',
              'semantic_completeness': 'unassessed', 'independent_acceptance': 'not_established'}
    result['sha256'] = C.digest(result)
    return result


def _body(row):
    return {key: value for key, value in row.items() if key != "sha256"}


def _read(root, name):
    return G._unseal(G._read(Path(root) / name))


def _exists(root, name):
    path = Path(root) / name
    return path.exists() or path.is_symlink()


def _identity():
    current = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if current != _LOADED_SHA256:
        raise ProjectError("Project adapter changed on disk; use a fresh process.")
    problems = I.audit({I.relative_path(__file__): _LOADED_SHA256})
    if problems:
        raise ProjectError("Project executing source identity refused: " + "; ".join(problems))
    return {"version": VERSION, "project": current, "root_spec_version": ROOT_SPEC_VERSION,
            "proposal_encoding": Q.identity(), "construction": M.implementation_identity()}


def load_project(folder):
    """Read a sealed original objective/budget/inventory for exact CLI resume."""
    result = _body(_read(folder, MANIFEST))
    if result.get("version") != VERSION:
        raise ProjectError("Unsupported project version.")
    return result



def _verify_proposal_encoding(folder, manifest, token, report):
    """Rebuild syntactic lowering from the exact linked native output, read-only."""
    required = "proposal_encoding" in manifest.get("identity", {})
    receipt = token.get("proposal_encoding")
    if receipt is None and not required and "proposal_encoding" not in report:
        return
    if type(receipt) is not dict or report.get("proposal_encoding") != receipt:
        raise ProjectError("Project proposal encoding receipt is missing or inconsistent.")
    attempt = receipt.get("native_attempt")
    if type(attempt) is not str or re.fullmatch(r"root-[0-9]{3}", attempt) is None:
        raise ProjectError("Project proposal encoding names an invalid native attempt.")
    native = _read(Path(folder) / "root-attempts" / attempt, "mica-native-result.json")
    if (native.get("status") != "done" or native.get("pins_sha256") != receipt.get("native_pins_sha256")
            or native.get("pins_sha256") != token.get("native_pins_sha256")):
        raise ProjectError("Project proposal encoding is detached from its native result.")
    root_calls = token.get("root_calls")
    if type(root_calls) is not int or not 0 <= root_calls <= manifest["budget"]["max_calls"]:
        raise ProjectError("Project root call allocation is invalid.")
    budget = {**manifest["budget"], "max_calls": manifest["budget"]["max_calls"] - root_calls}
    request, decisions, coverage, checked = _proposal_with_encoding(
        native.get("output"), manifest["objective"], manifest["allowed_outputs"], budget,
        artifact_format=manifest.get("artifact_format", "javascript_script"))
    checked = {**checked, "native_attempt": attempt, "native_pins_sha256": native["pins_sha256"]}
    if checked != receipt or decisions or request != token["request"] or coverage != token.get("root_coverage"):
        raise ProjectError("Project proposal encoding differs from its exact retained source and request.")


def read_project_result(folder):
    """Read the latest report, validating its immutable manifest/request links.

    This is a read-only receipt inspection, not a replay or fresh execution check.
    Native journal auditing occurs when the project is resumed.
    """
    manifest = load_project(folder)
    name = RESULT if _exists(folder, RESULT) else PLAN if _exists(folder, PLAN) else None
    if name is None:
        return None
    row = _read(folder, name)
    sources = manifest.get("identity", {}).get("construction", {}).get("sources", {})
    if any(name in sources for name in M._COST_SOURCES) and "host_costs" not in row:
        raise ProjectError("Instrumented project result is missing its cost summary.")
    if row.get("manifest_sha256") != G._hash(manifest):
        raise ProjectError("Project result is detached from its original objective.")
    if row.get("request") is not None:
        token = _read(folder, REQUEST)
        if (token.get("manifest_sha256") != G._hash(manifest)
                or C.normalize_request(token["request"]) != row["request"]
                or row.get("request_sha256") != C.digest(token["request"])):
            raise ProjectError("Project result has a different accepted root request.")
        if 'root_coverage' in token or 'root_coverage' in row:
            coverage = token.get('root_coverage')
            if type(coverage) is not dict:
                raise ProjectError('Project root coverage receipt is missing.')
            parts = coverage.get('clauses')
            if type(parts) is not list or not 1 <= len(parts) <= MAX_OBJECTIVE_CLAUSES or any(
                    type(part) is not dict or 'id' not in part or 'requirement_ids' not in part for part in parts):
                raise ProjectError('Project root coverage receipt has an invalid clause frontier.')
            mapping = [{'clause_id': part['id'], 'requirement_ids': part['requirement_ids']}
                       for part in parts]
            checked = root_coverage(manifest['objective'], token['request'], mapping)
            if checked != coverage or row.get('root_coverage') != checked:
                raise ProjectError('Project root coverage differs from its exact objective and request.')
        _verify_proposal_encoding(folder, manifest, token, row)
    if row.get("child") is not None:
        if _exists(Path(folder) / "construction", "mica-result.json") and _read(Path(folder) / "construction", "mica-result.json") != row["child"]:
            raise ProjectError("Project result disagrees with its construction receipt.")
        M.verify_result_artifacts(row['child'], row['request'], manifest['identity']['construction'])
        M.verify_host_costs(row['child'], Path(folder) / 'construction', manifest['identity']['construction'])
        if row['status'] == 'done' and any(row.get(k) != row['child'].get(k) for k in ('output', 'bundle', 'module_checks')):
            raise ProjectError('Project artifacts or checks differ from the accepted child receipt.')
    if row.get('status') not in ('planned', 'unknown', 'stopped') and 'host_costs' in row:
        roots = Path(folder) / 'root-attempts'
        G._safe_listing(roots, 5000)
        summaries = []
        for attempt in sorted(roots.iterdir()):
            if attempt.is_symlink() or not attempt.is_dir():
                raise ProjectError('Invalid native cost directory.')
            summaries.append(N.cost_summary(attempt))
        if row.get('child') is not None:
            summaries.append(row['child'].get('host_costs', T.summarize([])))
        if row['host_costs'] != T.combine(summaries):
            raise ProjectError('Project costs differ from its retained native and construction journals.')
    if row.get('bundle') is not None:
        M.B.verify_bundle(row['bundle'], runtime_identity=manifest['identity']['construction'])
        if row.get('child', {}).get('bundle') != row['bundle'] or row['bundle']['request'] != row.get('request'):
            raise ProjectError('Project bundle differs from its construction receipt.')
    if manifest.get('artifact_format') == 'javascript_modules' and row['status'] == 'done' and (
            row.get('bundle') is None or row.get('module_checks', {}).get('passed') is not True):
        raise ProjectError('Completed module project is missing its bundle or checks.')
    return row


def _outputs(values):
    values = C._strings(values, "allowed_outputs", nonempty=True)
    for value in values:
        C._path(value)
    if any(a != b and b.startswith(a + "/") for a in values for b in values):
        raise ProjectError("Allowed output files cannot be ancestors of one another.")
    return values


def root_proposal_schema():
    """Wire shape only; original objective and authority checks remain independent."""
    text = {'type': 'string'}
    strings = {'type': 'array', 'items': text}
    def obj(properties, required=None):
        return {'type': 'object', 'properties': properties, 'required': list(properties) if required is None else required,
                'additionalProperties': False}
    return obj({'proposal_version': {'const': ROOT_SPEC_VERSION},
        'request': {'anyOf': [{'type': 'null'}, obj({'objective': text, 'language': {'const': 'javascript'},
            'requirements': {'type': 'array', 'minItems': 1, 'items': obj({'id': text, 'text': text,
                'acceptance': {'enum': ['TESTED', 'PROVEN']}})},
            'exports': {'type': 'array', 'minItems': 1, 'items': obj({'name': text, 'signature': text})},
            'tests': {'type': 'array', 'minItems': 1, 'items': obj({'requirement_ids': strings, 'call': text, 'expected_value': {}})},
            'assumptions': strings, 'allowed_outputs': strings})]},
        'objective_coverage': {'type': 'array', 'items': obj({'clause_id': text, 'requirement_ids': strings})},
        'missing_decisions': {'type': 'array', 'items': obj({'id': text, 'question': text, 'why_consequential': text})}})


def root_prompt(objective, allowed_outputs, *, feedback=None, artifact_format='javascript_script'):
    """Only the public objective, declared paths and bounded error enter context."""
    schema = root_proposal_schema()
    row = {"role": "Propose an explicit JavaScript construction request for this objective.",
           "objective": objective, "allowed_outputs": allowed_outputs, "artifact_format": artifact_format,
           "objective_clauses": objective_clauses(objective),
           "caller_declared_exports": required_public_exports(objective),
           "output_format": schema,
           "rules": ["Return one raw JSON answer object without a fence or wrapper, with exactly proposal_version, request, objective_coverage and missing_decisions. Use proposal_version 3.",
               "Do not return this prompt, objective/allowed_outputs at top level, JSON Schema, or output_format. Instantiate the reply schema with task-specific values.",
               "Copy the original objective and allowed_outputs exactly. Do not propose a budget.",
               "Preserve every caller_declared_exports function name and signature in request.exports; these exact source declarations are caller authority.",
               "Preserve all requested behavior; state routine interpretation choices as assumptions.",
               "Map every supplied objective clause ID to nonempty requirement_ids in objective_coverage. Map every proposed requirement to at least one clause.",
               "Clause mappings are proposed attribution only, not proof that the requirement or tests fully capture the clause.",
               "Write concrete task-specific requirements and checks. There are no sample function names, behavior or expected answers to copy.",
               "Supply nonempty concrete requirements, public function signatures and executable checks.",
               "Each test.expected_value is the actual JSON value, not a JSON document encoded inside a string. Strings remain strings. Every requirement must have a check. Exception behavior needs a JavaScript call expression that catches the error and returns a JSON value; an error message string does not assert that an exception was thrown.",
               "Generated requirements/tests are model proposals, not independent evidence of user intent.",
               "TESTED means only the finite encoded checks. Do not claim universal semantic proof.",
               "Use PROVEN only if the objective explicitly requires proof; this lane cannot prove arbitrary JavaScript.",
               "This lane constructs pure JavaScript functions. It grants no network, files, shell, deployment or other effects.",
               "Do not ask for approval. Resolve routine choices as explicit assumptions.",
               "Only consequential incompatible choices or unsupported requested effects belong in missing_decisions.",
               "Each missing decision has id, question and why_consequential. In that case request may be null and objective_coverage must be empty."]}
    if feedback is not None:
        row["verified_failure"] = feedback
    prefix = ('Produce a new task-specific construction specification. Do not echo, rearrange or summarize the input envelope. '
              'Return exactly one raw JSON answer object without a fence or wrapper, with these four top-level keys: '
              'proposal_version (3), request, objective_coverage, missing_decisions. The request contains the proposed requirements, exports and tests. '
              'The original objective and declared public signatures must be preserved. '
              'The JSON Schema below is a shape guide, not an answer: do not return schema properties, output_format, role or rules. '
              'Invent no approval requirement. Use concrete behaviors and checks from the objective; provide no generic sample program.')
    return prefix + ROOT_INPUT_MARKER + json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _proposal(text, objective, outputs, child_budget, *, artifact_format='javascript_script'):
    """Compatibility entry point: existing callers receive the original three fields."""
    return _proposal_with_encoding(text, objective, outputs, child_budget,
                                   artifact_format=artifact_format)[:3]


def _proposal_with_encoding(text, objective, outputs, child_budget, *, artifact_format='javascript_script'):
    try:
        row, encoding = Q.decode(text)
    except Q.ProposalEncodingError as error:
        raise ProjectError(str(error)) from error
    C._bounded(row)
    if type(row) is not dict or set(row) != {"request", "objective_coverage", "missing_decisions"}:
        raise ProjectError("Root answer must contain exactly request, objective_coverage and missing_decisions; prompt/schema copies are not answers.")
    decisions = row["missing_decisions"]
    if type(decisions) is not list or len(decisions) > 16:
        raise ProjectError("Missing decisions must be a bounded list.")
    ids = set()
    for decision in decisions:
        if type(decision) is not dict or set(decision) != {"id", "question", "why_consequential"}:
            raise ProjectError("Every missing decision needs id, question and why_consequential.")
        ident = C._identifier(decision["id"])
        if ident in ids:
            raise ProjectError("Missing decision IDs must be unique.")
        ids.add(ident)
        C._text(decision["question"], "question", 4000)
        C._text(decision["why_consequential"], "why_consequential", 4000)
    if row["request"] is None and decisions:
        if row['objective_coverage'] != []:
            raise ProjectError('An unresolved null request cannot claim objective coverage.')
        return None, decisions, None, encoding
    request = row["request"]
    if type(request) is not dict or "budget" in request:
        raise ProjectError("Root model cannot supply construction budget authority.")
    if request.get("objective") != objective or request.get("allowed_outputs") != outputs:
        raise ProjectError("Root model changed the original objective or output authority.")
    if request.get('artifact_format', artifact_format) != artifact_format:
        raise ProjectError('Root model changed the caller artifact format.')
    request = C.normalize_request({**request, "budget": child_budget, 'artifact_format': artifact_format})
    coverage = root_coverage(objective, request, row['objective_coverage'])
    return request, decisions, coverage, encoding


class MicaProject:
    """Generate a root specification, then plan/build under one frozen budget.

    The injected Apps object is a symblic.providers.applicators.Applicators (or a compatible fake).
    The original objective is never replaced by a model summary. This constructor
    neither starts work nor reads files outside its explicit project workspace.
    """
    def __init__(self, objective, folder, apps, inventory, budget, allowed_outputs, stop=None, *, library=None,
                 calibration=None, artifact_format='javascript_script'):
        self.objective = C._text(objective, "objective")
        self.root = Path(folder)
        self.apps = apps
        self.inventory = R.normalize_inventory(inventory)
        self.budget = C._budget(budget)
        self.outputs = _outputs(allowed_outputs)
        if artifact_format not in ('javascript_script', 'javascript_modules'):
            raise ProjectError('Unknown artifact format.')
        if artifact_format == 'javascript_script' and len(self.outputs) != 1:
            raise ProjectError('Script construction needs exactly one output path.')
        if artifact_format == 'javascript_modules' and any(not p.endswith(('.js', '.mjs')) or p == '__symblic_test__.mjs' for p in self.outputs):
            raise ProjectError('Module outputs require .js/.mjs paths outside the reserved verifier module.')
        self.artifact_format = artifact_format
        self.calibration = M.H.normalize(calibration, G._hash(M.implementation_identity())) if calibration is not None else None
        self.library = str(Path(library).absolute()) if library is not None else None
        if self.library is not None and any(path.is_symlink() for path in (Path(self.library), *Path(self.library).parents)):
            raise ProjectError("Symlinked component library refused.")
        self.stop = stop if stop is not None else threading.Event()
        self.started_monotonic = time.monotonic()
        self.native_results = []

    def _deadline_expired(self, manifest):
        start = manifest["started_ms"] / 1000
        now = time.time()
        return (now < start or now >= start + self.budget["wall_seconds"]
                or time.monotonic() - self.started_monotonic >= self.budget["wall_seconds"])

    def _expired(self, manifest):
        return self.stop.is_set() or self._deadline_expired(manifest)

    def _route(self):
        rows = R.rank_models({"model_eligibility": {"task_class": "root_specification"},
                              "resource_budget": {"context_chars": self.budget["context_chars"]}},
                             self.inventory, [])
        for row in rows:
            route = {"id": "root-specification", "provider": "ollama", "model": row["model"],
                     "node": row["node"], "digest": row["digest"], "local": True}
            try:
                N.route_label(route)
            except N.NativeError:
                continue
            return route
        return None

    def _audit_root(self):
        """Audit every retained root delivery before any possible new dispatch."""
        folder = self.root / "root-attempts"
        G._safe_listing(folder, self.budget["max_candidates"])
        paths = sorted(folder.iterdir())
        uncertain, records = [], []
        for index, path in enumerate(paths):
            if path.name != f"root-{index:03}" or path.is_symlink() or not path.is_dir():
                raise ProjectError("Invalid or noncontiguous root attempt directory.")
            if not _exists(path, "mica-native-pins.json"):
                if any(path.iterdir()):
                    raise ProjectError("Unpinned root attempt data requires inspection.")
                continue
            inspection = N.inspect_attempt(path)
            observations = G._read(path / "mica-provider-evidence.jsonl", lines=True, missing=True)
            records.append({"calls": inspection["calls"], "provider_evidence": [G._unseal(row) for row in observations],
                            "host_costs": N.cost_summary(path)})
            if inspection["status"] == "unknown":
                uncertain.append(path.name)
        return paths, records, uncertain

    def _synthesize(self, manifest):
        paths, retained, uncertain = self._audit_root()
        self.native_results = retained
        if uncertain:
            return {"status": "unknown", "failure": "UNRESOLVED_EFFECT",
                    "error": "Retained root attempts have unresolved deliveries: " + ", ".join(uncertain)}, None
        if self.budget["wall_seconds"] < 30:
            return {"status": "exhausted", "failure": "RESOURCE_EXHAUSTION",
                    "error": "The original wall allowance is below the root provider's 30-second minimum."}, None
        route, feedback = self._route(), None
        if route is None:
            return {"status": "blocked", "failure": "NO_ELIGIBLE_LOCAL_MODEL"}, None
        root_calls = 0
        self.native_results = []
        count = min(self.budget["max_candidates"], self.budget["max_calls"])
        for index in range(count):
            folder = self.root / "root-attempts" / f"root-{index:03}"
            if not _exists(folder, "mica-native-pins.json") and self._expired(manifest):
                expired = self._deadline_expired(manifest)
                return {"status": "exhausted" if expired else "stopped", "failure": "RESOURCE_EXHAUSTION" if expired else "STOPPED",
                        "error": "Original project deadline expired." if expired else "Project stopped before dispatch."}, None
            try:
                prompt = root_prompt(self.objective, self.outputs, feedback=feedback, artifact_format=self.artifact_format)
            except (ProjectError, C.ContractError) as error:
                return {"status": "blocked", "failure": "INVALID_ROOT_REQUEST", "error": str(error)}, None
            if len(prompt) > self.budget["context_chars"]:
                return {"status": "blocked", "failure": "CONTEXT_EXHAUSTION", "error": "Complete root context exceeds its allowance."}, None
            source = N.planner_source(prompt, route, context_chars=self.budget["context_chars"], schema=root_proposal_schema())
            # Same allowance and options on every replay; the original project
            # timer provides the deadline across root synthesis and construction.
            options = {"ollama_limits": {"num_predict": 4096, "num_ctx": 16384,
                       "timeout_seconds": min(900, self.budget["wall_seconds"]),
                       "total_timeout_seconds": self.budget["wall_seconds"]}}
            result = N.execute(source, folder, self.apps, route, limit=1,
                               output_binding="proposal", stop=self.stop, options=options)
            self.native_results.append(result)
            root_calls += result["calls"]
            if result["status"] == "unknown":
                return {"status": "unknown", "failure": "UNRESOLVED_EFFECT", "error": result.get("error")}, None
            if result["status"] == "stopped":
                return {"status": "stopped", "failure": "STOPPED", "error": result.get("error")}, None
            if result["status"] in ("blocked", "exhausted"):
                return {"status": result["status"], "failure": M.failure_class(result), "error": result.get("error")}, None
            if result["status"] != "done":
                feedback = {"failure": M.failure_class(result), "error": result.get("error")}
                continue
            child_budget = {**self.budget, "max_calls": self.budget["max_calls"] - root_calls}
            try:
                request, decisions, coverage, encoding = _proposal_with_encoding(
                    result["output"], self.objective, self.outputs, child_budget,
                    artifact_format=self.artifact_format)
            except (ProjectError, C.ContractError) as error:
                feedback = {"failure": "INVALID_ROOT_REQUEST", "error": str(error)}
                continue
            if decisions:
                if len(paths) > index + 1:
                    raise ProjectError("Unexpected native attempts follow the accepted root proposal.")
                return {"status": "missing_decisions", "failure": "CONSEQUENTIAL_AMBIGUITY",
                        "missing_decisions": decisions, "proposed_request": request}, None
            token = {"version": VERSION, "manifest_sha256": G._hash(manifest), "request": request,
                     "root_calls": root_calls, "native_pins_sha256": result["pins_sha256"],
                     "provenance": self._provenance(request), "root_coverage": coverage,
                     "proposal_encoding": {**encoding, "native_attempt": folder.name,
                                           "native_pins_sha256": result["pins_sha256"]},
                     "deadline_ms": manifest["started_ms"] + self.budget["wall_seconds"] * 1000}
            if len(paths) > index + 1:
                raise ProjectError("Unexpected native attempts follow the accepted root proposal.")
            frozen = N._put_once(self.root, REQUEST, token)
            return {"status": "specified"}, frozen
        return {"status": "exhausted", "failure": "RESOURCE_EXHAUSTION",
                "error": "Root specification allowance exhausted.", "last_failure": feedback}, None

    def _provenance(self, request):
        return {"objective": "caller", "allowed_outputs": "caller", "artifact_format": "caller",
                "budget": "caller_with_bounded_defaults",
                "requirements": "model_proposed", "exports": "model_proposed", "assumptions": "model_proposed",
                "acceptance_tests": "model_proposed_not_independent", "caller_acceptance_tests": None,
                "objective_sha256": C.digest(self.objective),
                "proposed_tests_sha256": C.digest(request["tests"]) if request else None,
                "coverage_mapping": "model_proposed_exact_objective_spans_host_checked",
                "semantic_completeness": "unassessed",
                "scope": "Finite encoded checks only; generated checks do not establish adequacy to caller intent."}

    def plan(self, mode="mica"):
        """Propose and freeze the request and plan without building anything."""
        return self.execute(mode, plan_only=True)

    def execute(self, mode="mica", *, plan_only=False):
        if mode not in M.MODES:
            raise ProjectError("Unknown construction strategy.")
        if any(path.is_symlink() for path in (self.root, *self.root.parents)):
            raise ProjectError("Symlinked project workspace refused.")
        G._mkdir_private(self.root)
        G._safe_listing(self.root, 1024)
        G._mkdir_private(self.root / "root-attempts")
        fd = os.open(self.root / ".mica-project.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        timer = None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            old = load_project(self.root) if _exists(self.root, MANIFEST) else None
            manifest = {"version": VERSION, "objective": self.objective, "budget": self.budget,
                        "run_id": old['run_id'] if old else uuid.uuid4().hex,
                        "allowed_outputs": self.outputs, "inventory": self.inventory, "mode": mode,
                        "library": self.library, 'calibration': self.calibration, 'artifact_format': self.artifact_format,
                        "identity": _identity(), "started_ms": old["started_ms"] if old else int(time.time() * 1000)}
            N._put_once(self.root, MANIFEST, manifest)
            if self._expired(manifest):
                self.stop.set()
            remaining = max(0, manifest["started_ms"] / 1000 + self.budget["wall_seconds"] - time.time())
            timer = threading.Timer(remaining, self.stop.set)
            timer.daemon = True
            timer.start()
            result, token = self._synthesize(manifest)
            child = None
            if token is not None:
                child_run = M.MicaRun(token["request"], self.root / "construction", self.apps, self.inventory,
                                      stop=M.DeadlineStop(self.stop, token['deadline_ms']),
                                      library=self.library, calibration=self.calibration)
                child = child_run.plan(mode) if plan_only else child_run.execute(mode)
                result = {key: child[key] for key in ("status", "failure", "error", "output", "plan", 'bundle', 'module_checks') if key in child}
                result["assurance"] = ("TESTED_MODEL_PROPOSED_CHECKS" if child["status"] == "done"
                                       else "MODEL_PROPOSED_CONTRACT_GRAPH" if child["status"] == "planned"
                                       else "NO_ACCEPTED_ARTIFACT")
            if result["status"] == "stopped" and self._deadline_expired(manifest):
                result = {**result, "status": "exhausted", "failure": "RESOURCE_EXHAUSTION"}
            return self._report(manifest, result, token, child)
        finally:
            if timer is not None:
                timer.cancel()
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _report(self, manifest, result, token, child):
        root_calls = sum(row["calls"] for row in self.native_results)
        child_calls = child["calls"] if child else 0
        calls = root_calls + child_calls
        if calls > self.budget["max_calls"]:
            raise ProjectError("Project calls exceed the original frozen allocation.")
        evidence = [row["observed"] for native in self.native_results for row in native.get("provider_evidence", [])]
        measurements = {}
        for field in ("input_tokens", "output_tokens", "latency_ms"):
            values = [row.get("ms") if field == "latency_ms" else (row.get("usage") or {}).get(field) for row in evidence]
            known = [value for value in values if type(value) is int and value >= 0]
            other = child["measurements"][field] if child else {"known_sum": 0, "known_calls": 0, "unknown_calls": 0}
            nknown = len(known) + other["known_calls"]
            total = sum(known) + other["known_sum"]
            measurements[field] = {"known_sum": total, "known_calls": nknown,
                                   "unknown_calls": max(0, calls - nknown), "total": total if nknown == calls else None}
        request = token["request"] if token else None
        report = {"version": VERSION, **result, "objective": self.objective, "request": request,
                  "request_sha256": C.digest(request) if request else None, "manifest_sha256": G._hash(manifest),
                  "root_calls": root_calls, "construction_calls": child_calls, "calls": calls,
                  "calls_reserved_or_spent": root_calls + (child["calls_reserved_or_spent"] if child else 0),
                  "provenance": self._provenance(request), "child": child, "measurements": measurements,
                  "root_coverage": token.get('root_coverage') if token else None,
                  "proposal_encoding": token.get('proposal_encoding') if token else None,
                  "host_costs": T.combine([n.get("host_costs", T.summarize([])) for n in self.native_results]
                                         + ([child.get("host_costs", T.summarize([]))] if child else [])),
                  "costs": {"provider_calls": calls, "input_tokens": measurements["input_tokens"]["total"],
                            "output_tokens": measurements["output_tokens"]["total"],
                            "provider_ms": measurements["latency_ms"]["total"],
                            "wall_seconds": max(0, time.time() - manifest["started_ms"] / 1000),
                            "cpu_seconds": None, "memory_bytes": None},
                  "evidence": {"root_native_attempts": "root-attempts/", "construction": "construction/",
                               "deadline_ms": manifest["started_ms"] + self.budget["wall_seconds"] * 1000,
                               "scope": "Native journal and finite model-proposed checks; no independent intent-adequacy claim."}}
        if report["status"] in ("unknown", "stopped"):
            return report
        name = PLAN if report["status"] == "planned" else RESULT
        if _exists(self.root, name):
            old = _read(self.root, name)
            report["costs"]["wall_seconds"] = old["costs"]["wall_seconds"]
        return N._put_once(self.root, name, report)
