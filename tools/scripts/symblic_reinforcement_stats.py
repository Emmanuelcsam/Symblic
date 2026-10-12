#!/usr/bin/env python3
"""Offline descriptive benchmark analysis; no runner imports or implicit store paths.

    python3 tools/scripts/symblic_reinforcement_stats.py --manifest MANIFEST.json --rows OUTCOMES.jsonl

Reads one benchmark manifest (which cells exist) and one explicit JSONL snapshot of selected outcomes, and prints
descriptive statistics per cell. It computes; it does not run benchmarks or call models. See
docs/reference/reinforcements/benchmark-review.md for the manifest contract.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys


LIMITS = (
    'Descriptive only: pairs, nodes, repeats and model labels are not independent '
    'Bernoulli trials. No confidence interval or effective independent model count '
    'is inferred. Item counts identify clusters, not independent sampled items. '
    'Correctness trusts the supplied benchmark scorer; fingerprints measure only '
    'the supplied within-condition equivalence. Complete-case comparisons may be '
    'biased by nonrandom failures. No generalization beyond this planned workload.'
)


def _text(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{key} must be a nonempty string')
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _lane(plan):
    # Keep full applicator strings and explicit placement; never short_by().
    return (plan['condition'], plan['by'], plan.get('node', ''), plan.get('repeat', '0'))


def _valid(row):
    return row is not None and row.get('ok') is True and not row.get('error')


def _rate(k, n):
    return {'numerator': k, 'denominator': n, 'rate': k / n if n else None}


def analyze(planned: list, rows: list) -> dict:
    """Analyze a frozen plan and one explicitly selected outcome per cell.

    Identical duplicate rows are collapsed and counted; any differing duplicate
    fails, including retries. Caller must resolve retries by a declared policy.
    """
    if not isinstance(planned, list) or not planned:
        raise ValueError('planned cells must be a nonempty list')
    plans = {}
    semantic = set()
    for p in planned:
        if not isinstance(p, dict):
            raise ValueError('planned cell must be an object')
        for key in ('cell', 'suite', 'item', 'condition', 'by'):
            _text(p, key)
        parts = p['cell'].split('|')
        if len(parts) != 4 or any(not x.strip() for x in parts) or parts[:2] != [p['suite'], p['item']]:
            raise ValueError(f'invalid planned cell ID: {p["cell"]}')
        models = p.get('models')
        if not isinstance(models, list) or not models or any(
                not isinstance(m, str) or not m.strip() for m in models) or len(set(models)) != len(models):
            raise ValueError('models must be a nonempty list of distinct exact model labels')
        for key in ('node', 'repeat'):
            if key in p:
                _text(p, key)
        if p['cell'] in plans:
            raise ValueError(f'duplicate planned cell: {p["cell"]}')
        identity = (p['suite'], p['item'], *_lane(p))
        if identity in semantic:
            raise ValueError('duplicate planned logical cell; specify repeat or distinct placement')
        semantic.add(identity)
        plans[p['cell']] = p
    outcomes = {}
    duplicates = 0
    if not isinstance(rows, list):
        raise ValueError('rows must be a list')
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError('outcome must be an object')
        cell = _text(r, 'cell')
        if cell not in plans:
            raise ValueError(f'unplanned outcome: {cell}')
        if type(r.get('ok')) is not bool:
            raise ValueError(f'ok must be boolean: {cell}')
        if r.get('correct') is not None and type(r['correct']) is not bool:
            raise ValueError(f'correct must be boolean or null: {cell}')
        if r.get('hash') is not None and (not isinstance(r['hash'], str) or not r['hash']):
            raise ValueError(f'hash must be nonempty string or null: {cell}')
        if 'node' in r and not isinstance(r['node'], str):
            raise ValueError(f'node must be a string: {cell}')
        p = plans[cell]
        for key in ('suite', 'item', 'condition', 'by', 'repeat'):
            if key in r and r[key] != p.get(key, '0' if key == 'repeat' else None):
                raise ValueError(f'outcome {key} conflicts with plan: {cell}')
        if p.get('node') and r.get('node') and p['node'] != r['node']:
            raise ValueError(f'outcome node conflicts with plan: {cell}')
        if cell in outcomes:
            if _json(outcomes[cell]) != _json(r):
                raise ValueError(f'conflicting duplicate cell: {cell}')
            duplicates += 1
        outcomes[cell] = r

    def coverage(cells):
        rs = [outcomes.get(c) for c in cells]
        valid = [r for r in rs if _valid(r)]
        known = [r for r in valid if type(r.get('correct')) is bool]
        correct = sum(r['correct'] for r in known)
        return {
            'scheduled': len(cells), 'observed': sum(r is not None for r in rs),
            'missing': sum(r is None for r in rs),
            'failed_or_error': sum(r is not None and not _valid(r) for r in rs),
            'error_flagged': sum(bool(r and r.get('error')) for r in rs),
            'valid': len(valid), 'correctness_unknown_valid': len(valid) - len(known),
            'valid_coverage': _rate(len(valid), len(cells)),
            'verified_correct_over_scheduled': _rate(correct, len(cells)),
            'correct_over_valid_scored': _rate(correct, len(known)),
        }

    agreement_groups = defaultdict(list)
    suite_lanes = defaultdict(lambda: defaultdict(dict))
    for cell, p in plans.items():
        agreement_groups[(p['suite'], p['item'], p['condition'], p.get('repeat', '0'))].append(cell)
        suite_lanes[p['suite']][_lane(p)][p['item']] = cell
    agreements = []
    for key, cells in sorted(agreement_groups.items()):
        valid = [outcomes[c] for c in cells if _valid(outcomes.get(c))]
        hashed = [r for r in valid if r.get('hash')]
        counts = Counter(r['hash'] for r in hashed)
        n = len(hashed)
        pairs = n * (n - 1) // 2
        identical = sum(k * (k - 1) // 2 for k in counts.values())
        surviving_unanimous = n >= 2 and len(counts) == 1
        complete = n == len(cells) and len(cells) >= 2
        agreements.append({
            'suite': key[0], 'item': key[1], 'condition': key[2], 'repeat': key[3],
            **coverage(cells), 'fingerprinted_valid': n,
            'survivor_unanimous': surviving_unanimous,
            'complete_fingerprint_panel': complete,
            'scheduled_panel_unanimous': complete and surviving_unanimous,
            'shared_wrong_survivors': surviving_unanimous and all(r.get('correct') is False for r in hashed),
            'pairwise_identical_descriptive': _rate(identical, pairs),
        })

    comparisons = []
    for suite, lanes in sorted(suite_lanes.items()):
        if len(lanes) < 2:
            continue
        all_items = set.union(*(set(v) for v in lanes.values()))
        scheduled = set.intersection(*(set(v) for v in lanes.values()))
        complete = sorted(it for it in scheduled if all(
            _valid(outcomes.get(v[it])) and type(outcomes[v[it]].get('correct')) is bool
            for v in lanes.values()))
        columns = []
        for lane, item_cells in sorted(lanes.items()):
            scores = [int(outcomes[item_cells[it]]['correct']) for it in complete]
            columns.append({'condition': lane[0], 'by': lane[1], 'planned_node': lane[2],
                            'repeat': lane[3], **coverage(list(item_cells.values())),
                            'matched_correct': _rate(sum(scores), len(scores)), 'item_scores': scores})
        differences = []
        for i, left in enumerate(columns):
            for j in range(i + 1, len(columns)):
                right = columns[j]
                deltas = [b - a for a, b in zip(left['item_scores'], right['item_scores'])]
                differences.append({'left_lane': i, 'right_lane': j,
                                    'right_minus_left_mean': sum(deltas) / len(deltas) if deltas else None,
                                    'item_differences': deltas})
        comparisons.append({'suite': suite, 'union_items': len(all_items),
                            'scheduled_in_every_lane': len(scheduled),
                            'excluded_not_scheduled_everywhere': sorted(all_items - scheduled),
                            'excluded_missing_failed_or_unscored': sorted(scheduled - set(complete)),
                            'complete_matched_items': complete, 'lanes': columns,
                            'paired_descriptive_differences': differences})
    models = sorted({m for p in planned for m in p['models']})
    items = sorted({(p['suite'], p['item']) for p in planned})
    return {'schema_version': 1, 'uncertainty_limits': LIMITS,
            'identity_counts': {'distinct_model_labels': len(models), 'models': models,
                                'item_clusters': len(items), 'items': [list(it) for it in items],
                                'distinct_applicator_labels': len({p['by'] for p in planned}),
                                'observed_nodes': sorted({r['node'] for r in rows if r.get('node')}),
                                'node_unknown_observed': sum(not r.get('node') for r in outcomes.values()),
                                'independent_model_count': None, 'independent_item_count': None},
            'coverage': coverage(list(plans)), 'identical_duplicate_rows': duplicates,
            'missing_cells': sorted(set(plans) - set(outcomes)),
            'failed_cells': sorted(c for c, r in outcomes.items() if not _valid(r)),
            'cell_identities': [{'cell': c, 'by': p['by'], 'models': p['models'],
                                 'planned_node': p.get('node'),
                                 'observed_node': outcomes.get(c, {}).get('node')}
                                for c, p in sorted(plans.items())],
            'agreement_by_item': agreements, 'matched_comparisons': comparisons}


def read_jsonl(path):
    rows = []
    with Path(path).open(encoding='utf-8') as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError as exc:
                    raise ValueError(f'invalid JSONL at line {number}') from exc
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, help='JSON object: schema_version=1, cells=[...]')
    parser.add_argument('--rows', required=True, help='explicit offline JSONL snapshot, one selected outcome/cell')
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
        if not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1:
            raise ValueError('manifest schema_version must be 1')
        result = analyze(manifest.get('cells'), read_jsonl(args.rows))
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    except (OSError, ValueError, TypeError) as exc:
        print(f'analysis failed: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
