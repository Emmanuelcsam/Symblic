"""Native scalar checker: re-runs a Symblic program's own `ensure` predicates on a recorded answer.

What it is for
    Distillation evaluation (symblic/distill/worker.py) can grade a model's answer with the *native* checks of the
    Symblic program the training item came from, instead of comparing against a reference answer. This module is
    that checker. Given a contract (source hash, statement hash, kernel id, predicate hashes) and an answer, it
    finds the original program in a trusted *contract bundle*, coerces the answer to the declared Symblic type and
    evaluates exactly the recorded closed predicates with the native kernel.

Trust model
    The operator builds the bundle with symblic/distill/contracts.py (``symblic-distill export-contracts``) and
    stages it at BUNDLE_FILE. The bundle pins the kernel id and the SHA-256 of every Symblic source file
    (``runtime_hashes``); any drift refuses. Each check runs in a separate ``python -I -B`` process with CPU,
    memory, file-size and core-dump limits, executing exactly the source bytes the worker loaded. Predicates may
    use only a small whitelist of syntax nodes and pure builtins (SAFE_NODES, SAFE_CALLS).

What a pass means
    The encoded predicates of the original program hold for this answer under the recorded kernel. It does not
    mean the answer is true or that the predicates capture the author's intent.

Depends on: ``symblic.kernel.language`` / ``evidence`` (inside the checking process), ``symblic.mica.source_identity``
(loaded-source audit). Loaded by symblic/distill/worker.py through its fixed CHECKER_MODULE_PATH; never imported
with a caller-chosen path. Imports are inert; no provider or network is used.
"""

from __future__ import annotations
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
import subprocess
import sys
from fractions import Fraction

# Where the operator stages the trusted contract bundle. Fixed on purpose: no caller can point the checker elsewhere.
BUNDLE_FILE = Path.home() / ".local/state/symblic-distill/native-contracts.json"
# Source files every native runtime snapshot must contain (the checking process always executes these).
CORE_RUNTIME = ("symblic/kernel/language.py", "symblic/kernel/evidence.py", "symblic/kernel/identity.py")
# Never part of the runtime snapshot: the distillation tooling itself (this file is pinned separately).
EXCLUDED_RUNTIME = "symblic/distill/"
MAX_RUNTIME_FILES = 2000
MAX_BYTES = 16_000_000
SAFE_NODES = {
    "num",
    "lit",
    "str",
    "name",
    "list",
    "set",
    "record",
    "range",
    "un",
    "bin",
    "cmp",
    "cond",
    "quant",
    "comp",
    "attr",
    "index",
    "call",
}
SAFE_CALLS = {"abs", "sum", "product", "min", "max", "len", "count"}


class NativeContractError(ValueError):
    """A refused bundle, contract or runtime (a finite code, never caller text)."""


