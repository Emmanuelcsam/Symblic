/* Read-only rendering of versioned native evidence. Missing observations stay missing. */
(function () {
  'use strict';
  const object = value => value && typeof value === 'object' && !Array.isArray(value);
  const count = value => Number.isSafeInteger(value) && value >= 0 ? String(value) : 'not reported';
  const text = value => typeof value === 'string' ? value : 'not reported';
  const timestamp = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 8.64e12
    ? new Date(value * 1000).toISOString() : 'not reported';
  const block = value => object(value) && value.version === 1 ? value : null;
  function add(parent, tag, value, cls) {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = value;
    if (cls) node.className = cls;
    parent.appendChild(node);
    return node;
  }
  function section(parent, title, value) {
    const part = add(parent, 'div', undefined, 'card');
    add(part, 'p', title, 'lbl');
    if (!block(value)) {
      add(part, 'p', value == null ? 'Not reported by this run.' : 'Unsupported report version.', 'hint');
      return null;
    }
    return part;
  }
  function rows(parent, values, render, truncated) {
    if (!Array.isArray(values)) {
      add(parent, 'p', 'Detail rows were not reported.', 'hint');
      return;
    }
    const list = add(parent, 'ul');
    values.slice(0, 100).forEach(row => {
      if (object(row)) render(add(list, 'li'), row);
    });
    if (truncated === true || values.length > 100) {
      add(parent, 'p', 'This view contains a bounded selection; the complete run record has the retained evidence.', 'hint');
    }
  }
  const REASONS = {
    no_finite_domain: 'No finite answer domain', over_limit: 'Domain exceeds the analysis limit',
    no_anchored_checks: 'No anchored checks', unsupported_check: 'Check is outside this analysis',
    budget: 'Analysis budget reached', not_attempted: 'Analysis was not attempted',
    author_disabled: 'Speculative analysis was disabled by the author',
  };
  const STATUS = {
    determined: 'One answer satisfies the encoded constraints',
    underdetermined: 'Several answers satisfy the encoded constraints',
    contradictory: 'No answer satisfies the encoded constraints',
    unassessed: 'Uniqueness was not established',
  };
  const CONSTRUCTOR_DISPOSITIONS = {
    accepted: 'Accepted after native checks', diagnosed: 'Candidates checked; diagnostic only',
    no_candidate: 'No candidate returned (solver report)', unsupported: 'Outside the supported fragment',
    unavailable: 'Constructor unavailable', timeout: 'Constructor time limit reached',
    unknown: 'Constructor outcome unknown', stopped: 'Construction stopped',
    cleanup_failed: 'Worker cleanup unconfirmed', not_attempted: 'Construction was not attempted',
  };
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  function constructorReceipt(parent, value) {
    const receipt = block(value);
    if (!receipt || receipt.kind !== 'smt_linear') {
      add(parent, 'p', 'Constructor receipt: unsupported or malformed.', 'hint');
      return;
    }
    const disposition = typeof receipt.disposition === 'string' && own(CONSTRUCTOR_DISPOSITIONS, receipt.disposition)
      ? CONSTRUCTOR_DISPOSITIONS[receipt.disposition] : 'Disposition not reported';
    add(parent, 'p', 'Constructor: ' + disposition, 'hint');
    if (own(receipt, 'reason')) {
      const reason = typeof receipt.reason === 'string' && /^[a-z][a-z0-9_]{0,63}$/.test(receipt.reason)
        ? receipt.reason : 'not reported';
      add(parent, 'p', 'Constructor reason: ' + reason, 'hint');
    }
    const replay = receipt.replayed === true ? 'yes' : receipt.replayed === false ? 'no' : 'not reported';
    add(parent, 'p', 'Replayed: ' + replay, 'hint');
    if (own(receipt, 'attempt')) add(parent, 'p', 'Constructor attempt: '
      + (Number.isSafeInteger(receipt.attempt) && receipt.attempt > 0 ? receipt.attempt : 'not reported'), 'hint');
    if (own(receipt, 'witnesses')) add(parent, 'p', 'Checked witnesses: '
      + (receipt.witnesses === 1 || receipt.witnesses === 2 ? receipt.witnesses : 'not reported'), 'hint');
    if (receipt.exhaustive === false) {
      add(parent, 'p', 'Search was not exhaustive; uniqueness was not established.', 'hint');
    } else if (own(receipt, 'exhaustive')) {
      add(parent, 'p', 'Search exhaustiveness was not reported in a supported form.', 'hint');
    }
    if ((receipt.disposition === 'accepted' || receipt.disposition === 'diagnosed')
      && receipt.determination === 'underdetermined' && receipt.witnesses === 2) {
      add(parent, 'p', 'The constructor reports distinct checked candidates satisfying the encoded constraints.', 'hint');
    }
  }
  function render(target, report, options = {}) {
    if (!target) return;
    target.replaceChildren();
    const details = add(target, 'details', undefined, 'unit');
    const heading = add(details, 'summary', 'Determinism and model use');
    const summary = block(report?.determinism_summary);
    if (summary) {
      heading.textContent += ' · ' + count(summary.determined) + ' determined · '
        + count(summary.underdetermined) + ' with alternatives';
    }
    add(details, 'p', 'These receipts describe the written constraints, tests and observed calls.', 'hint');
    if (summary && own(summary, 'answered_by_constructor')) add(details, 'p',
      'Answered by constructor: ' + count(summary.answered_by_constructor), 'hint');
    const determinacy = block(report?.determinacy);
    const d = section(details, 'Answer determination', report?.determinacy);
    if (d) {
      const totals = object(determinacy.summary) ? determinacy.summary : {};
      add(d, 'p', ['determined', 'underdetermined', 'contradictory', 'unassessed']
        .map(key => key + ': ' + count(totals[key])).join(' · '), 'hint');
      rows(d, determinacy.asks, (li, row) => {
        const item = row.index === undefined ? '' : ' · item '
          + (Number.isSafeInteger(row.index) && row.index > 0 ? row.index : 'not reported');
        add(li, 'p', 'Line ' + count(row.line) + item + ' · ' + text(row.name) + ': '
          + (STATUS[row.status] || 'Unrecognized assessment'));
        if (row.status === 'unassessed') add(li, 'p', REASONS[row.reason] || text(row.reason), 'hint');
        else add(li, 'p', 'Passing values: ' + count(row.passing_count) + ' · domain size: '
          + count(row.domain?.size) + ' · method: ' + text(row.method), 'hint');
        const answered = row.answered_by === 'kernel' ? 'Kernel' : row.answered_by === 'model' ? 'Model'
          : row.answered_by === 'constructor' ? 'Constructor' : row.answered_by === 'mixed' ? 'Mixed sources'
          : row.answered_by === null ? 'No accepted answer' : 'Not reported';
        add(li, 'p', 'Answered by: ' + answered + ' · solve mode: ' + text(row.solve_mode), 'hint');
        if (own(row, 'constructor')) constructorReceipt(li, row.constructor);
        if (Array.isArray(row.passing) && row.passing.length) {
          const examples = add(li, 'details');
          add(examples, 'summary', 'Values admitted by the checks');
          row.passing.slice(0, 20).forEach(value => add(examples, 'pre', text(value), 'sy-cap'));
        }
        if (row.passing_truncated === true) add(li, 'p', 'Passing-value list is truncated.', 'hint');
        if (row.checks_truncated === true) add(li, 'p', 'Check list is truncated in this report.', 'hint');
      }, determinacy.asks_truncated);
    }
    const behavior = block(report?.code_behavior);
    const c = section(details, 'Code behavior', report?.code_behavior);
    if (c) rows(c, behavior.asks, (li, row) => {
      add(li, 'p', 'Line ' + count(row.line) + ' · ' + text(row.name));
      if (row.scope !== 'declared_tests_only') {
        add(li, 'p', 'Unrecognized behavior scope; inspect the original record.', 'hint');
        return;
      }
      const label = {agreed_on_declared: 'Passing candidates agree on the declared tests',
        differs_on_declared: 'Passing candidates differ on the declared tests',
        unmeasured: 'The declared tests did not provide comparable behavior observations',
        single: 'One passing candidate; agreement was not measured', none: 'No passing candidate'}[row.status];
      add(li, 'p', label || 'Behavior status was not reported');
      add(li, 'p', count(row.passing) + ' passing of ' + count(row.candidates)
        + ' candidates · ' + count(row.tests?.count) + ' declared tests. This does not establish equivalence on other inputs.', 'hint');
      if (row.covered_by === 'root_D7') add(li, 'p', 'Additional probe comparisons have a separate differential-spec receipt.', 'hint');
    }, behavior?.asks_truncated);
    const identity = block(report?.model_identity);
    const i = section(details, 'Model manifest observations', report?.model_identity);
    if (i) {
      const basis = identity.basis === 'fresh_recheck' ? 'Explicit recheck of retained call records'
        : identity.basis === 'recorded_at_report' ? 'Recorded when the runner wrote this report'
        : 'Observation time basis was not reported';
      add(i, 'p', basis + ' · computed at: ' + timestamp(identity.computed_at), 'hint');
      if (identity.basis === 'fresh_recheck' || identity.audit_complete !== undefined) {
        add(i, 'p', identity.audit_complete === true ? 'Stored-record audit: complete.'
          : identity.audit_complete === false ? 'Stored-record audit: incomplete; missing or unchecked identity evidence remains unknown.'
            : 'Stored-record audit coverage was not reported.', 'hint');
        add(i, 'p', 'Call ledger: ' + ({present: 'readable', absent: 'absent', unreadable: 'unreadable'}[identity.calls_file]
          || 'not reported') + ' · malformed records: ' + count(identity.invalid_rows), 'hint');
        add(i, 'p', 'Records scanned: ' + count(identity.rows_scanned)
          + ' · missing identity records: ' + count(identity.missing_identity_rows), 'hint');
      }
      add(i, 'p', identity.strict === true ? 'Answers with changed, missing or uncheckable manifest observations are refused. Dispatched calls remain charged.'
        : identity.strict === false ? 'Changed observed manifests are recorded.' : 'Drift policy was not reported.', 'hint');
      if (identity.checker?.available === false) add(i, 'p', 'The identity checker is unavailable; stored identity labels cannot establish a current pin.', 'hint');
      const apps = object(identity.applicators) ? Object.entries(identity.applicators) : [];
      apps.slice(0, 100).forEach(([app, row]) => {
        if (!object(row)) return;
        add(i, 'p', app);
        const digest = add(i, 'p', 'Manifest pin in this observation: ' + text(row.pinned), 'hint');
        digest.style.overflowWrap = 'anywhere';
        add(i, 'p', ['observed', 'drift', 'unavailable', 'invalid', 'unverifiable']
          .map(key => key + ': ' + count(row.statuses?.[key])).join(' · '), 'hint');
      });
      if (!object(identity.applicators)) add(i, 'p', 'Applicator observations were not reported.', 'hint');
      rows(i, identity.drift, (li, row) => add(li, 'p', 'Line ' + count(row.line) + ' · '
        + text(row.applicator) + ' · change ' + text(row.action)), identity.drift_truncated
          || identity.applicators_truncated || apps.length > 100);
      add(i, 'p', 'Manifest observations do not attest which weights were loaded throughout execution.', 'hint');
      if (identity.rows_truncated === true) add(i, 'p', 'The recheck reached its record limit; later rows were not assessed.', 'hint');
    }
    if (typeof options.recheck === 'function') {
      const controls = i || add(details, 'div', undefined, 'card');
      const button = add(controls, 'button', 'Recheck retained model observations', 'btn sm');
      button.type = 'button';
      const message = add(controls, 'p', 'Reads bounded stored receipts; does not contact a model.', 'hint');
      message.setAttribute('role', 'status');
      button.onclick = async () => {
        button.disabled = true;
        message.textContent = 'Rechecking retained call records…';
        try {
          const checked = await options.recheck();
          if (!block(checked) || checked.basis !== 'fresh_recheck') throw new Error('The server did not return a supported fresh recheck.');
          render(target, {...report, model_identity: checked}, options);
          target.querySelector('details').open = true;
        } catch (error) {
          message.textContent = error?.message || 'The recheck could not finish.';
          button.disabled = false;
        }
      };
    }
    const escalation = block(report?.escalation);
    const e = section(details, 'Escalation outcomes', report?.escalation);
    if (e) {
      add(e, 'p', 'Accepted locally with no cloud calls: ' + count(escalation.local_only_success)
        + ' · accepted from cloud: ' + count(escalation.cloud_accepted) + ' · failed: ' + count(escalation.failed), 'hint');
      rows(e, escalation.by_rung, (li, row) => add(li, 'p', 'Rung '
        + (Number.isSafeInteger(row.rung) && row.rung >= 0 ? row.rung + 1 : 'not reported') + ' · '
        + text(row.applicator) + ' · ' + text(row.locality) + ' · accepted: ' + count(row.accepted)), escalation.by_rung_truncated);
      add(e, 'p', 'Charged cloud calls: ' + count(escalation.cloud_dispatches_charged)
        + ' · cloud refusals before dispatch: ' + count(escalation.cloud_refused_pre_dispatch), 'hint');
      add(e, 'p', 'Accepted means the declared checks passed. Cloud selection does not establish that cloud execution was necessary.', 'hint');
    }
  }
  window.SymblicDeterminism = Object.freeze({render});
}());
