"""Symblic abstraction-layer experiments with real applicators (run by the operator; they call models):

  (a) certify: the `text` library routines' certification tests, once per cohort of agents;
  (b) reproduce: docs/reference/papers/scaling-a-recipe.symd, once per cohort, aligned statement by statement,
      plus each cohort's correctness against the exact expected shopping list.

    python3 tools/scripts/symblic_lang_bench.py --out DIR [--cohort SPEC ...] [--only certify|reproduce]

Every cohort starts from an empty record (its own run folder). Model calls go only through
symblic.providers.applicators.Applicators, so configure your applicators first (SYMBLIC_OLLAMA_HOSTS for local
models, SYMBLIC_COMMAND_<NAME> for agent command lines). This script adds a global cap on concurrent qwen3:4b
calls and a thermal gate that holds new calls while any worker node reads HOT °C or more, until all are below
COOL. The gate reads node temperatures from the original host's cluster status route
(SYMBLIC_CLUSTER_STATUS_URL, default http://127.0.0.1:8080/api/cluster/status); without such a route it never
holds. Results go to --out, which should be a private folder outside this repository.

In the original host the experiment ran in a transient systemd user unit (CPUQuota=50%, MemoryMax=1G) with
the models on the host's worker nodes; its recorded outcomes are summarized in docs/reference/LANGUAGE-3.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the repository root
sys.path.insert(0, ROOT)

from symblic.kernel import language as S  # noqa: E402
from symblic.lang import abstraction as L  # noqa: E402
from symblic.authoring import paper as P  # noqa: E402
from symblic.kernel import run as SR  # noqa: E402

# Default cohorts: two independent runs of one local model through Ollama. The original experiment also used
# agent command lines; add them with --cohort command:NAME (configured as SYMBLIC_COMMAND_NAME, see
# symblic/providers/README.md).
COHORTS = ['ollama:qwen3:4b-instruct', 'ollama:qwen3:4b-instruct']
PAPER = os.path.join(ROOT, 'docs', 'reference', 'papers', 'scaling-a-recipe.symd')
# The recipe read carefully: 1.5 cup milk, 2 tbsp butter, 1 tsp baking powder, 200 g flour, for 4 servings,
# scaled to 6: millilitres by the paper's definitions (cup 240, tbsp 15, tsp 5).
EXPECTED_AMOUNTS = [Fraction(540), Fraction(45), Fraction(15, 2), Fraction(300)]


STATUS_URL = os.environ.get('SYMBLIC_CLUSTER_STATUS_URL', 'http://127.0.0.1:8080/api/cluster/status')
NODE_PREFIX = os.environ.get('SYMBLIC_NODE_PREFIX', 'node')   # node ids the thermal gate watches


class Gate:
    """Thermal hold and the qwen cap, shared by every cohort in this process."""

    def __init__(self, hot: float, cool: float, qwen_max: int, log):
        self.hot, self.cool, self.log = hot, cool, log
        self.qwen = threading.BoundedSemaphore(qwen_max)
        self.lock = threading.Lock()
        self.checked = 0.0
        self.holding = False
        self.holds = []

    def temps(self) -> dict:
        req = urllib.request.Request(STATUS_URL, headers={'Host': urllib.parse.urlsplit(STATUS_URL).netloc})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=60) as r:
                data = json.loads(r.read())
        except Exception:  # noqa: BLE001  (unknown temperatures: keep the last decision)
            return {}
        return {n['id']: float((n.get('vitals') or {}).get('temp') or 0) for n in data.get('status') or []
                if str(n.get('id', '')).startswith(NODE_PREFIX) and n.get('online')}

    def wait(self) -> None:
        with self.lock:
            if time.time() - self.checked < 45 and not self.holding:
                return
            self.checked = time.time()
            t = self.temps()
            if not t or max(t.values()) < self.hot:
                return
            self.holding = True
            hot = max(t, key=t.get)
            self.log(f'thermal hold: {hot} at {t[hot]:.0f} °C (pause until every node < {self.cool:.0f} °C)')
            started = time.time()
            while True:
                time.sleep(60)
                t = self.temps()
                if t and max(t.values()) < self.cool:
                    break
            self.holds.append({'node': hot, 'seconds': round(time.time() - started)})
            self.log('thermal hold released')
            self.holding = False
            self.checked = time.time()


class GatedApps:
    def __init__(self, apps, gate: Gate):
        self.apps, self.gate = apps, gate
        self.calls = 0
        self.lock = threading.Lock()

    def call(self, req):
        self.gate.wait()
        app = req['app']
        qwen = app.get('engine') == 'ollama' and str(app.get('model') or '').startswith('qwen3:4b')
        if qwen:
            self.gate.qwen.acquire()
        try:
            with self.lock:
                self.calls += 1
            return self.apps.call(req)
        finally:
            if qwen:
                self.gate.qwen.release()

    def delegate(self, *a, **k):
        return {'error': 'delegation is off in this experiment'}


def cohort_names(cohorts: list) -> list:
    seen, out = {}, []
    for c in cohorts:
        seen[c] = seen.get(c, 0) + 1
        out.append(c if cohorts.count(c) == 1 else f'{c}#{seen[c]}')
    return out


def safe(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', name)


def save(path: str, data) -> None:
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, ensure_ascii=False, default=str)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def certify_text(out: str, cohorts: list, names: list, make_apps, log) -> dict:
    source = L.library_source('text')

    def one(i):
        by, name = cohorts[i], names[i]
        folder = os.path.join(out, 'certify', safe(name))
        os.makedirs(folder, mode=0o700, exist_ok=True)
        t0 = time.time()
        apps = make_apps()
        res = L.run_tests(source, apps, by=by, folder=folder, log=lambda t: log(f'[certify {name}] {t}'))
        res['seconds'] = round(time.time() - t0, 1)
        res['model_calls'] = apps.calls
        log(f'[certify {name}] {res["passed"]}/{res["passed"] + res["failed"]} passed in {res["seconds"]} s')
        return name, res
    with ThreadPoolExecutor(max_workers=len(cohorts)) as pool:
        per = dict(pool.map(one, range(len(cohorts))))
    titles = [t['title'] for t in next(iter(per.values()))['tests']]
    tests = []
    for title in titles:
        rows = {}
        for name, res in per.items():
            t = next((x for x in res['tests'] if x['title'] == title), None)
            rows[name] = {'status': t['status'] if t else 'missing', 'calls': (t or {}).get('calls'),
                          'error': ((t or {}).get('error') or {}).get('message')}
        tests.append({'title': title, 'passed': sum(r['status'] == 'passed' for r in rows.values()),
                      'of': len(rows), 'cohorts': rows})
    return {'cohorts': {n: {k: r[k] for k in ('passed', 'failed', 'status', 'error', 'asks', 'calls', 'cached',
                                                'seconds', 'model_calls')} for n, r in per.items()},
            'tests': tests, 'certified_for_all': [t['title'] for t in tests if t['passed'] == t['of']]}


def reproduce_recipe(out: str, cohorts: list, names: list, make_apps, log, paper: str = PAPER,
                     expect: dict | None = None) -> dict:
    text = open(paper, encoding='utf-8').read()
    reports = {}

    def runner_for(name):
        def runner(source, by):
            folder = os.path.join(out, 'reproduce', safe(name))
            os.makedirs(folder, mode=0o700, exist_ok=True)
            with open(os.path.join(folder, 'program.sym'), 'w', encoding='utf-8') as f:
                f.write(source)
            with open(os.path.join(folder, 'meta.json'), 'w', encoding='utf-8') as f:
                json.dump({'inputs': {}, 'options': {'by': by}, 'title': f'scaling-a-recipe · {name}'}, f)
            apps = make_apps()
            run = SR.Run(source, {}, apps, {'by': by}, folder=folder, log=lambda t: log(f'[paper {name}] {t}'))
            rep = run.execute()
            if expect is None:
                scaled = run.kernel.env.lookup('scaled')
                correct = _recipe_correct(scaled.value if scaled else None)
            else:
                correct = _expected(run, expect)
            steps = run.kernel.env.lookup('steps')
            reports[name] = {'status': rep['status'], 'error': rep.get('error'), 'fingerprint': rep['fingerprint'],
                             'model_calls': apps.calls, 'seconds': rep['seconds'], 'correct': correct,
                             'steps': S.show(steps.value, 600) if steps else None}
            log(f'[paper {name}] {rep["status"]} {rep["fingerprint"]} correct={reports[name]["correct"]}')
            return {'report': rep}
        return runner

    compiled = P.compile_paper(text)
    results = {}

    def one(i):
        results[names[i]] = runner_for(names[i])(compiled['source'], cohorts[i])
    with ThreadPoolExecutor(max_workers=len(cohorts)) as pool:
        list(pool.map(one, range(len(cohorts))))
    runs = [{'by': names[i], 'report': results[names[i]]['report']} for i in range(len(cohorts))]
    aligned = P.align(compiled, P.columns_from_runs(runs))
    aligned['sha256'] = compiled['sha256']
    aligned['correctness'] = reports
    aligned['text'] = P.report_text(aligned)
    return aligned


def _expected(run, expect: dict) -> dict:
    """{name: exact value}: each binding compared exactly (numbers as rationals)."""
    out = {'ok': True, 'values': {}}
    for name, want in expect.items():
        b = run.kernel.env.lookup(name)
        got = b.value if b else None
        out['values'][name] = S.show(got, 200) if got is not None else None
        try:
            same = got is not None and Fraction(got) == Fraction(want)
        except (TypeError, ValueError):
            same = got == want
        out['ok'] = out['ok'] and same
    return out


def _recipe_correct(scaled) -> dict:
    if not scaled:
        return {'ok': False, 'why': 'no result'}
    amounts = [S.norm_num(x.get('amount')) if isinstance(x, dict) else None for x in scaled]
    units = [x.get('unit') if isinstance(x, dict) else None for x in scaled]
    ok_amounts = [Fraction(a) == e if a is not None else False for a, e in zip(amounts, EXPECTED_AMOUNTS, strict=False)]
    return {'ok': len(scaled) == 4 and all(ok_amounts) and units == ['ml', 'ml', 'ml', 'g'],
            'amounts': [str(a) for a in amounts], 'units': units}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Certify the text library and reproduce a paper once per cohort of '
                                            'applicators (calls real models; see the module docstring).')
    p.add_argument('--out', required=True, help='a private folder outside this repository for the results')
    p.add_argument('--cohort', action='append', default=[],
                   help='an applicator spec, repeatable (default: ' + ', '.join(COHORTS) + ')')
    p.add_argument('--only', choices=['certify', 'reproduce'], default=None)
    p.add_argument('--paper', action='append', default=[], help='reproduce these papers instead of the recipe')
    p.add_argument('--expect', action='append', default=[], help='NAME=VALUE ground truth for --paper (exact)')
    p.add_argument('--qwen-max', type=int, default=2)
    p.add_argument('--avoid', default='', help='comma-separated node names the applicators should avoid')
    p.add_argument('--hot', type=float, default=85)
    p.add_argument('--cool', type=float, default=75)
    a = p.parse_args(argv)
    out = os.path.abspath(a.out)
    os.makedirs(out, mode=0o700, exist_ok=True)
    logf = open(os.path.join(out, 'log.txt'), 'a', encoding='utf-8')
    log_lock = threading.Lock()

    def log(text):
        line = f'{time.strftime("%H:%M:%S")} {text}'
        with log_lock:
            logf.write(line + '\n')
            logf.flush()
            print(line, flush=True)
    from symblic.providers import applicators as SA
    if hasattr(SA, 'install_sigterm'):
        SA.install_sigterm()                 # a SIGTERM cancels this process's live model calls
    cohorts = a.cohort or COHORTS
    names = cohort_names(cohorts)
    gate = Gate(a.hot, a.cool, a.qwen_max, log)
    avoid = [x for x in a.avoid.split(',') if x]

    def make_apps():
        return GatedApps(SA.Applicators(owner_label='operator (Symblic abstraction-layer experiments)',
                                        run_id=os.path.basename(out), avoid=avoid, thermal=True), gate)
    meta = {'started': time.time(), 'cohorts': dict(zip(names, cohorts, strict=True)), 'avoid': avoid,
            'qwen_max': a.qwen_max,
            'thermal': [a.hot, a.cool], 'versions': {'lang': S.VERSION, 'canon': getattr(S, 'CANON_VERSION', 1)},
            'text_sha256': L.describe_module('text')['sha256']}
    save(os.path.join(out, 'meta.json'), meta)
    log(f'start: cohorts {names}, avoid {avoid}, qwen max {a.qwen_max}, thermal {a.hot}/{a.cool}')
    if a.only in (None, 'certify'):
        cert = certify_text(out, cohorts, names, make_apps, log)
        save(os.path.join(out, 'certify.json'), cert)
        log('certify: ' + ', '.join(f'{t["title"]} {t["passed"]}/{t["of"]}' for t in cert['tests']))
    if a.only in (None, 'reproduce') and not a.paper:
        rep = reproduce_recipe(out, cohorts, names, make_apps, log)
        save(os.path.join(out, 'reproduce.json'), rep)
        log('reproduce:\n' + rep['text'])
    expect = dict(kv.split('=', 1) for kv in a.expect) or None
    for paper in a.paper:
        tag = os.path.splitext(os.path.basename(paper))[0]
        sub = os.path.join(out, tag)
        os.makedirs(sub, mode=0o700, exist_ok=True)
        rep = reproduce_recipe(sub, cohorts, names, make_apps, log, paper=os.path.abspath(paper), expect=expect)
        save(os.path.join(sub, 'reproduce.json'), rep)
        log(f'reproduce {tag}:\n' + rep['text'])
    meta.update(finished=time.time(), thermal_holds=gate.holds)
    save(os.path.join(out, 'meta.json'), meta)
    log('done')
    return 0


if __name__ == '__main__':
    sys.exit(main())