def digest(value):
    """SHA-256 of canonical JSON."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _bounded_bytes(path, limit):
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise NativeContractError("not_regular_file")
    with p.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise NativeContractError("file_too_large")
    return raw


def file_hash(path):
    """SHA-256 of a bounded regular file."""
    return hashlib.sha256(_bounded_bytes(path, 8_000_000)).hexdigest()


def read_bundle(path):
    """Read a contract bundle and check its own digest."""
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_BYTES:
        raise NativeContractError("invalid_contract_bundle")
    b = json.loads(_bounded_bytes(p, MAX_BYTES))
    body = {k: v for k, v in b.items() if k != "bundle_sha256"}
    if b.get("version") != 1 or digest(body) != b.get("bundle_sha256"):
        raise NativeContractError("bundle_digest_mismatch")
    return b


def pack(value):
    """A kernel value (nodes, fractions, tuples) as plain JSON that unpack() restores exactly."""
    from symblic.kernel import language as S

    if isinstance(value, S.Node):
        return {"$node": {k: pack(v) for k, v in vars(value).items()}}
    if value is None or type(value) in (bool, int, str):
        return value
    if isinstance(value, Fraction):
        return {"$fraction": [value.numerator, value.denominator]}
    if type(value) is tuple:
        return {"$tuple": [pack(v) for v in value]}
    if type(value) is list:
        return [pack(v) for v in value]
    if type(value) is dict and all(type(k) is str for k in value):
        return {"$dict": {k: pack(v) for k, v in value.items()}}
    raise NativeContractError("unsupported_native_value")


def unpack(value):
    """The inverse of pack()."""
    from symblic.kernel import language as S

    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is list:
        return [unpack(v) for v in value]
    if type(value) is not dict or len(value) != 1:
        raise NativeContractError("invalid_native_value")
    if "$node" in value:
        d = {k: unpack(v) for k, v in value["$node"].items()}
        return S.Node(**d)
    if "$fraction" in value:
        return Fraction(*value["$fraction"])
    if "$tuple" in value:
        return tuple(unpack(v) for v in value["$tuple"])
    if "$dict" in value:
        return {k: unpack(v) for k, v in value["$dict"].items()}
    raise NativeContractError("invalid_native_value")


def validate_ast(node):
    """Refuse predicate syntax outside SAFE_NODES / SAFE_CALLS, or too deep or too large."""
    from symblic.kernel import language as S

    count = 0

    def walk(v, depth=0):
        nonlocal count
        if depth > 64:
            raise NativeContractError("predicate_too_deep")
        count += 1
        if count > 10000:
            raise NativeContractError("predicate_too_large")
        if isinstance(v, S.Node):
            if v.k not in SAFE_NODES or (v.k == "call" and v.fn not in SAFE_CALLS):
                raise NativeContractError("unsupported_predicate")
            for x in vars(v).values():
                walk(x, depth + 1)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x, depth + 1)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x, depth + 1)

    walk(node)


def capture_check(statement, env, receipt):
    """The predicate syntax and the closed context bindings of one check, for the bundle."""
    from symblic.kernel import language as S

    validate_ast(statement.cond)
    bindings = {}
    for name in sorted(S.free_names(statement.cond)):
        b = env.lookup(name)
        if b is None:
            continue
        ep = (b.meta or {}).get("epistemic", {}).get("assessment", {})
        bindings[name] = {
            "value": pack(b.value),
            "type": pack(b.type),
            "line": b.line,
            "class": b.klass,
            "closed": ep.get("lineage_complete") is True
            and ep.get("conditional_on") == [],
            "hash": b.hash,
        }
    return {"receipt": receipt, "ast": pack(statement.cond), "bindings": bindings}


def _relative_source(name):
    """True for a repository-relative POSIX path of a Symblic source file: symblic/.../name.py, no '..'."""
    parts = name.split("/") if type(name) is str else []
    return (len(parts) >= 2 and parts[0] == "symblic" and name.endswith(".py") and "\\" not in name
            and all(part and part not in (".", "..") for part in parts))


def runtime_hashes(repo):
    """{repository-relative path: sha256} of every Symblic source file under repo/symblic.

    The distillation tooling (symblic/distill/) is left out; caches are ignored. A file that is a symlink
    refuses. This is the disk snapshot a contract bundle pins as its native runtime.
    """
    root = Path(repo).resolve()
    names = []
    for path in sorted((root / "symblic").rglob("*.py")):
        name = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or name.startswith(EXCLUDED_RUNTIME):
            continue
        names.append(name)
        if len(names) > MAX_RUNTIME_FILES:
            raise NativeContractError("runtime_too_large")
    return {name: file_hash(root / name) for name in names}


def _loaded_runtime(root):
    """Repository-relative paths of the Symblic modules loaded in this process from `root` that carry an
    import-identity marker (unmarked modules, such as package __init__ files, are disk-pinned only)."""
    package = (root / "symblic").resolve()
    loaded = set()
    for module in tuple(sys.modules.values()):
        namespace = getattr(module, "__dict__", None)
        file = namespace.get("__file__") if isinstance(namespace, dict) else None
        if type(file) is not str or "_symblic_import_identity" not in namespace:
            continue
        try:
            path = Path(file).resolve()
            path.relative_to(package)
        except (OSError, ValueError):
            continue
        name = path.relative_to(root.resolve()).as_posix()
        if name.endswith(".py") and not name.startswith(EXCLUDED_RUNTIME):
            loaded.add(name)
    return loaded


def verify_runtime(bundle):
    """Check the bundle's runtime against disk and against the code loaded in this process; return the kernel.

    Refuses: a changed or unlisted source file (stale_runtime_source), a snapshot missing a core file or a loaded
    module (incomplete_native_runtime), a kernel already imported from another checkout (mixed_native_runtime),
    a different kernel id (stale_kernel), or loaded code that differs from the pinned bytes
    (loaded_native_identity_mismatch).
    """
    root = Path(bundle["runtime_root"])
    if not root.is_absolute() or root.is_symlink():
        raise NativeContractError("runtime_path")
    pins = bundle["runtime_sha256"]
    for name, expected in pins.items():
        if not _relative_source(name) or file_hash(root / name) != expected:
            raise NativeContractError("stale_runtime_source")
    if not set(CORE_RUNTIME) <= pins.keys():
        raise NativeContractError("incomplete_native_runtime")
    # Never mix an already-imported engine with a different frozen runtime.
    for module_name, name in (("symblic.kernel.language", "symblic/kernel/language.py"),
                              ("symblic.kernel.evidence", "symblic/kernel/evidence.py")):
        m = sys.modules.get(module_name)
        if m is not None and Path(m.__file__).resolve() != (root / name).resolve():
            raise NativeContractError("mixed_native_runtime")
    sys.path.insert(0, str(root))
    from symblic.kernel import language as S
    from symblic.kernel import evidence as _E  # noqa: F401  (loaded now so the audit below covers it)

    if S.kernel_id()["id"] != bundle["kernel_id"]:
        raise NativeContractError("stale_kernel")
    from symblic.mica import source_identity as I

    # Every marked Symblic module executing here must be pinned by the bundle and match its pinned bytes.
    loaded = _loaded_runtime(root)
    if not loaded <= pins.keys():
        raise NativeContractError("incomplete_native_runtime")
    if I.audit({name: pins[name] for name in sorted(loaded)}):
        raise NativeContractError("loaded_native_identity_mismatch")
    return S


def contract_key(contract):
    """The bundle key of a contract."""
    return digest(contract)


def evaluate(bundle, contract, answer):
    """Evaluate a contract's predicates on `answer` in this process (the bounded child calls this)."""
    S = verify_runtime(bundle)
    from symblic.kernel import evidence as E

    entry = bundle["contracts"].get(contract_key(contract))
    if entry is None or entry["contract"] != contract:
        raise NativeContractError("unregistered_contract")
    if contract["kernel_id"] != bundle["kernel_id"]:
        raise NativeContractError("stale_contract_kernel")
    source = entry["source"]
    if hashlib.sha256(source.encode()).hexdigest() != contract["source_sha256"]:
        raise NativeContractError("source_digest_mismatch")
    prog = S.parse(source)
    ask = [
        n
        for n in prog["statements"]
        if n.k == "ask" and n.line == entry["ask_line"] and n.name == entry["name"]
    ]
    if len(ask) != 1:
        raise NativeContractError("source_ask_mismatch")
    ty = unpack(entry["type"])
    if E.syntax(ask[0].type) != E.syntax(ty):
        raise NativeContractError("source_type_mismatch")
    expected = {"integer": int, "boolean": bool, "string": str, "label": str}.get(
        contract["answer_type"]
    )
    if type(answer) is not expected or (
        contract["answer_type"] == "label" and answer not in contract.get("labels", [])
    ):
        return {
            "passed": False,
            "scope": "encoded_predicate",
            "kernel_id": bundle["kernel_id"],
            "receipts": [
                digest(
                    {
                        "contract": contract_key(contract),
                        "answer": answer,
                        "passed": False,
                        "reason": "type",
                    }
                )
            ],
        }
    try:
        value = S.coerce(answer, ty)
    except S.SymblicError:
        return {
            "passed": False,
            "scope": "encoded_predicate",
            "kernel_id": bundle["kernel_id"],
            "receipts": [
                digest(
                    {
                        "contract": contract_key(contract),
                        "answer": answer,
                        "passed": False,
                        "reason": "native_type",
                    }
                )
            ],
        }
    if set(contract["predicate_sha256s"]) != {
        p["predicate_sha256"] for p in entry["predicates"]
    }:
        raise NativeContractError("predicate_set_mismatch")
    receipts = []
    all_passed = True
    for pred in entry["predicates"]:
        cond = unpack(pred["ast"])
        validate_ast(cond)
        matched = [
            n
            for n in prog["statements"]
            if n.k in ("ensure", "assert")
            and n.line == pred["line"]
            and E.digest(E.syntax(n.cond)) == pred["predicate_sha256"]
        ]
        if len(matched) != 1 or E.syntax(matched[0].cond) != E.syntax(cond):
            raise NativeContractError("source_predicate_mismatch")
        env = S.Env()
        if entry["name"] not in S.free_names(cond):
            raise NativeContractError("predicate_does_not_read_answer")
        for name, row in pred["context"].items():
            if (
                name == entry["name"]
                or row["line"] >= entry["ask_line"]
                or not row["closed"]
                or row["class"] != "exact"
            ):
                raise NativeContractError("nonclosed_context")
            val = unpack(row["value"])
            if S.fingerprint(val) != row["hash"]:
                raise NativeContractError("context_digest_mismatch")
            env.vars[name] = S.Binding(name, val, unpack(row["type"]), line=row["line"])
        env.vars[entry["name"]] = S.Binding(
            entry["name"], value, ty, line=entry["ask_line"]
        )
        if any(n not in env.vars and n not in S.CONSTANTS for n in S.free_names(cond)):
            raise NativeContractError("open_context")
        try:
            passed = S._truth(
                S.Kernel(env=env, budget=S.Budget(100000)).eval(cond), cond
            )
        except S.SymblicError as exc:
            raise NativeContractError("native_predicate_evaluation_failed") from exc
        statement = S.Node("ensure", pred["line"], 1, cond=cond)
        receipt = E.check_receipt(
            statement,
            env,
            source=contract["source_sha256"],
            passed=passed,
            text=pred["text"],
        )
        receipts.append(receipt["id"])
        all_passed = all_passed and passed
    if not receipts:
        raise NativeContractError("empty_predicates")
    return {
        "passed": all_passed,
        "scope": "encoded_predicate",
        "kernel_id": bundle["kernel_id"],
        "receipts": receipts,
    }


