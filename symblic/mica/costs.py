"""MICA host costs: wall-clock and thread-CPU spans of scheduling, assembly and verification work.

Depends on: nothing first-party. Used by search.py, native.py and project.py.

Details
    Observed scoped host costs, with explicit interrupted and overlapping work.

    No executor, source execution or model call. Callers own the durable event writer.
    Wall spans include waiting for sandboxed children; thread CPU excludes their CPU.
    These instrumented portions are not a total resource or energy measurement.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import contextlib
import re
import threading
import time
import uuid

VERSION = 1
CATEGORIES = ('verification', 'scheduler', 'assembly')
SCOPE = 'instrumented_host_spans_not_total_compute_or_energy'
_LOCAL = threading.local()
_ID = re.compile(r'[0-9a-f]{32}\Z')
_LIMIT = 100000
_COUNTERS = ("elapsed_ns", "host_thread_cpu_ns", "exclusive_ns", "exclusive_host_thread_cpu_ns")


class MeasurementError(RuntimeError):
    """Host instrumentation failed; this is never a model correctness grade."""


def _meter(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as error:
        raise MeasurementError("Host cost measurement failed: " + (str(error) or type(error).__name__)) from error


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value):
    _need(type(value) is int and 0 <= value <= 10**20, 'Invalid cost counter.')
    return value


@contextlib.contextmanager
def measure(emit, category, label, *, clock=time.monotonic_ns, cpu=time.thread_time_ns):
    """Record one durable span, without interpreting candidate correctness.

    The record start precedes the operation. An absent finish is unknown after a
    crash. Same-thread nested spans exclude child time from their exclusive cost;
    concurrent thread wall spans can overlap and must not be summed as latency.
    Each scope excludes its own writer/fsync overhead. Nested writer work may be
    included in the containing scope; there is no total-overhead measurement.
    """
    _need(category in CATEGORIES and type(label) is str and 0 < len(label) <= 160,
          'Invalid cost scope.')
    ident = uuid.uuid4().hex
    stack = getattr(_LOCAL, 'stack', None)
    if stack is None:
        stack = _LOCAL.stack = []
    parent = stack[-1] if stack else None
    _meter(emit, 'cost_started', cost_id=ident, category=category, label=label, version=VERSION)
    frame = {'wall': 0, 'cpu': 0}
    start, cpu_start = _meter(_integer, _meter(clock)), _meter(_integer, _meter(cpu))
    stack.append(frame)
    outcome = 'returned'
    try:
        yield
    except BaseException:
        outcome = 'raised'
        raise
    finally:
        popped = stack.pop()
        wall = _meter(_integer, _meter(clock)) - start
        host_cpu = _meter(_integer, _meter(cpu)) - cpu_start
        _meter(_need, popped is frame and wall >= frame['wall'] and host_cpu >= frame['cpu'],
              'Measurement clock or nested accounting moved backwards.')
        if parent is not None:
            parent['wall'] += wall
            parent['cpu'] += host_cpu
        _meter(emit, 'cost_finished', cost_id=ident, outcome=outcome,
             elapsed_ns=wall, host_thread_cpu_ns=host_cpu,
             exclusive_ns=wall-frame['wall'], exclusive_host_thread_cpu_ns=host_cpu-frame['cpu'])


def call(emit, category, label, fn, *args, **kwargs):
    with measure(emit, category, label):
        return fn(*args, **kwargs)


def summarize(events):
    """Validate complete pairs; never assign zero cost to unfinished scopes.

    Other journal kinds remain owned by the caller. Seal/chain verification is
    also the caller's responsibility. No proof or provider-quality grade results.
    """
    _need(type(events) is list and len(events) <= _LIMIT, 'Cost journal exceeds its bound.')
    starts, ends = {}, {}
    counters = ('elapsed_ns', 'host_thread_cpu_ns', 'exclusive_ns', 'exclusive_host_thread_cpu_ns')
    for event in events:
        _need(type(event) is dict, 'Invalid journal row.')
        kind = event.get('kind')
        if kind not in ('cost_started', 'cost_finished'):
            continue
        ident = event.get('cost_id')
        _need(type(ident) is str and _ID.fullmatch(ident), 'Invalid measurement identity.')
        if kind == 'cost_started':
            _need(ident not in starts and type(event.get('version')) is int and event['version'] == VERSION
                  and event.get('category') in CATEGORIES and type(event.get('label')) is str
                  and 0 < len(event['label']) <= 160, 'Conflicting or invalid cost start.')
            starts[ident] = event
        else:
            _need(ident in starts and ident not in ends and event.get('outcome') in ('returned', 'raised'),
                  'Missing, duplicated or reordered cost pair.')
            for field in counters:
                _integer(event.get(field))
            _need(event['exclusive_ns'] <= event['elapsed_ns']
                  and event['exclusive_host_thread_cpu_ns'] <= event['host_thread_cpu_ns'],
                  'Exclusive cost exceeds its containing span.')
            ends[ident] = event
    groups = []
    for category in CATEGORIES:
        selected = [ident for ident, row in starts.items() if row['category'] == category]
        completed = [ends[ident] for ident in selected if ident in ends]
        unknown = len(selected)-len(completed)
        groups.append({'category': category, 'started': len(selected), 'completed': len(completed),
                       'interrupted': unknown, 'raised': sum(r['outcome'] == 'raised' for r in completed),
                       'counters': {field: {'known_sum': sum(r[field] for r in completed),
                                            'completed_span_total': sum(r[field] for r in completed) if not unknown else None}
                                    for field in counters}})
    return {'version': VERSION, 'scope': SCOPE, 'groups': groups,
            'started': len(starts), 'completed': len(ends), 'interrupted': len(starts)-len(ends),
            'coverage': 'partial_instrumented_scopes_only',
            'wall_semantics': 'sum_of_spans_may_overlap_across_threads_not_end_to_end_latency',
            'cpu_semantics': 'host_calling_threads_only_excludes_child_processes_and_remote_workers',
            'unmeasured': ['some_event_writer_overhead', 'uninstrumented_host_work', 'child_process_cpu',
                           'remote_worker_cpu', 'gpu_compute', 'peak_memory', 'energy', 'currency']}


def _validate_summary(item):
    empty = summarize([])
    variable = {'groups', 'started', 'completed', 'interrupted'}
    _need(type(item) is dict and set(item) == set(empty), 'Invalid cost summary fields.')
    for key in set(empty) - variable:
        _need(type(item[key]) is type(empty[key]) and item[key] == empty[key],
              'Incompatible cost summary semantics.')
    _need(type(item['groups']) is list and len(item['groups']) == len(CATEGORIES),
          'Missing or duplicate cost category.')
    seen = set()
    for row in item['groups']:
        _need(type(row) is dict and set(row) == {'category', 'started', 'completed', 'interrupted', 'raised', 'counters'},
              'Invalid cost category fields.')
        category = row['category']
        _need(type(category) is str and category in CATEGORIES and category not in seen,
              'Missing or duplicate cost category.')
        seen.add(category)
        for field in ('started', 'completed', 'interrupted', 'raised'):
            _integer(row[field])
        _need(row['started'] == row['completed'] + row['interrupted'] and row['raised'] <= row['completed'],
              'Cost summary counts disagree.')
        _need(type(row['counters']) is dict and set(row['counters']) == set(_COUNTERS),
              'Invalid cost counter fields.')
        for field in _COUNTERS:
            counter = row['counters'][field]
            _need(type(counter) is dict and set(counter) == {'known_sum', 'completed_span_total'},
                  'Invalid cost counter summary.')
            known = _integer(counter['known_sum'])
            _need(row['completed'] > 0 or known == 0, 'Cost without a completed span.')
            if row['interrupted']:
                _need(counter['completed_span_total'] is None, 'Interrupted cost cannot have a complete total.')
            else:
                _need(_integer(counter['completed_span_total']) == known, 'Cost counter totals disagree.')
        for exclusive, inclusive in (('exclusive_ns', 'elapsed_ns'),
                                     ('exclusive_host_thread_cpu_ns', 'host_thread_cpu_ns')):
            _need(row['counters'][exclusive]['known_sum'] <= row['counters'][inclusive]['known_sum'],
                  'Exclusive cost exceeds its containing spans.')
    for field in ('started', 'completed', 'interrupted'):
        _need(_integer(item[field]) == sum(row[field] for row in item['groups']),
              'Top-level cost summary counts disagree.')


def combine(summaries):
    """Validate each input, then aggregate disjoint journals without inventing totals."""
    _need(type(summaries) is list and len(summaries) <= 10000, 'Too many cost summaries.')
    for item in summaries:
        _validate_summary(item)
    rows = []
    for category in CATEGORIES:
        selected = [r for summary in summaries for r in summary['groups'] if r['category'] == category]
        row = {'category': category}
        for field in ('started', 'completed', 'interrupted', 'raised'):
            row[field] = _integer(sum(r[field] for r in selected))
        row['counters'] = {}
        for field in _COUNTERS:
            known = _integer(sum(r['counters'][field]['known_sum'] for r in selected))
            row['counters'][field] = {'known_sum': known, 'completed_span_total': known if not row['interrupted'] else None}
        rows.append(row)
    empty = summarize([])
    result = {**empty, 'groups': rows, 'started': sum(r['started'] for r in rows),
              'completed': sum(r['completed'] for r in rows), 'interrupted': sum(r['interrupted'] for r in rows)}
    _validate_summary(result)
    return result
