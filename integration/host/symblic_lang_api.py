"""HOST-ONLY: the host's routes for the abstraction layer (library, papers, tests, locks, certify jobs).

What it did: symblic_engine.handle (integration/host/symblic_engine.py) handed these routes here; they sat
behind the host's owner check with the rest of its automation routes. Runs and comparisons go through
symblic_engine (its runner units, folders and compare view); this module only adds the library, papers,
in-language tests and locks on top. The same features work without the host from the command line:
`tools/symblic test|certify|lib|doc|paper|lock` (symblic/lang/abstraction.py, symblic/authoring/paper.py,
symblic/kernel/lockfile.py). Saving needs the host's store module (`host_apps`).

    GET  symblic/library                     the standard library: modules, signatures, docs, tests
    GET  symblic/module?name=                one module's documentation and source
    POST symblic/tests        {source}       run the program's `test` blocks (kernel only: asks fail)
    POST symblic/paper/check  {source}       a .symd paper's diagnostics and plan, on the paper's lines
    POST symblic/paper/compile {source}      the program a paper compiles to, with its source map
    POST symblic/paper/run    {source, inputs, by, title, options}              -> {id}
    POST symblic/paper/reproduce {source, inputs, applicators: [...], title}   -> {id, runs}
    GET  symblic/paper/view?id=COMPARE       the comparison aligned on the paper (underspecified lines)
    GET  symblic/paper/map?run=ID            the paper map of a run started from a paper
    POST symblic/lock         {id}           freeze a finished run (run.lock.json in its folder)
    GET  symblic/lock?id=                    that lock
    POST symblic/lock/replay  {id}           replay the lock with no model; the fingerprint must match
    POST symblic/lang/certify {module | source, cohorts: [...]}           -> {id}   (a background job)
    POST symblic/lang/crystallise {source, routine, domain: [...], by, min_agreement, workers} -> {id}
    GET  symblic/lang/jobs | symblic/lang/job?id=   POST symblic/lang/stop {id} | symblic/lang/save {id, name}
    GET  symblic/lang/evidence               the measured experiments (bench folders lang-*): papers reproduced,
                                             modules certified, routines crystallised
Jobs run `python -m symblic.lang.abstraction job --dir FOLDER` in their own systemd user unit symblic-lang-<id>
(like runs): they ask real agents, so they never run in the server's request thread.
"""

from __future__ import annotations

import os
import re
import time

from symblic.kernel import language as S

PAPER_FILE = 'paper.json'
JOB_RX = re.compile(r'^[0-9a-f]{12}$')
MAX_DOMAIN = 200
MAX_COHORTS = 6
LOCK_FILE = 'run.lock.json'
MODULE_RX = re.compile(r'^[a-z][a-z0-9_]{0,40}$')


def _paper_record(compiled: dict) -> dict:
    return {k: compiled[k] for k in ('title', 'map', 'sections', 'terms', 'sha256', 'context')}


def _save(path: str, data) -> None:
    import host_apps
    host_apps.save_json(path, data)
    os.chmod(path, 0o600)


def _load(path: str, default=None):
    import host_apps
    return host_apps.load_json(path, default)


def paper_run(body: dict) -> dict:
    from integration.host import symblic_engine as E
    from symblic.authoring import paper as P
    text = E._clean_source(body.get('source'))
    compiled = P.compile_paper(text)
    checked = P.check_paper(text)
    if not checked['ok']:
        e = checked['errors'][0]
        raise E.SymblicApiError(f'paper line {e.get("line", 0)}: {e["message"]}')
    res = E.start_run({**body, 'source': compiled['source'], 'title': body.get('title') or compiled['title']})
    _save(os.path.join(E.run_dir(res['id']), PAPER_FILE), _paper_record(compiled))
    return res


def paper_reproduce(body: dict) -> dict:
    from integration.host import symblic_engine as E
    from symblic.authoring import paper as P
    text = E._clean_source(body.get('source'))
    compiled = P.compile_paper(text)
    checked = P.check_paper(text)
    if not checked['ok']:
        e = checked['errors'][0]
        raise E.SymblicApiError(f'paper line {e.get("line", 0)}: {e["message"]}')
    res = E.start_compare({**body, 'source': compiled['source'],
                           'title': body.get('title') or f'{compiled["title"]} (reproduction)'})
    _save(os.path.join(E.compares_dir(), f'{res["id"]}.{PAPER_FILE}'), _paper_record(compiled))
    return res


