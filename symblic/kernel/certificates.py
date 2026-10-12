"""Test certificates: a sealed record of which applicators passed a program's tests, and routing built from it.

`symblic.lang.abstraction certify` runs a module's `test` blocks once per cohort of applicators. make_certificate()
seals such a report with the program's SHA-256, the kernel identity and the hashes of the Python modules that
produced it; validate_certificate() refuses a certificate whose content, source, kernel or modules changed;
route_table() turns a valid certificate into an ordered list of qualified applicators and a bounded escalation
policy for a later run (no call is made here).

Limits, stated plainly: a certificate attests to recorded test outcomes, never to future correctness or to
independent observations. Hashes detect edits; they are not signatures or authentication. The caller must
obtain reports from a trusted certification run and provide the current source, semantic kernel identity and
complete module hash map before routing. Requested model labels are pinned, not a provider's mutable upstream
weights: a matching source and kernel do not establish that a hosted model is still the version observed
during certification, and routing keeps that limitation explicit.

Depends on: the standard library only. Used by: symblic.lang.abstraction (certify writes certificates) and
symblic.kernel.run (the run option `certificate` sends each ask to the certified applicators, in order).
"""

from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json
import re

from symblic.kernel import language as S

CERTIFICATE_VERSION = 1
ROUTE_VERSION = 1
SCOPE = 'observed_tests_only'


class CertificateError(ValueError):
    pass


def _copy(value):
    try:
        return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise CertificateError('certificate data must be finite JSON values') from exc


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def source_hash(source: str) -> str:
    if not isinstance(source, str):
        raise CertificateError('source must be text')
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def certificate_hash(certificate: dict) -> str:
    return _hash({k: v for k, v in certificate.items() if k != 'sha256'})


def _kernel(kernel):
    if not isinstance(kernel, dict) or not isinstance(kernel.get('id'), str) or not kernel['id']:
        raise CertificateError('a recorded kernel identity is required')
    # Python patch/minor versions are informative; kernel_id's semantic identity
    # deliberately includes the Unicode version instead of the Python version.
    return {k: v for k, v in kernel.items() if k != 'python'}


def _modules(hashes):
    if not isinstance(hashes, dict):
        raise CertificateError('a complete module hash map is required ({} for no modules)')
    if any(not isinstance(k, str) or not k or not isinstance(v, str)
           or not re.fullmatch(r'[0-9a-f]{64}', v) for k, v in hashes.items()):
        raise CertificateError('module hashes must map names to SHA-256 hex digests')
    return dict(sorted(hashes.items()))


def _label(value):
    if not isinstance(value, str) or not value.strip():
        raise CertificateError('cohort and candidate labels must be nonempty text')
    parts = [part.strip() for part in value.strip().split(',')]
    if not all(parts):
        raise CertificateError('cohort labels cannot contain empty members')
    return ', '.join(parts)


def _labels(values):
    if not isinstance(values, list):
        raise CertificateError('candidates must be an ordered list')
    labels = [_label(v) for v in values]
    if len(set(labels)) != len(labels):
        raise CertificateError('duplicate cohort or candidate labels are not additional evidence')
    return labels


def _assessment(report):
    """Recompute qualification from individual rows; never trust `all`/`certified`."""
    if not isinstance(report, dict):
        raise CertificateError('certification report must be an object')
    cohorts, tests = report.get('cohorts'), report.get('tests')
    if not isinstance(cohorts, list) or not isinstance(tests, list):
        raise CertificateError('certification report needs cohort and test lists')
    if any(not isinstance(row, dict) for row in cohorts + tests):
        raise CertificateError('cohorts and tests must be objects')
    labels = _labels([c.get('by') for c in cohorts])
    titles = [_label(t.get('title')) for t in tests]
    if len(set(titles)) != len(titles):
        raise CertificateError('duplicate test titles cannot qualify a certificate')
    reasons = {label: [] for label in labels}
    if not tests:
        for label in labels:
            reasons[label].append('no_tests')
    statuses = {label: [] for label in labels}
    model_calls = {label: 0 for label in labels}
    for test in tests:
        rows = test.get('cohorts')
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise CertificateError('each test needs cohort result rows')
        row_labels = _labels([r.get('by') for r in rows])
        if set(row_labels) - set(labels):
            raise CertificateError('test row names an unreported cohort')
        by = dict(zip(row_labels, rows))
        for label in labels:
            row = by.get(label)
            passed = bool(row and row.get('status') == 'passed' and not row.get('error'))
            statuses[label].append(passed)
            calls = row.get('calls', 0) if row else 0
            if type(calls) is not int or calls < 0:
                raise CertificateError('test model call counts must be nonnegative integers')
            model_calls[label] += calls
            if not passed:
                reasons[label].append('test_not_passed:' + test['title'])
        observed = sum(r.get('status') == 'passed' and not r.get('error') for r in rows)
        if (type(test.get('passed')) is not int or type(test.get('of')) is not int
                or test['passed'] != observed or test['of'] != len(rows)):
            raise CertificateError('test summary disagrees with its recorded rows')
    for cohort, label in zip(cohorts, labels):
        if not model_calls[label]:
            reasons[label].append('model_not_exercised')
        if cohort.get('error') or cohort.get('status', 'done') != 'done':
            reasons[label].append('cohort_failed')
        passed = sum(statuses[label])
        if (type(cohort.get('passed')) is not int or type(cohort.get('failed')) is not int
                or cohort['passed'] != passed or cohort['failed'] != len(tests) - passed):
            reasons[label].append('incomplete_or_inconsistent_cohort_counts')
    return labels, titles, reasons


