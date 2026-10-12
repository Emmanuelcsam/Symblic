"""Registry of the bounded research experiments, and reproducible receipts for their results.

What it is for
    Each module listed in ``MODULES`` is a small, pure calculation over caller-supplied finite data (quantum
    toy models, exact numerics, graph adaptation, sampling, ...). ``catalog()`` lists them; ``run(id, data)``
    runs one and returns a *receipt*: the exact input, the output, the SHA-256 of every source file the
    result depended on, and a hash over all of it. ``verify(receipt)`` recomputes the experiment and compares.

What a receipt proves (and does not)
    Same adapter source + same exact input -> same output. It is not an independent empirical validation:
    the adapters compute supplied finite models and claim nothing about physical systems or model behaviour.
    These experiments are research explorations with no result claimed; see README.md in this package.

Safety boundary
    Inputs and outputs are bounded JSON (no floats; exact numbers travel as strings such as "1/3").
    Nothing here calls a model, reads user files, writes anywhere or starts a worker. An adapter that mutates
    its input, raises an unexpected error, or whose source changed on disk since import is refused.

Depends on: ``symblic.kernel.identity`` (import markers), ``symblic.mica.source_identity`` (package-aware
loaded-source pins), and, for adapters that run native Symblic programs, ``symblic.kernel.execution_pins``.

Run it:
    python3 -m symblic.experiments.registry list
    python3 -m symblic.experiments.registry example circuit_rewrite > input.json
    python3 -m symblic.experiments.registry run circuit_rewrite input.json > receipt.json
    python3 -m symblic.experiments.registry verify receipt.json
"""

# Bind the executing module to its exact first-party source before dependencies.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)
import argparse
import hashlib
import importlib
import json
import re
from pathlib import Path
import sys

from symblic.mica import source_identity as _sources

VERSION = 1
# Every adapter module the registry offers, by full module name.
MODULES = ('symblic.experiments.quantum', 'symblic.experiments.context',
           'symblic.experiments.geometry', 'symblic.experiments.graph', 'symblic.experiments.sampling',
           'symblic.experiments.structure', 'symblic.experiments.resources',
           'symblic.experiments.numerics', 'symblic.experiments.transport', 'symblic.experiments.protocols')
# Always part of a receipt's implementation pins: the registry itself and the identity helpers it trusts.
CORE = ('symblic.kernel.identity', 'symblic.mica.source_identity', 'symblic.experiments.registry')
MAX_BYTES = 1_048_576
MAX_NODES = 65_536
MAX_DEPTH = 24
MAX_TEXT = 65_536
_MODULE_NAME = re.compile(r'symblic(\.[a-z_][a-z0-9_]*)+\Z')


class ExperimentError(ValueError):
    """A refused experiment: a short stable code such as unknown_experiment or loaded_adapter_differs."""


def bounded(value):
    """Canonical UTF-8 JSON bytes of a bounded, float-free JSON value, or ExperimentError (depth, size, type)."""
    active = set()
    count = size = 0

    def walk(item, depth):
        nonlocal count, size
        count += 1
        size += 2
        if depth > MAX_DEPTH or count > MAX_NODES or size > MAX_BYTES:
            raise ExperimentError('structure_limit')
        kind = type(item)
        if kind in (dict, list):
            if id(item) in active or len(item) > MAX_NODES:
                raise ExperimentError('structure_limit')
            active.add(id(item))
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise ExperimentError('json_type')
                    walk(key, depth+1)
                    walk(child, depth+1)
            else:
                for child in item:
                    walk(child, depth+1)
            active.remove(id(item))
        elif kind is str:
            if len(item) > MAX_TEXT:
                raise ExperimentError('text_limit')
            try:
                size += len(item.encode('utf-8'))
            except UnicodeError:
                raise ExperimentError('unicode') from None
        elif kind is int:
            if abs(item) > 2**53-1:
                raise ExperimentError('integer_bound')
            size += 18
        elif kind is bool or item is None:
            size += 5
        else:
            raise ExperimentError('json_type')
    walk(value, 0)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise ExperimentError('byte_limit')
    return raw


def loads(raw):
    """Strict JSON parse: no duplicate keys, no floats or NaN (use exact strings such as \"1/3\"), bounded."""
    if type(raw) not in (str, bytes) or len(raw) > MAX_BYTES:
        raise ExperimentError('byte_limit')

    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ExperimentError('duplicate_key')
            result[key] = value
        return result

    def approximate(_):
        raise ExperimentError('use_exact_number_string')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_float=approximate, parse_constant=approximate)
        bounded(value)
        return value
    except ExperimentError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise ExperimentError('invalid_json') from None


def digest(value):
    """SHA-256 hex digest of the canonical JSON of a bounded value."""
    return hashlib.sha256(bounded(value)).hexdigest()