def paper_view(cid: str) -> dict:
    from integration.host import symblic_engine as E
    from symblic.authoring import paper as P
    view = E.compare_view(cid)                     # validates the id
    record = _load(os.path.join(E.compares_dir(), f'{cid}.{PAPER_FILE}'))
    if not record:
        raise E.SymblicApiError('This comparison was not started from a paper.')
    aligned = P.align(record, view['columns'])
    aligned['compare'] = {'id': view['id'], 'title': view.get('title'), 'created': view.get('created'),
                          'summary': view.get('summary')}
    aligned['text'] = P.report_text(aligned)
    return aligned


def paper_map(run_id: str) -> dict:
    from integration.host import symblic_engine as E
    record = _load(os.path.join(E.run_dir(run_id), PAPER_FILE))
    if not record:
        raise E.SymblicApiError('This run was not started from a paper.')
    return record


def lock_run(run_id: str) -> dict:
    from integration.host import symblic_engine as E
    from symblic.kernel import lockfile as K
    folder = E.run_dir(run_id)
    if E.launcher['active'](run_id):
        raise E.SymblicApiError('The run is still going.')
    lock = K.make_lock(folder)
    K.save_lock(lock, os.path.join(folder, LOCK_FILE))
    return {'ok': True, 'fingerprint': lock['fingerprint'], 'statements': len(lock['statements']),
            'calls': len(lock['calls']), 'sha256': lock['sha256']}


def lock_get(run_id: str) -> dict:
    from integration.host import symblic_engine as E
    from symblic.kernel import lockfile as K
    path = os.path.join(E.run_dir(run_id), LOCK_FILE)
    if not os.path.isfile(path):
        raise E.SymblicApiError('This run has no lock yet.')
    return K.load_lock(path)


def lock_replay(run_id: str) -> dict:
    from symblic.kernel import lockfile as K
    res = K.replay(lock_get(run_id))
    return {k: res[k] for k in ('ok', 'fingerprint', 'expected', 'status', 'error', 'refused', 'calls', 'cached')}


def module_view(name: str) -> dict:
    from integration.host import symblic_engine as E
    from symblic.lang import abstraction as L
    if not MODULE_RX.match(str(name or '')):
        raise E.SymblicApiError('No such module.')
    source = L.library_source(name)
    if source is None:
        raise E.SymblicApiError('No such module.')
    return {**L.describe_module(name, source), 'source': source}


def tests_run(body: dict) -> dict:
    """The program's tests with the kernel only: an ask inside a test fails (certification needs agents,
    which run through a run or `tools/symblic certify`, never from the page's request thread)."""
    from integration.host import symblic_engine as E
    from symblic.kernel import process_limits as P
    return P.call_bounded('tests', {'source': E._clean_source(body.get('source'))})


# ---------------------------------------------------------------------------
# Background jobs: certify a module with several cohorts, crystallise a routine
# ---------------------------------------------------------------------------

def jobs_dir() -> str:
    from integration.host import symblic_engine as E
    path = os.path.join(E.root(), 'lang-jobs')
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _unit(job_id: str) -> str:
    return f'symblic-lang-{job_id}'


def _launch(job_id: str, folder: str) -> dict:
    from integration.host import symblic_engine as E
    return E._launch_unit(_unit(job_id), ['-m', 'symblic.lang.abstraction', 'job', '--dir', folder])


def _active(job_id: str) -> bool:
    from integration.host import symblic_engine as E
    return E._systemd_active(job_id, unit=_unit(job_id))


def _stop(job_id: str) -> bool:
    from integration.host import symblic_engine as E
    return E._systemd_stop(job_id, unit=_unit(job_id))


jobs = {'launch': _launch, 'active': _active, 'stop': _stop}       # replaced in tests


def _job_dir(job_id) -> str:
    from integration.host import symblic_engine as E
    if not JOB_RX.match(str(job_id or '')):
        raise E.SymblicApiError('No such job.')
    path = os.path.join(jobs_dir(), job_id)
    if not os.path.isdir(path):
        raise E.SymblicApiError('No such job.')
    return path