def make_certificate(source: str, report: dict, *, kernel=None, module_hashes=None,
                     candidates=None) -> dict:
    """Seal a trusted report; missing provenance remains explicitly unqualified.

    `report` must record source_sha256, kernel and module_hashes at execution time.
    Arguments cannot retrospectively substitute those missing observations.
    """
    report = _copy(report)
    labels, titles, reasons = _assessment(report)
    expected_source = source_hash(source)
    current_kernel = _copy(kernel if kernel is not None else S.kernel_id())
    _kernel(current_kernel)
    current_modules = _modules(module_hashes) if module_hashes is not None else None
    missing = [k for k in ('source_sha256', 'kernel', 'module_hashes') if k not in report]
    if 'source_sha256' in report and report['source_sha256'] != expected_source:
        raise CertificateError('report source hash differs from the supplied source')
    if 'kernel' in report and _kernel(report['kernel']) != _kernel(current_kernel):
        raise CertificateError('report kernel identity differs from the current kernel')
    if 'module_hashes' in report:
        recorded_modules = _modules(report['module_hashes'])
        if current_modules is not None and recorded_modules != current_modules:
            raise CertificateError('report module hashes differ from current modules')
    else:
        recorded_modules = None
    requested = _labels(candidates if candidates is not None else labels)
    rows = []
    for label in requested:
        why = list(reasons.get(label, ['not_observed']))
        if missing:
            why.append('missing_report_provenance:' + ','.join(missing))
        if current_modules is None:
            why.append('current_module_hashes_not_supplied')
        rows.append({'by': label, 'qualified': not why, 'reasons': why})
    certificate = {'symblic_certificate': CERTIFICATE_VERSION, 'scope': SCOPE,
                   'source_sha256': expected_source, 'kernel': current_kernel,
                   'module_hashes': recorded_modules, 'report': report,
                   'test_titles': titles, 'observed_cohorts': labels,
                   'candidates': rows, 'provenance_complete': not missing and current_modules is not None,
                   'assurance': 'empirical_test_results', 'independence': 'not_established',
                   'model_identity_scope': 'requested_cohort_labels', 'model_freshness': 'not_established'}
    certificate['sha256'] = certificate_hash(certificate)
    return certificate


def validate_certificate(certificate: dict, source: str, *, kernel=None, module_hashes=None) -> dict:
    """Return a detached validated certificate, or refuse edits, missing pins and drift."""
    cert = _copy(certificate)
    if not isinstance(cert, dict) or cert.get('symblic_certificate') != CERTIFICATE_VERSION:
        raise CertificateError('unsupported certificate schema version')
    if cert.get('sha256') != certificate_hash(cert):
        raise CertificateError('certificate content hash mismatch')
    if cert.get('source_sha256') != source_hash(source):
        raise CertificateError('certificate source is stale')
    current = kernel if kernel is not None else S.kernel_id()
    if _kernel(cert.get('kernel')) != _kernel(current):
        raise CertificateError('certificate kernel identity is stale')
    if not cert.get('provenance_complete'):
        raise CertificateError('certificate execution provenance is incomplete')
    if _modules(cert.get('module_hashes')) != _modules(module_hashes):
        raise CertificateError('certificate module hashes are stale')
    try:
        candidate_labels = [r['by'] for r in cert['candidates']]
    except (KeyError, TypeError) as exc:
        raise CertificateError('invalid certificate candidate table') from exc
    rebuilt = make_certificate(source, cert.get('report'), kernel=current, module_hashes=module_hashes,
                               candidates=candidate_labels)
    # Recompute all assurance fields: recomputing a hash over fabricated summary
    # flags cannot upgrade the detailed recorded test outcomes.
    for key in ('scope', 'test_titles', 'observed_cohorts', 'candidates', 'provenance_complete',
                'assurance', 'independence', 'model_identity_scope', 'model_freshness'):
        if cert.get(key) != rebuilt[key]:
            raise CertificateError('certificate qualification does not match its recorded evidence')
    return cert


def route_table(certificate: dict, source: str, *, kernel=None, module_hashes=None,
                candidates=None) -> dict:
    """Return ordered qualified candidates and an explicit bounded escalation policy.

    No dispatch occurs. Candidate order is author-supplied, never inferred cost.
    Runtime checks must still reject invalid answers and perform each escalation.
    """
    base = {'symblic_routes': ROUTE_VERSION, 'scope': SCOPE, 'order_basis': 'declared',
            'candidates': [], 'rejected': [], 'independence': 'not_established',
            'model_identity_scope': 'requested_cohort_labels', 'model_freshness': 'not_established'}
    try:
        cert = validate_certificate(certificate, source, kernel=kernel, module_hashes=module_hashes)
        rows = {row['by']: row for row in cert['candidates']}
        requested = _labels(candidates if candidates is not None else list(rows))
    except CertificateError as exc:
        return {**base, 'status': 'escalate', 'escalation': {'action': 'refuse', 'reason': str(exc)}}
    for label in requested:
        row = rows.get(label)
        if row and row['qualified']:
            base['candidates'].append(label)
        else:
            base['rejected'].append({'by': label, 'reasons': row['reasons'] if row else ['not_observed']})
    return {**base, 'status': 'qualified' if base['candidates'] else 'escalate',
            'certificate_sha256': cert['sha256'],
            'escalation': {'action': 'next_candidate_then_refuse' if base['candidates'] else 'refuse',
                           'on': ['invalid_answer', 'failed_constraint', 'ambiguous', 'unavailable'],
                           'reason': 'only recorded test scope is qualified; runtime checks remain required'}}
