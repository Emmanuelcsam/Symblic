"""Agent graphs, part 3: composition. Reuse a group of nodes several times by expanding it into one flat graph.

What it is for
    A composition document declares inline `definitions` (a group of nodes with public input and output ports)
    and `instances` that use a definition, each pinned by the SHA-256 of the definition's exact body. The
    expander renames each instance's nodes into its own namespace, wires ports to ordinary node edges, and hands
    the complete flat graph to the ordinary freezer (symblic.graph.planner.freeze_graph). Nothing new runs: the
    result is an ordinary frozen graph plus a manifest that maps every expanded node back to its definition,
    instance and source hash. Expansion is one level deep and has no budgets or overrides of its own.

    expand_composition(document, policy) -> {'frozen', 'manifest'};  compose(body) -> a draft and the manifest;
    example() loads examples/reusable-graph.json;  catalog() describes the document format.

    Command line (no model calls, no run folder):
        python3 -m symblic.graph.compose catalog | example | compose FILE [--flat]

Depends on: symblic.kernel (language, evidence) and symblic.graph.planner. Used by: the original host's graph
routes (integration/host/symblic_graph_api.py). Status: prototype with unit tests (tests/graph).
Document contract: docs/reference/GRAPH-COMPOSITION.md.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from symblic.kernel import language as S
from symblic.kernel import evidence as E
from symblic.graph import planner as G

VERSION = 1
MAX_DEFINITIONS = 32
MAX_INSTANCES = 32
MAX_PORTS = 32
_SOURCE_SHA256, _SOURCE_LOADED = G._import_identity(__file__, sys._getframe(0).f_code)


def definition_digest(definition):
    """Pin the exact bounded inline body; this digest grants no authority."""
    return G.digest(definition)


def _namespace(instance, node):
    return 'SG_' + G.digest([VERSION, instance, node])[:48]


def _named_rows(rows, limit, label, *, nonempty=False):
    if type(rows) is not list or not (int(nonempty) <= len(rows) <= limit):
        raise G.GraphError(label + ' limit')
    named = {}
    for row in rows:
        if type(row) is not dict:
            raise G.GraphError(label + ' must contain objects')
        name = G.identifier(row.get('id'))
        if name in named:
            raise G.GraphError('duplicate ' + label + ' identifier')
        named[name] = row
    return named


def _ports(rows):
    if type(rows) is not dict or len(rows) > MAX_PORTS:
        raise G.GraphError('port limit')
    for name in rows:
        G.identifier(name)
    return rows


def _source_digest(node):
    source = node.get('source')
    if type(source) is not str or len(source.encode('utf-8')) > 32768:
        raise G.GraphError('explicit bounded node source required')
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def _given_types(node):
    """Describe explicit native given types without running imports/defaults.

    Local preceding define declarations use the existing type resolver. Imported
    type aliases are deliberately not resolved by this authoring-only interface.
    """
    _source_digest(node)
    source = node['source']
    try:
        statements = S.parse(source)['statements']
        types, declared = {}, {}
        for statement in statements:
            if statement.k == 'define':
                if statement.name in types:
                    raise G.GraphError('duplicate local type declaration')
                types[statement.name] = statement.type
            elif statement.k == 'given':
                if statement.name in declared:
                    raise G.GraphError('duplicate top-level given')
                declared[statement.name] = (None if statement.type is None else
                    E.syntax(S.resolve_type(statement.type, types, statement.line)))
        return declared
    except (S.SymblicError, RecursionError) as error:
        raise G.GraphError('invalid or unresolved native port type/source') from error


def _definition(body):
    G.keys(body, ('nodes', 'inputs', 'outputs'))
    nodes = _named_rows(body['nodes'], G.MAX_NODES, 'definition nodes', nonempty=True)
    inputs, outputs = _ports(body['inputs']), _ports(body['outputs'])
    if not outputs:
        raise G.GraphError('definition needs an explicit output port')
    targets, contracts, given_cache = {}, {}, {}
    for port, declaration in inputs.items():
        G.keys(declaration, ('targets',))
        rows = declaration['targets']
        if type(rows) is not list or not 1 <= len(rows) <= G.MAX_NODES:
            raise G.GraphError('input port target limit')
        contract = None
        for target in rows:
            G.keys(target, ('node', 'input'))
            local, name = G.identifier(target['node']), G.identifier(target['input'])
            if local not in nodes:
                raise G.GraphError('input port names a missing local node')
            node = nodes[local]
            if type(node.get('inputs')) is not dict:
                raise G.GraphError('node inputs must be an object')
            key = (local, name)
            if key in targets or name in node['inputs']:
                raise G.GraphError('duplicate or overwriting public input target')
            if local not in given_cache:
                given_cache[local] = _given_types(node)
            declared = given_cache[local]
            if name not in declared or declared[name] is None:
                raise G.GraphError('public input needs an explicit top-level given type')
            current = {'native_type': declared[name], 'join': node.get('join')}
            if contract is not None and current != contract:
                raise G.GraphError('fanout port native type/join contracts differ')
            contract = current
            targets[key] = port
        contracts[port] = contract
    for port, declaration in outputs.items():
        G.keys(declaration, ('node',))
        local = G.identifier(declaration['node'])
        if (local not in nodes or not nodes[local].get('output_binding')
                or type(nodes[local].get('output_schema')) is not dict):
            raise G.GraphError('output port requires a local explicit output binding')
    return nodes, targets, contracts


def _edge(ref, resolve):
    if type(ref) is not dict:
        raise G.GraphError('input reference must be an object')
    if 'literal' in ref:
        G.keys(ref, ('literal',))
        return G.snapshot(ref)
    if 'instance' in ref:
        G.keys(ref, ('instance', 'port'), ('delay', 'seed'))
        ident = resolve('instance', G.identifier(ref['instance']), G.identifier(ref['port']))
    else:
        G.keys(ref, ('node',), ('delay', 'seed'))
        ident = resolve('node', G.identifier(ref['node']), None)
    return {'node': ident, **{key: ref[key] for key in ('delay', 'seed') if key in ref}}


def expand_composition(document, policy):
    """Expand one level and return an ordinary frozen graph plus an audit map.

    There are no definition clocks, group budgets or instance overrides. Every
    original leaf permission/source/cap is preserved exactly. Literal/seed values
    and prior-node envelopes keep the ordinary graph semantics and provenance.
    """
    if not _SOURCE_LOADED or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != _SOURCE_SHA256:
        raise G.GraphError('expander source changed or differs from loaded code; use a fresh process')
    doc = G.snapshot(document)
    G.keys(doc, ('version', 'id', 'definitions', 'instances', 'nodes', 'iterations', 'max_calls'))
    if type(doc['version']) is not int or doc['version'] != VERSION:
        raise G.GraphError('unsupported composition version')
    definitions = doc['definitions']
    if type(definitions) is not dict or not 1 <= len(definitions) <= MAX_DEFINITIONS:
        raise G.GraphError('definition limit')
    for name in definitions:
        G.identifier(name)
    instances = _named_rows(doc['instances'], MAX_INSTANCES, 'instances', nonempty=True)
    top = _named_rows(doc['nodes'], G.MAX_NODES, 'top-level nodes')
    # Count before parsing or expanding; compact repeated references cannot evade
    # the existing global node ceiling or cause unbounded expansion work.
    declared_count = sum(len(body.get('nodes', [])) if type(body) is dict and
                         type(body.get('nodes')) is list else G.MAX_NODES + 1
                         for body in definitions.values())
    if declared_count + len(top) > G.MAX_NODES:
        raise G.GraphError('declared node limit')
    used, expanded_count = set(), len(top)
    for instance in instances.values():
        G.keys(instance, ('id', 'definition', 'sha256', 'inputs'))
        name = G.identifier(instance['definition'])
        if name not in definitions or instance['sha256'] != definition_digest(definitions[name]):
            raise G.GraphError('missing definition or inline definition digest mismatch')
        used.add(name)
        expanded_count += len(definitions[name]['nodes'])
    if used != set(definitions):
        raise G.GraphError('unused definitions are not admitted')
    if expanded_count > G.MAX_NODES:
        raise G.GraphError('expanded node limit')
    parsed = {name: _definition(body) for name, body in definitions.items()}
    identifiers = set(top)
    mapping, outputs = {}, {}
    for name, instance in instances.items():
        body = definitions[instance['definition']]
        local_nodes, _, _ = parsed[instance['definition']]
        if type(instance['inputs']) is not dict or set(instance['inputs']) != set(body['inputs']):
            raise G.GraphError('instance inputs must exactly bind public ports')
        for local in local_nodes:
            generated = G.identifier(_namespace(name, local))
            if generated in identifiers:
                raise G.GraphError('expanded namespace collision')
            identifiers.add(generated)
            mapping[name, local] = generated
        outputs[name] = {port: mapping[name, row['node']] for port, row in body['outputs'].items()}

    def external(kind, name, port):
        if kind == 'node' and name in top:
            return name
        if kind == 'instance' and name in outputs and port in outputs[name]:
            return outputs[name][port]
        raise G.GraphError('missing or private external producer/port')

    leaves, source_map, port_map = [], {}, {}
    for name, node in top.items():
        copy = G.snapshot(node)
        if type(copy.get('inputs')) is not dict:
            raise G.GraphError('top-level inputs must be an object')
        copy['inputs'] = {key: _edge(ref, external) for key, ref in copy['inputs'].items()}
        leaves.append(copy)
        source_map[name] = {'scope': 'top', 'node': name,
                            'source_sha256': _source_digest(copy)}
    for name, instance in instances.items():
        body = definitions[instance['definition']]
        local_nodes, targets, contracts = parsed[instance['definition']]
        bindings = {port: _edge(ref, external) for port, ref in instance['inputs'].items()}

        def internal(kind, local, port, *, local_scope=local_nodes, instance_name=name):
            if kind != 'node' or local not in local_scope:
                raise G.GraphError('definition references a missing/private external node')
            return mapping[instance_name, local]

        for local, node in local_nodes.items():
            copy = G.snapshot(node)
            copy['id'] = mapping[name, local]
            if type(copy.get('inputs')) is not dict:
                raise G.GraphError('definition inputs must be an object')
            copy['inputs'] = {key: _edge(ref, internal) for key, ref in copy['inputs'].items()}
            for (target, key), port in targets.items():
                if target == local:
                    copy['inputs'][key] = G.snapshot(bindings[port])
            leaves.append(copy)
            source_map[copy['id']] = {'scope': 'instance', 'instance': name,
                'definition': instance['definition'], 'definition_sha256': instance['sha256'],
                'node': local, 'source_sha256': _source_digest(copy)}
        port_map[name] = {'inputs': {port: {'contract': contracts[port], 'binding': bindings[port],
            'targets': [{'node': mapping[name, target['node']], 'input': target['input']}
                        for target in body['inputs'][port]['targets']]} for port in bindings},
            'outputs': {port: {'node': outputs[name][port],
                'output_binding': local_nodes[row['node']]['output_binding'],
                'output_schema': local_nodes[row['node']]['output_schema']}
                for port, row in body['outputs'].items()}}
    flat = {'id': doc['id'], 'nodes': leaves, 'iterations': doc['iterations'], 'max_calls': doc['max_calls']}
    frozen = G.freeze_graph(flat, policy)
    manifest = {'version': VERSION, 'composition_sha256': G.digest(doc),
        'definition_sha256': {name: definition_digest(body) for name, body in definitions.items()},
        'expander_sha256': _SOURCE_SHA256, 'graph_hash': frozen['graph_hash'],
        'policy_hash': frozen['policy_hash'], 'nodes': source_map, 'ports': port_map,
        'scope': 'authoring_expansion_not_execution_authority'}
    manifest['sha256'] = G.digest(manifest)
    return G.snapshot({'version': VERSION, 'frozen': frozen, 'manifest': manifest})


def compose(body):
    """Return an ordinary draft and authoring provenance, without dispatch."""
    G.keys(body, ('composition', 'policy'))
    expanded = expand_composition(body['composition'], body['policy'])
    frozen = expanded['frozen']
    return G.snapshot({'ok': True, 'version': VERSION,
        'draft': {'graph': frozen['graph'], 'policy': frozen['policy']},
        'manifest': expanded['manifest'],
        'scope': 'authoring_only; check the flat draft in its intended execution host'})


def _document(path):
    import json

    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise G.GraphError('duplicate JSON key: ' + key)
            result[key] = value
        return result

    def constant(_):
        raise G.GraphError('non-finite JSON number')

    with open(path, 'rb') as stream:
        raw = stream.read(G.MAX_BYTES + 1)
    if len(raw) > G.MAX_BYTES:
        raise G.GraphError('composition document byte limit')
    return G.snapshot(json.loads(raw, object_pairs_hook=pairs, parse_constant=constant))


def example():
    """The checked-in deterministic example is data, never a provider request."""
    return _document(Path(__file__).resolve().parents[2] / 'examples/reusable-graph.json')


def catalog():
    return {'version': VERSION, 'scope': 'authoring_only',
        'commands': ['catalog', 'example', 'compose FILE [--flat]'],
        'document_fields': ['composition', 'policy'],
        'composition_fields': ['version', 'id', 'definitions', 'instances', 'nodes', 'iterations', 'max_calls'],
        'definition_fields': ['nodes', 'inputs', 'outputs'],
        'instance_fields': ['id', 'definition', 'sha256', 'inputs'],
        'limits': {'definitions': MAX_DEFINITIONS, 'instances': MAX_INSTANCES,
                   'ports_per_direction': MAX_PORTS, 'declared_nodes': G.MAX_NODES,
                   'expanded_nodes': G.MAX_NODES, 'json_bytes': G.MAX_BYTES},
        'definition_digest': 'SHA-256 of canonical UTF-8 JSON: sorted keys, no whitespace, ensure_ascii=false; use definition_digest(body)',
        'input_ports': 'Explicit native given types; identical type and join for fanout; no target overwrite.',
        'output_ports': 'Alias a whole leaf output binding; no projection or group-success assertion.',
        'references': ['literal envelope', 'top-level node', 'instance and output port'],
        'execution': 'CLI expansion makes zero model calls. Check the returned flat draft in its host, then explicitly run it (symblic.graph.run.GraphRun). The original host web jobs did not inject an effect host.',
        'documentation': 'docs/reference/GRAPH-COMPOSITION.md'}


def main(argv=None):
    """Pure agent entry point. No run directory, provider or launcher is opened."""
    import argparse
    import json
    parser = argparse.ArgumentParser(prog='python3 -m symblic.graph.compose',
                                     description='Expand a reusable graph composition into one flat graph (no model calls).')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('catalog', 'example', 'compose'):
        child = commands.add_parser(command)
        child.add_argument('--agent-json', action='store_true', help='emit one JSON result (also the default)')
        if command == 'compose':
            child.add_argument('path', help='JSON containing composition and policy')
            child.add_argument('--flat', action='store_true', help='emit only the ordinary graph/policy draft')
    args = parser.parse_args(argv)
    try:
        if args.command == 'catalog':
            result = catalog()
        elif args.command == 'example':
            result = example()
        else:
            result = compose(_document(args.path))
            if args.flat:
                result = result['draft']
    except (G.GraphError, S.SymblicError, OSError, ValueError, RecursionError) as error:
        print(json.dumps({'ok': False, 'error': {'kind': 'graph_composition', 'message': str(error)}}))
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