def _identity(module):
    """{repository-relative source path: sha256} for the adapter, its declared DEPENDENCIES and CORE.

    Each module must be loaded from this installation with a genuine import marker that matches its unchanged
    source file (see symblic.mica.source_identity). Modules that keep their own (sha256, loaded) pair instead of
    the kernel marker (the graph planner) are checked through that pair. An adapter that runs native Symblic
    programs (USES_NATIVE_KERNEL) also requires the kernel's own loaded-runtime check to pass.
    """
    sources = {}
    marked = {}
    for name in (*CORE, module.__name__, *getattr(module, 'DEPENDENCIES', ())):
        if type(name) is not str or not _MODULE_NAME.fullmatch(name):
            raise ExperimentError('adapter_dependency')
        loaded = importlib.import_module(name)
        try:
            path = Path(loaded.__file__)
            if path.suffix != '.py' or path.stat().st_size > 2_000_000:
                raise ExperimentError('adapter_source')
            if hasattr(loaded, '_SOURCE_SHA256') and not hasattr(loaded, '_symblic_import_identity'):
                digest = _sources.file_sha256(path)
                if not getattr(loaded, '_SOURCE_LOADED', False) or loaded._SOURCE_SHA256 != digest:
                    raise ExperimentError('loaded_adapter_differs')
                sources[_sources.relative_path(path)] = digest
            else:
                relative, digest = _sources.pin(loaded)
                sources[relative] = marked[relative] = digest
        except _sources.IdentityError:
            raise ExperimentError('loaded_adapter_differs') from None
        except OSError:
            raise ExperimentError('adapter_source_unavailable') from None
    if _sources.audit(marked):
        raise ExperimentError('loaded_adapter_differs')
    if getattr(module, 'USES_NATIVE_KERNEL', False):
        try:
            from symblic.kernel import execution_pins as execution
            execution._check_loaded_runtime()
        except Exception:
            raise ExperimentError('native_runtime_identity') from None
    return dict(sorted(sources.items()))


def _registry():
    """({experiment id: (module, catalog entry)}, [modules that could not be imported])."""
    result = {}
    unavailable = []
    for name in MODULES:
        try:
            module = importlib.import_module(name)
        except ImportError:
            unavailable.append(name)
            continue
        for entry in module.catalog():
            key = entry['id']
            if key in result:
                raise ExperimentError('duplicate_experiment')
            result[key] = (module, entry)
    return result, unavailable


def catalog():
    """Every available experiment's catalog entry (id, title, summary, example input, sources, limits)."""
    registry, unavailable = _registry()
    return {'schema': 'symblic.experiments.catalog.v1', 'experiments': [entry for _, entry in registry.values()],
            'unavailable_modules': unavailable, 'effects': 'none', 'models': 'none'}


def run(experiment_id, data):
    """Run one experiment on a copy of `data` and return its receipt (see the module docstring)."""
    if type(experiment_id) is not str or len(experiment_id) > 100:
        raise ExperimentError('experiment_id')
    input_raw = bounded(data)
    data = loads(input_raw)  # Adapters never receive the caller's mutable object.
    registry, _ = _registry()
    if experiment_id not in registry:
        raise ExperimentError('unknown_experiment')
    module, _ = registry[experiment_id]
    source_pins = _identity(module)
    try:
        output = module.run(experiment_id, data)
        bounded(output)
        if bounded(data) != input_raw:
            raise ExperimentError('adapter_mutated_input')
    except ExperimentError:
        raise
    except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError) as error:
        # Only simple stable error identifiers can leave a library boundary.
        message = str(error)
        if not message or len(message) > 100 or not all(c.isalnum() or c in '_-.' for c in message):
            message = 'invalid_experiment_input'
        raise ExperimentError(message) from None
    if _identity(module) != source_pins:
        raise ExperimentError('adapter_changed')
    record = {'schema': 'symblic.experiment.receipt.v1', 'experiment': experiment_id,
              'adapter': module.__name__, 'adapter_version': module.VERSION,
              'implementation_sha256': source_pins,
              'input_sha256': digest(data), 'input': data, 'output': output,
              'effects': 'none', 'model_calls': 0}
    record['sha256'] = digest(record)
    return record


def verify(receipt):
    """Recompute the experiment, not merely its self-issued hash."""
    bounded(receipt)
    if type(receipt) is not dict or set(receipt) != {'schema', 'experiment', 'adapter', 'adapter_version',
                                                   'implementation_sha256', 'input_sha256', 'input', 'output', 'effects', 'model_calls', 'sha256'}:
        raise ExperimentError('receipt_schema')
    expected = run(receipt['experiment'], receipt['input'])
    supplied_hash_valid = receipt['sha256'] == digest({k: v for k, v in receipt.items() if k != 'sha256'})
    return {'ok': supplied_hash_valid and bounded(expected) == bounded(receipt),
            'supplied_hash_valid': supplied_hash_valid, 'expected_sha256': expected['sha256'],
            'scope': 'same installed adapter and exact supplied input; not independent empirical validation'}


def main(argv=None):
    """Command line: list | example ID | run ID FILE|- | verify FILE. Prints JSON; exit 2 on refusal."""
    parser = argparse.ArgumentParser(prog='python3 -m symblic.experiments.registry',
                                     description='List, run and verify the bounded research experiments.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    example = sub.add_parser('example')
    example.add_argument('experiment')
    execute = sub.add_parser('run')
    execute.add_argument('experiment')
    execute.add_argument('file', help='JSON input path or - for stdin')
    check = sub.add_parser('verify')
    check.add_argument('file')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            output = catalog()
        elif args.command == 'example':
            registry, _ = _registry()
            if args.experiment not in registry:
                raise ExperimentError('unknown_experiment')
            output = registry[args.experiment][1]['example']
        else:
            if args.file == '-':
                raw = sys.stdin.buffer.read(MAX_BYTES+1)
            else:
                with open(args.file, 'rb') as stream:
                    raw = stream.read(MAX_BYTES+1)
            data = loads(raw)
            output = verify(data) if args.command == 'verify' else run(args.experiment, data)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if output.get('ok', True) else 1
    except (ExperimentError, OSError):
        print(json.dumps({'ok': False, 'error': 'Experiment refused; check schema, bounds and exact input.'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