def _cohorts(raw) -> list:
    from integration.host import symblic_engine as E
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_COHORTS:
        raise E.SymblicApiError(f'Pick 1 to {MAX_COHORTS} agents.')
    out = []
    for a in raw:
        try:
            out.append(S.parse_applicator(a)['spec'])
        except S.SymblicError as e:
            raise E.SymblicApiError(e.message) from None
    if len(set(out)) != len(out):
        raise E.SymblicApiError('Each agent once.')
    return out


def _start_job(job: dict) -> dict:
    import secrets
    from integration.host import symblic_engine as E
    job_id = secrets.token_hex(6)
    folder = os.path.join(jobs_dir(), job_id)
    os.makedirs(folder, mode=0o700)
    job.update(id=job_id, created=time.time())
    _save(os.path.join(folder, 'job.json'), job)
    started = jobs['launch'](job_id, folder)
    if not started.get('ok'):
        _save(os.path.join(folder, 'result.json'), {'status': 'failed', 'error': started.get('error') or
                                                    'did not start', 'finished': time.time()})
        raise E.SymblicApiError(started.get('error') or 'The job did not start.')
    return {'id': job_id}


def start_certify(body: dict) -> dict:
    from integration.host import symblic_engine as E
    from symblic.lang import abstraction as L
    module = str(body.get('module') or '')
    if module:
        if not MODULE_RX.match(module) or L.library_source(module) is None:
            raise E.SymblicApiError('No such module.')
        source = None
    else:
        source = E._clean_source(body.get('source'))
    text = source if source is not None else L.library_source(module)
    if not any(s.k == 'test' for s in S.parse(text)['statements']):
        raise E.SymblicApiError('There are no tests to certify.')
    return _start_job({'kind': 'certify', 'module': module, 'source': source, 'cohorts': _cohorts(body.get('cohorts')),
                       'title': f'certify {module or "program"}'})


def start_crystallise(body: dict) -> dict:
    import json
    from integration.host import symblic_engine as E
    source = E._clean_source(body.get('source'))
    checked = S.check(source)
    if not checked['ok']:
        e = checked['errors'][0]
        raise E.SymblicApiError(f'line {e.get("line", 0)}: {e["message"]}')
    routine = str(body.get('routine') or '')
    if not any(s.k == 'routine' and s.name == routine for s in S.parse(source)['statements']):
        raise E.SymblicApiError('Pick one of the program\'s routines.')
    domain = body.get('domain')
    if not isinstance(domain, list) or not 1 <= len(domain) <= MAX_DOMAIN:
        raise E.SymblicApiError(f'Give 1 to {MAX_DOMAIN} inputs.')
    if any(len(json.dumps(x)) > 2000 for x in domain):
        raise E.SymblicApiError('An input is too large.')
    by = _cohorts([body.get('by') or 'claude:haiku'])[0]
    try:
        agree = float(body.get('min_agreement', 1.0))
    except (TypeError, ValueError):
        raise E.SymblicApiError('Agreement is a number from 0.5 to 1.') from None
    if not 0.5 <= agree <= 1:
        raise E.SymblicApiError('Agreement is a number from 0.5 to 1.')
    workers = max(1, min(4, int(body.get('workers') or 2)))
    return _start_job({'kind': 'crystallise', 'source': source, 'routine': routine, 'domain': domain, 'by': by,
                       'min_agreement': agree, 'workers': workers, 'title': f'crystallise {routine}'})


def _job_status(job_id: str, folder: str, result) -> str:
    if result and result.get('status') in ('done', 'failed'):
        return result['status']
    if jobs['active'](job_id):
        return 'running'
    age = time.time() - os.path.getmtime(folder)
    return 'starting' if age < 30 else 'lost'


def list_jobs() -> list:
    import glob
    out = []
    for folder in sorted(glob.glob(os.path.join(jobs_dir(), '*')), key=os.path.getmtime, reverse=True)[:100]:
        job_id = os.path.basename(folder)
        if not JOB_RX.match(job_id):
            continue
        job = _load(os.path.join(folder, 'job.json'), {}) or {}
        result = _load(os.path.join(folder, 'result.json'), None)
        row = {'id': job_id, 'kind': job.get('kind'), 'title': job.get('title'), 'created': job.get('created'),
               'status': _job_status(job_id, folder, result)}
        r = (result or {}).get('result') or {}
        if job.get('kind') == 'certify' and r:
            row['summary'] = f'{len(r.get("certified") or [])}/{len(r.get("tests") or [])} tests pass for every agent'
        elif job.get('kind') == 'crystallise' and r:
            row['summary'] = f'{len(r.get("kept") or [])} kept, {len(r.get("left_out") or [])} left out'
        out.append(row)
    return out


