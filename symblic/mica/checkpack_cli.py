"""Command line for MICA check packs: freeze, public export, evaluator fixture, validate.

Run as `python3 -m symblic.mica.cli checkpack ...`. Depends on checkpack.py, checkpack_link.py, cli.py.

Details
    Freeze/extract finite MICA checks as JSON; never dispatch a candidate or model.

    The full pack and fixture contain evaluator-only data. Pass only the `public`
    output to construction. Freeze the pack and benchmark before candidate dispatch.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import json
import sys

from symblic.mica import cli as L
from symblic.mica import checkpack as K


def parser():
    p = L._Parser(prog='python3 -m symblic.mica.cli checkpack', description=__doc__, add_help=False)
    p.add_argument('--help', action='store_true')
    commands = p.add_subparsers(dest='command')
    commands.add_parser('capabilities', add_help=False)
    bind = commands.add_parser('binding', add_help=False)
    bind.add_argument('request'); bind.add_argument('--requirement-id', required=True)
    freeze = commands.add_parser('freeze', add_help=False)
    freeze.add_argument('request'); freeze.add_argument('--declaration', required=True)
    freeze.add_argument('--checker')
    for name in ('validate', 'public', 'fixture', 'linked-fixture'):
        sub = commands.add_parser(name, add_help=False)
        sub.add_argument('pack'); sub.add_argument('--checker')
        sub.add_argument('--freeze', required=True, help='Original SHA-256 retained when the pack was frozen.')
    return p


def _checker(path, factory):
    if path:
        return L._json_file(path, max_bytes=K.MAX_BYTES)
    if factory:
        return factory()
    from symblic.mica.bench import js_evaluator_identity
    return js_evaluator_identity()  # Existing asset/runtime identity, no candidate run.


def dispatch(args, *, checker_factory=None):
    if args.help or args.command in (None, 'capabilities'):
        return {'version': K.VERSION, 'commands': ['binding', 'freeze', 'validate', 'public', 'fixture', 'linked-fixture'],
                'kinds': ['case', 'round_trip', 'round_trip_domain'], 'scope': K.SCOPE,
                'authority': 'caller_supplied_only; model_proposed remains proposal',
                'declaration_schema': K.declaration_schema(), 'schema_scope': 'structural_guidance_root_binding_checks_remain_authoritative',
                'limits': {'cases': K.MAX_CASES, 'bytes': K.MAX_BYTES, 'hidden_cases': 200},
                'candidate_execution': False, 'provider_calls': 0, 'usage': parser().format_help()}
    if args.command == 'binding':
        return K.requirement_binding(L._json_file(args.request, max_bytes=K.MAX_BYTES), args.requirement_id)
    checker = _checker(args.checker, checker_factory)
    if args.command == 'freeze':
        return K.freeze(L._json_file(args.request, max_bytes=K.MAX_BYTES),
                        L._json_file(args.declaration, max_bytes=K.MAX_BYTES), checker)
    pack = K.validate(L._json_file(args.pack, max_bytes=K.MAX_BYTES), current_checker=checker,
                      expected_sha256=args.freeze)
    if args.command == 'public':
        return K.public_request(pack)
    if args.command == 'fixture':
        return K.fixture(pack)
    if args.command == 'linked-fixture':
        from symblic.mica import checkpack_link as H
        return H.linked_fixture(pack, expected_sha256=args.freeze)
    return {'valid': True, 'sha256': pack['sha256'], 'scope': pack['scope'],
            'counts': pack['counts'], 'semantic_completeness': 'unassessed',
            'freeze_scope': pack['freeze_scope']}


def main(argv=None, *, out=None, checker_factory=None):
    stream = out or sys.stdout
    try:
        result = dispatch(parser().parse_args(argv), checker_factory=checker_factory)
        code = 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        result = {'ok': False, 'error': {'code': getattr(error, 'code', type(error).__name__),
                                       'message': str(error)[:1000]}}
        code = 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False), file=stream)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