_SOURCE_BYTES = globals().get("_SYMBLIC_CHECKER_SOURCE")
if _SOURCE_BYTES is None:
    _SOURCE_BYTES = _bounded_bytes(__file__, 1_000_000)
_SOURCE_SHA256 = hashlib.sha256(_SOURCE_BYTES).hexdigest()

# This constant bootstrap receives only the exact source captured by the worker's
# approved module loader. Limits precede loading the bundle or native runtime.
_BOOTSTRAP = r"""
import sys, resource, json, hashlib
for kind, ceiling in [(resource.RLIMIT_CPU, 5), (resource.RLIMIT_AS, 512*1024*1024),
                      (resource.RLIMIT_FSIZE, 256*1024), (resource.RLIMIT_CORE, 0)]:
    soft, hard = resource.getrlimit(kind)
    limited = min([ceiling] + [v for v in (soft, hard) if v != resource.RLIM_INFINITY])
    resource.setrlimit(kind, (limited, limited))
raw = sys.stdin.buffer.read(16000001)
if len(raw) > 16000000:
    raise SystemExit(2)
wire = json.loads(raw)
source = bytes.fromhex(wire['source_hex'])
if len(source) > 1000000 or hashlib.sha256(source).hexdigest() != wire['source_sha256']:
    raise SystemExit(2)
sys.argv = [wire['origin'], wire['action'], wire['bundle']]
namespace = {'__name__':'__main__', '__file__':wire['origin'],
             '_SYMBLIC_CHECKER_SOURCE':source, '_SYMBLIC_NATIVE_REQUEST':wire['request']}
exec(compile(source, wire['origin'], 'exec'), namespace)
"""