def job_view(job_id: str) -> dict:
    folder = _job_dir(job_id)
    job = _load(os.path.join(folder, 'job.json'), {}) or {}
    result = _load(os.path.join(folder, 'result.json'), None)
    log = ''
    try:
        with open(os.path.join(folder, 'log.txt'), encoding='utf-8') as f:
            log = f.read()[-6000:]
    except OSError:
        pass
    return {'id': job_id, 'job': {k: v for k, v in job.items() if k != 'source'}, 'status':
            _job_status(job_id, folder, result), 'result': result, 'log': log}


def stop_job(job_id: str) -> dict:
    _job_dir(job_id)
    return {'ok': jobs['stop'](job_id)}


def save_crystal(body: dict) -> dict:
    from integration.host import symblic_engine as E
    view = job_view(body.get('id'))
    res = (view.get('result') or {}).get('result') or {}
    if view['job'].get('kind') != 'crystallise' or not res.get('module'):
        raise E.SymblicApiError('Only a finished crystal can be saved.')
    return E.save_program({'name': body.get('name'), 'source': res['module']})


# ---------------------------------------------------------------------------
# Evidence: what the experiments measured (tools/scripts/symblic_lang_bench.py, crystallise runs)
# ---------------------------------------------------------------------------

def _paper_row(name: str, rep: dict) -> dict:
    cov = rep.get('coverage') or {}
    cohorts = rep.get('cohorts') or []
    correct = rep.get('correctness') or {}
    return {'kind': 'reproduce', 'name': name, 'title': rep.get('title'), 'reproduces': rep.get('reproduces'),
            'results_reproduce': rep.get('results_reproduce'), 'model_statements': rep.get('model_statements'),
            'model_reproduced': rep.get('model_reproduced'),
            'finished': cov.get('finished', sum(1 for c in cohorts if c.get('status') == 'done')),
            'of': cov.get('of', len(cohorts)),
            'cohorts': [{'by': c.get('by'), 'status': c.get('status'), 'fingerprint': c.get('fingerprint'),
                         'correct': _correct(correct.get(c.get('by')), c), 'error': str(c.get('error') or '')[:160]}
                        for c in cohorts],
            'underspecified': [{'paper_line': u.get('paper_line'), 'section': u.get('section_title'),
                                'name': u.get('name'), 'distinct': u.get('distinct')}
                               for u in rep.get('underspecified') or []]}


def _correct(row, cohort: dict):
    """True/False against the experiment's ground truth; None when there is none or the cohort did not finish
    (an outage is not a wrong answer)."""
    if cohort.get('status') != 'done' or not isinstance(row, dict):
        return None
    c = row.get('correct') or {}
    return None if c.get('why') == 'no result' or 'ok' not in c else bool(c['ok'])


def _realigned(folder: str, rep: dict) -> dict:
    """A record made before alignment counted coverage: align it again from its run folders, with the paper
    found by its SHA-256 among docs/reference/papers. Unchanged when the paper or a run cannot be found."""
    import glob
    import hashlib
    from integration.host import symblic_engine as E
    from symblic.authoring import paper as P
    papers = []
    for path in sorted(glob.glob(os.path.join(E.REPO_ROOT, 'docs', 'reference', 'papers', '*.symd'))):
        with open(path, encoding='utf-8') as f:
            papers.append(f.read())
    by_sha = [t for t in papers if hashlib.sha256(t.encode('utf-8')).hexdigest() == rep.get('sha256')]
    # records made before 2026-10-02 23:15 hashed a paper's definitions instead of the paper (a fixed bug):
    # fall back to the one paper with the record's title
    by_title = [t for t in papers if P.compile_paper(t)['title'] == rep.get('title')]
    for text in by_sha or (by_title if len(by_title) == 1 else []):
        runs = []
        for c in rep['cohorts']:
            st = _load(os.path.join(folder, 'reproduce', re.sub(r'[^A-Za-z0-9_.-]+', '_', c['by']), 'state.json'))
            if not isinstance(st, dict):
                return rep
            runs.append({'by': c['by'], 'report': st})
        fresh = P.align(P.compile_paper(text), P.columns_from_runs(runs))
        fresh['correctness'] = rep.get('correctness')
        return fresh
    return rep


