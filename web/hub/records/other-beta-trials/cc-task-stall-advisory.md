Fix a production observability defect in the Symblic task coordinator (single file: symblicos/tasks.py, plus focused tests in tests/test_symblicos_tasks.py).

DEFECT (observed live 2026-10-08, twice): In TaskManager.advance()'s observe path for an 'active' step, when the launched agent's first turn never actually started (observed: the engine's eligibility check returned 503 so the CLI sat at its banner with zero conversation steps; also a killed unbounded background command leaving the CLI idle), the completion check correctly reports "not done" forever, but the task record surfaces NOTHING: the step stays status 'active' and row['error'] stays empty indefinitely. A headless caller polling tasks/get cannot distinguish "long turn in progress" from "wedged at launch". A separate defect report earlier the same day had a fresh agent spend 20+ minutes waiting on its own killed background grep with no surfaced hint.

REQUIRED FIX: add a non-failing stall advisory to the step and task records. In the observe branch for an active step, when ALL of these hold:
- the step has a 'started' timestamp (already recorded at launch) and it is older than 15 minutes (define one module constant, e.g. STALL_HINT_SECONDS = 900),
- completion is not done/failed/unknown (the normal in-progress case),
- no evidence was captured this pass,
then set step['stalled'] = True and row['stalled_hint'] = a single fixed sentence telling the operator to inspect the linked agent terminal (do not invent status changes; do NOT set row['error'] since that field means failure; do not stop or touch the agent).
Requirements:
1. Purely additive: never change step status, never stop agents, never block later completion. Once completion evidence or a terminal state arrives, clear step['stalled'] and row['stalled_hint'] in the same write path that records that state.
2. The advisory must be idempotent (setting it twice must not rewrite history or bump revisions needlessly beyond the existing _write behavior).
3. Do not fire it for discrete triad steps (their completion path differs and long builds are normal); apply it to the plain agent lanes only, or document explicitly why it covers all lanes if you find a simpler correct rule.
4. Follow the file's existing error-message voice (plain English sentence, no stack details, no private data).
5. Add focused tests in tests/test_symblicos_tasks.py following that file's existing test style: (a) an active step older than the threshold with a not-done completion gets the advisory and stays active; (b) a fresh active step gets nothing; (c) when completion later reports done, the advisory is cleared. Use the existing fake-hub/test harness patterns in that file; tests must not start real agents, tmux or models.
6. Keep the diff minimal; no new files; no unrelated refactors.

DELIVERABLE: patched symblicos/tasks.py and tests/test_symblicos_tasks.py, with a one-paragraph summary of the exact condition and fields added.
