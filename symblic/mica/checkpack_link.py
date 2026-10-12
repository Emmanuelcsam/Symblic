"""Links a frozen check pack to a MICA benchmark fixture, so the benchmark can verify where its hidden tests came from.

Depends on: checkpack.py, contracts.py, source_identity.py. Used by checkpack_cli.py and bench.py.

Details
    Pure optional check-pack/benchmark-fixture linkage, never a semantic oracle.

    The original pack stays private. Hashes retain caller-supplied finite interpretations
    and exact source witnesses, not authenticated authorship or independent evidence.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
import hashlib
from pathlib import Path

from symblic.mica import contracts as C
from symblic.mica import checkpack as K
from symblic.mica import source_identity as I

VERSION = 1
SCOPE = 'caller_bound_finite_interpretation_semantic_completeness_and_independence_unassessed'
FIELDS = {'id', 'family', 'split', 'request', 'hidden_tests'}
# This file, as links record it; links written before the package layout used the old flat file name.
SOURCE = 'symblic/mica/checkpack_link.py'
LEGACY_SOURCE = 'symblic_mica_checkpack_link.py'


class LinkError(ValueError):
    """Finite diagnostics never include private evaluator data."""


def _fail(code):
    raise LinkError(code)


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        _fail('checkpack_link_fields')


def _identity(declaration=None):
    """{version, source, source_sha256, generator} of the code that links a pack to a benchmark fixture."""
    path = Path(__file__)
    with path.open('rb') as stream:
        raw = stream.read(262145)
    sha = hashlib.sha256(raw).hexdigest()
    if (len(raw) > 262144 or not _symblic_import_identity.get('matched')
            or _symblic_import_identity.get('sha256') != sha
            or I.audit({SOURCE: sha})):
        _fail('checkpack_link_loaded_source')
    return {'version': VERSION, 'source': SOURCE, 'source_sha256': sha, 'generator': K._identity(declaration)}


def _fixture(pack):
    # This is the existing five-field fixture projection of already revalidated
    # pack data. Historical inspection must not require today's generator source.
    hidden = [[row['call'], row['expected']] for row in pack['checks']
              if row['origin'] == 'caller_supplied' and row['visibility'] == 'hidden']
    if not hidden:
        _fail('checkpack_link_no_hidden_cases')
    return {**copy.deepcopy(pack['declaration']['evaluation']),
            'request': copy.deepcopy(pack['public_request']), 'hidden_tests': hidden}


def linked_fixture(pack, *, expected_sha256):
    """Explicit private export; pin must be retained before any candidate dispatch."""
    pack = K.validate(pack, expected_sha256=expected_sha256)
    fixture = K.fixture(pack, expected_sha256=expected_sha256)
    body = {'version': VERSION, 'scope': SCOPE, 'pack_sha256': pack['sha256'],
            'fixture_sha256': C.digest(fixture), 'implementation': _identity(pack['declaration']), 'pack': pack}
    linked = {**fixture, 'checkpack': {**body, 'sha256': C.digest(body)}}
    C._bounded(linked)
    return linked


def validate_fixture(fixture, *, current_checker, require_current=True):
    """Rebuild exact linkage; current=False is historical integrity inspection."""
    C._bounded(fixture)
    _keys(fixture, FIELDS | {'checkpack'})
    link = fixture['checkpack']
    _keys(link, {'version', 'scope', 'pack_sha256', 'fixture_sha256', 'implementation', 'pack', 'sha256'})
    if type(link['version']) is not int or link['version'] != VERSION or link['scope'] != SCOPE:
        _fail('checkpack_link_version_scope')
    for name in ('sha256', 'pack_sha256', 'fixture_sha256'):
        if type(link[name]) is not str or not C._SHA.fullmatch(link[name]):
            _fail('checkpack_link_hash')
    if link['sha256'] != C.digest({k: v for k, v in link.items() if k != 'sha256'}):
        _fail('checkpack_link_pin')
    implementation = link['implementation']
    _keys(implementation, {'version', 'source', 'source_sha256', 'generator'})
    if (type(implementation['version']) is not int or implementation['version'] != VERSION
            or implementation['source'] not in (SOURCE, LEGACY_SOURCE)
            or type(implementation['source_sha256']) is not str
            or not C._SHA.fullmatch(implementation['source_sha256'])):
        _fail('checkpack_link_implementation')
    try:
        pack = K.validate(link['pack'], expected_sha256=link['pack_sha256'],
                          current_checker=current_checker, require_current=require_current)
    except (ValueError, TypeError, KeyError):
        _fail('checkpack_link_pack')
    if implementation['generator'] != pack['implementation']:
        _fail('checkpack_link_generator_pin')
    if require_current and implementation != _identity(pack['declaration']):
        _fail('checkpack_link_implementation_pin')
    ordinary = {key: fixture[key] for key in FIELDS}
    if C.digest(ordinary) != link['fixture_sha256'] or ordinary != _fixture(pack):
        _fail('checkpack_link_fixture_pin')
    return copy.deepcopy(link)


def public_receipt(ident, link):
    """Digest-only metadata for an already validated link; never private cases."""
    return {'fixture_id': ident, 'link_sha256': link['sha256'], 'pack_sha256': link['pack_sha256'],
            'fixture_sha256': link['fixture_sha256'], 'implementation': copy.deepcopy(link['implementation']),
            'checker_sha256': C.digest(link['pack']['checker_identity']),
            'original_request_sha256': link['pack']['original_request_sha256'],
            'public_request_sha256': link['pack']['public_request_sha256'], 'scope': SCOPE}