def lang_evidence() -> dict:
    """Every abstraction-layer experiment folder (automation_data/symblic/bench/lang-*), newest first."""
    import glob
    from integration.host import symblic_engine as E
    out = []
    for folder in sorted(glob.glob(os.path.join(E.bench_dir(), 'lang-*')), key=os.path.getmtime, reverse=True)[:30]:
        name = os.path.basename(folder)
        cert = _load(os.path.join(folder, 'certify.json'))
        if isinstance(cert, dict) and cert.get('tests'):
            out.append({'kind': 'certify', 'name': name, 'tests': [{'title': t['title'], 'passed': t['passed'],
                                                                    'of': t['of'], 'cohorts': t['cohorts']}
                                                                   for t in cert['tests']],
                        'certified': cert.get('certified_for_all') or []})
        for path in [os.path.join(folder, 'reproduce.json')] + sorted(glob.glob(os.path.join(folder, '*',
                                                                                             'reproduce.json'))):
            rep = _load(path)
            if isinstance(rep, dict) and rep.get('cohorts'):
                if 'coverage' not in rep:
                    rep = _realigned(os.path.dirname(path), rep)
                out.append(_paper_row(name, rep))
        crystal = _load(os.path.join(folder, 'result.json'))
        if isinstance(crystal, dict) and crystal.get('module'):
            out.append({'kind': 'crystallise', 'name': name, 'routine': crystal.get('routine'),
                        'kept': len(crystal.get('kept') or []), 'left_out': len(crystal.get('left_out') or []),
                        'applicators': crystal.get('applicators'), 'families': crystal.get('families')})
    return {'experiments': out}


def handle(handler, method: str, route: str, data: dict) -> bool:
    from integration.host import symblic_engine as E
    from symblic.lang import abstraction as L
    from symblic.kernel import lockfile as K
    from symblic.authoring import paper as P
    q = handler.get_query_param
    data = data if isinstance(data, dict) else {}
    try:
        if method == 'GET':
            if route == 'library':
                handler.send_json({'modules': L.library()})
            elif route == 'module':
                handler.send_json(module_view(q('name')))
            elif route == 'paper/view':
                handler.send_json(paper_view(q('id')))
            elif route == 'paper/map':
                handler.send_json(paper_map(q('run')))
            elif route == 'lock':
                handler.send_json(lock_get(q('id')))
            elif route == 'lang/jobs':
                handler.send_json({'jobs': list_jobs()})
            elif route == 'lang/job':
                handler.send_json(job_view(q('id')))
            elif route == 'lang/evidence':
                handler.send_json(lang_evidence())
            else:
                return False
            return True
        if method != 'POST':
            return False
        if route == 'tests':
            handler.send_json(tests_run(data))
        elif route == 'paper/check':
            handler.send_json(P.check_paper(E._clean_source(data.get('source'))))
        elif route == 'paper/compile':
            handler.send_json(P.compile_paper(E._clean_source(data.get('source'))))
        elif route == 'paper/run':
            handler.send_json(paper_run(data))
        elif route == 'paper/reproduce':
            handler.send_json(paper_reproduce(data))
        elif route == 'lock':
            handler.send_json(lock_run(data.get('id')))
        elif route == 'lock/replay':
            handler.send_json(lock_replay(data.get('id')))
        elif route == 'lang/certify':
            handler.send_json(start_certify(data))
        elif route == 'lang/crystallise':
            handler.send_json(start_crystallise(data))
        elif route == 'lang/stop':
            handler.send_json(stop_job(data.get('id')))
        elif route == 'lang/save':
            handler.send_json(save_crystal(data))
        else:
            return False
        return True
    except (E.SymblicApiError, P.PaperError, K.LockError) as e:
        handler.send_json({'error': getattr(e, 'message', None) or str(e)}, 400)
        return True
    except S.SymblicError as e:
        handler.send_json({'error': str(e)}, 400)
        return True