def _source_unchanged():
    if file_hash(__file__) != _SOURCE_SHA256:
        raise NativeContractError("checker_source_changed")


def _bounded_child(action, bundle_file, request=None):
    _source_unchanged()
    wire = {
        "source_hex": _SOURCE_BYTES.hex(),
        "source_sha256": _SOURCE_SHA256,
        "origin": str(Path(__file__).resolve()),
        "action": action,
        "bundle": str(bundle_file),
        "request": request,
    }
    payload = json.dumps(wire).encode()
    if len(payload) > MAX_BYTES:
        raise NativeContractError("checker_input_too_large")
    node = shutil.which("node")
    path = ([str(Path(node).resolve().parent)] if node else []) + [
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    env = {"PATH": os.pathsep.join(path), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-B", "-c", _BOOTSTRAP],
                input=payload,
                stdout=out,
                stderr=err,
                env=env,
                timeout=15,
            )
        except subprocess.TimeoutExpired as exc:
            raise NativeContractError("native_wall_timeout") from exc
        out.seek(0)
        raw = out.read(65537)
        if proc.returncode or len(raw) > 65536:
            raise NativeContractError("native_resource_or_validation_refusal")
    result = json.loads(raw)
    if result.get("checker_module_sha256") != _SOURCE_SHA256:
        raise NativeContractError("checker_child_source_mismatch")
    return result


class NativeScalarChecker:
    """The registered checker: identity() and check(contract, answer), each run in a bounded child process."""
    bundle_file = BUNDLE_FILE

    def __init__(self):
        _source_unchanged()
        self.bundle = read_bundle(self.bundle_file)
        self.identity_sha = digest(
            {
                "bundle_sha256": self.bundle["bundle_sha256"],
                "runtime_sha256": self.bundle["runtime_sha256"],
            }
        )
        result = _bounded_child("_identity", self.bundle_file)
        if result.get("identity_sha256") != self.identity_sha:
            raise NativeContractError("native_identity_unverified")

    def identity(self):
        _source_unchanged()
        return {
            "id": "symblic-native-scalar-v1",
            "version": 1,
            "kernel_id": self.bundle["kernel_id"],
            "contract_version": 1,
            "source_sha256": self.identity_sha,
        }

    def check(self, contract, answer):
        _source_unchanged()
        if (
            read_bundle(self.bundle_file)["bundle_sha256"]
            != self.bundle["bundle_sha256"]
        ):
            raise NativeContractError("contract_bundle_changed")
        result = _bounded_child(
            "_check", self.bundle_file, {"contract": contract, "answer": answer}
        )
        if result.get("identity_sha256") != self.identity_sha:
            raise NativeContractError("native_identity_changed")
        return result["receipt"]


CHECKERS = {"symblic-native-scalar-v1": NativeScalarChecker}

if __name__ == "__main__":
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ("_check", "_identity", "_limits"):
            raise NativeContractError("internal_cli_only")
        if "_SYMBLIC_NATIVE_REQUEST" not in globals():
            raise NativeContractError("bounded_bootstrap_required")
        if sys.argv[1] == "_limits":
            import resource

            print(
                json.dumps(
                    {
                        "checker_module_sha256": _SOURCE_SHA256,
                        "cpu": resource.getrlimit(resource.RLIMIT_CPU),
                        "address_space": resource.getrlimit(resource.RLIMIT_AS),
                    }
                )
            )
            sys.exit(0)
        b = read_bundle(sys.argv[2])
        identity = digest(
            {"bundle_sha256": b["bundle_sha256"], "runtime_sha256": b["runtime_sha256"]}
        )
        if sys.argv[1] == "_identity":
            verify_runtime(b)
            result = {"identity_sha256": identity}
        else:
            req = globals()["_SYMBLIC_NATIVE_REQUEST"]
            result = {
                "receipt": evaluate(b, req["contract"], req["answer"]),
                "identity_sha256": identity,
            }
        print(json.dumps({**result, "checker_module_sha256": _SOURCE_SHA256}))
    except Exception as exc:
        print(
            json.dumps({"status": "refused", "code": type(exc).__name__}),
            file=sys.stderr,
        )
        sys.exit(2)
