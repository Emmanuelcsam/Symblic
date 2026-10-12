"""symblic.authoring.paper: compiling a literate paper (.symd), its source map, and the reproduction protocol with
fake cohorts. No model, no network, no host; run folders are temporary."""

import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # the repository root

from symblic.kernel import language as S  # noqa: E402
from symblic.lang import abstraction as L  # noqa: E402
from symblic.authoring import paper as P  # noqa: E402
from symblic.kernel import run as SR  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the repository root
PAPERS = os.path.join(ROOT, 'docs', 'reference', 'papers')
RECIPE = os.path.join(PAPERS, 'scaling-a-recipe.symd')

PAPER = '''---
by: fake:x
effort: low
---
# Colour study

We name colours exactly. A colour is one of the three primaries.

## Definitions

- **primary**: red, yellow or blue
**sky** means the daytime sky on a clear day

## Asking

The question below is about the sky {not a placeholder}.

```symblic
ask hue: one of {red, yellow, blue} "Which primary is closest to the sky?"
let doubled = [hue, hue].
show doubled.
```

```python
print("quoted code is prose")
```
'''


class FakeApps:
    def __init__(self, answer):
        self.answer, self.reqs, self.lock = answer, [], threading.Lock()

    def call(self, req):
        with self.lock:
            self.reqs.append(req)
        return {'ok': True, 'json': self.answer(req['prompt'], req), 'ms': 1}


def runner_for(answers: dict, record: list | None = None):
    """A runner whose cohort `by` answers with answers[by](prompt). Each run starts from an empty folder."""
    def runner(source, by):
        apps = FakeApps(answers[by if isinstance(by, str) else by[0]])
        folder = tempfile.mkdtemp()
        try:
            run = SR.Run(source, {}, apps, {'by': by}, folder=folder)
            rep = run.execute()
            if record is not None:
                record.append((by, apps.reqs))
            return {'report': rep, 'trace': run.trace}
        finally:
            shutil.rmtree(folder)
    return runner


class Base(unittest.TestCase):
    def setUp(self):
        L.register()


class Compile(Base):
    def test_structure_terms_context_and_source_map(self):
        c = P.compile_paper(PAPER)
        src = c['source']
        self.assertEqual(c['title'], 'Colour study')
        self.assertIn('use by="fake:x".', src)
        self.assertIn('use effort=low.', src)
        self.assertIn('program Colour study.', src)
        self.assertIn('term "primary" means "red, yellow or blue".', src)
        self.assertIn('term "sky" means "the daytime sky on a clear day".', src)
        self.assertEqual([t['term'] for t in c['terms']], ['primary', 'sky'])
        self.assertIn('{{not a placeholder}}', src)           # prose braces are literal
        self.assertIn('quoted code is prose', src)             # other code blocks are context, not statements
        self.assertIn('use context=[paper_definitions, section_0, section_2].', src)
        self.assertIn('- sky: the daytime sky on a clear day', src)      # every definition reaches every ask
        prog = S.parse(src)
        ask = next(s for s in prog['statements'] if s.k == 'ask')
        pos = P.paper_line(c, ask.line)
        self.assertEqual(pos['paper_line'], PAPER.split('\n').index(next(
            ln for ln in PAPER.split('\n') if ln.startswith('ask hue'))) + 1)
        self.assertEqual(pos['section_title'], 'Asking')
        self.assertEqual(c['sha256'], P.compile_paper(PAPER)['sha256'])
        import hashlib                                     # the whole paper's hash (a paper with definitions once
        self.assertEqual(c['sha256'], hashlib.sha256(PAPER.encode('utf-8')).hexdigest())   # hashed only those)
        self.assertEqual(c['source'], P.compile_paper(PAPER)['source'])      # deterministic

    def test_the_section_prose_and_definitions_reach_the_capsule(self):
        apps = FakeApps(lambda p, q: {'answer': 'blue'})
        run = SR.Run(P.compile_paper(PAPER)['source'], {}, apps, {})
        rep = run.execute()
        self.assertEqual(rep['status'], 'done', rep['error'])
        prompt = apps.reqs[0]['prompt']
        self.assertIn('We name colours exactly', prompt)                 # the introduction
        self.assertIn('The question below is about the sky', prompt)     # the section's prose
        self.assertIn('red, yellow or blue', prompt)                     # the definition of "primary"
        self.assertEqual(run.kernel.env.lookup('doubled').value, ('blue', 'blue'))

    def test_context_none_and_an_ask_with_its_own_context(self):
        paper = PAPER.replace('effort: low', 'effort: low\ncontext: none')
        apps = FakeApps(lambda p, q: {'answer': 'blue'})
        rep = SR.Run(P.compile_paper(paper)['source'], {}, apps, {}).execute()
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertNotIn('We name colours exactly', apps.reqs[0]['prompt'])
        own = PAPER.replace('closest to the sky?"', 'closest to the sky?" with context=none')
        apps = FakeApps(lambda p, q: {'answer': 'blue'})
        SR.Run(P.compile_paper(own)['source'], {}, apps, {}).execute()
        self.assertNotIn('We name colours exactly', apps.reqs[0]['prompt'])

    def test_an_ask_reads_everything_before_it(self):
        paper = ('# Box\n\nWe build a box.\n\n## The object\n\nThe box is 2 units wide.\n\n## Aside\n\n'
                 'Boxes are old.\n\n## Construction\n\nBuild it.\n\n'
                 '```symblic\nask w: Int "How wide is the box?"\n```\n')
        src = P.compile_paper(paper)['source']
        self.assertIn('use context=[section_0, section_1, section_2, section_3].', src)
        apps = FakeApps(lambda p, q: {'answer': 2})
        SR.Run(src, {}, apps, {'by': 'fake:x'}).execute()
        self.assertIn('2 units wide', apps.reqs[0]['prompt'])            # stated two sections earlier
        narrow = P.compile_paper('---\ncontext: section\n---\n' + paper)['source']
        self.assertIn('use context=[section_0, section_3].', narrow)
        long = paper.replace('Boxes are old.', 'Boxes are old. ' * 400).replace(
            'The box is 2 units wide.', 'The box is 2 units wide. ' + 'Long. ' * 1000)  # 6 000 + 6 000 > budget
        c = P.compile_paper(long)
        self.assertIn('use context=[section_0, section_2, section_3].', c['source'])   # the farther one goes
        self.assertTrue(any('left out of the context' in w['message'] for w in c['warnings']))

    def test_lint_flags_vague_quantities_unless_the_paper_defines_them(self):
        def kinds(text):
            return sorted({w['message'].split('"')[1] for w in P.lint(text)})
        base = ('# T\n\nHeat to 600 C slowly, hold for a couple of hours at about 3 C per minute.\n'
                'Use 1% dispersant.\n')
        self.assertEqual(kinds(base), ['1%', 'a couple of', 'about 3', 'slowly'])
        defined = (base + '\n## Definitions\n\n- **slowly**: 5 C per minute\n- **a couple of hours**: 2 hours\n'
                   '- **about 3 C per minute**: exactly 3 C per minute\n'
                   '- **dispersant percentage**: of dry powder\n')
        self.assertEqual(kinds(defined), [])
        self.assertEqual(kinds('# T\n\nUse 5% w/w salt and 2 % of the powder.\n'), [])
        c = P.check_paper(base)
        self.assertTrue(any(w.get('kind') == 'vague' and w['line'] == 3 for w in c['warnings']))
        for name in ('furnace-schedule', 'furnace-schedule-contract', 'slurry', 'scaling-a-recipe'):
            with open(os.path.join(PAPERS, name + '.symd'), encoding='utf-8') as f:
                self.assertEqual(P.lint(f.read()), [], name)

    def test_malformed_papers(self):
        for bad, msg in (('---\nby: x\n# no end\n', 'front matter'), ('# T\n```symblic\nlet x = 1.\n', 'not closed'),
                         ('# T\n- **a**: one\n- **A**: two\n', 'defined twice')):
            with self.assertRaises(P.PaperError) as cm:
                P.compile_paper(bad)
            self.assertIn(msg, cm.exception.message)
        c = P.check_paper('# T\n\n```symblic\nlet x = .\n```\n')
        self.assertFalse(c['ok'])
        self.assertEqual(c['errors'][0]['line'], 4)                     # the paper's line, not the program's
        warning = P.compile_paper('---\nmodel: x\n---\n# T\n')['warnings'][0]['message']
        self.assertIn('unknown front matter key', warning)

    def test_the_example_paper_checks_and_runs_with_a_careful_reader(self):
        with open(RECIPE, encoding='utf-8') as f:
            text = f.read()
        c = P.check_paper(text)
        self.assertTrue(c['ok'], c['errors'])

        def careful(prompt, req):
            if 'How many servings' in prompt:
                return {'answer': 4}
            return {'answer': [{'item': 'milk', 'amount': 1.5, 'unit': 'cup'},
                               {'item': 'melted butter', 'amount': 2, 'unit': 'tablespoon'},
                               {'item': 'baking powder', 'amount': 1, 'unit': 'teaspoon'},
                               {'item': 'flour', 'amount': 200, 'unit': 'g'}]}
        run = SR.Run(P.compile_paper(text)['source'], {}, FakeApps(careful), {'by': 'fake:x'})
        rep = run.execute()
        self.assertEqual(rep['status'], 'done', rep['error'])
        scaled = run.kernel.env.lookup('scaled').value
        self.assertEqual(scaled[0]['amount'], 540)                     # 1.5 cups x 240 mL x 6/4
        self.assertEqual(scaled[3], {'item': 'flour', 'amount': 300, 'unit': 'g'})


class Reproduce(Base):
    def test_identical_readers_reproduce_and_a_divergent_one_is_traced_to_the_paper(self):
        same = lambda p, q: {'answer': 'blue'}                        # noqa: E731
        rep = P.reproduce(PAPER, ['fake:a', 'fake:b', 'fake:c'], runner_for({'fake:a': same, 'fake:b': same,
                                                                              'fake:c': same}))
        self.assertTrue(rep['reproduces'])
        self.assertEqual((rep['model_statements'], rep['model_reproduced'], rep['score']), (1, 1, 1.0))
        self.assertEqual(rep['underspecified'], [])

        odd = lambda p, q: {'answer': 'yellow'}                       # noqa: E731
        rep = P.reproduce(PAPER, ['fake:a', 'fake:b', 'fake:c'], runner_for({'fake:a': same, 'fake:b': same,
                                                                              'fake:c': odd}))
        self.assertFalse(rep['reproduces'])
        self.assertEqual(rep['model_reproduced'], 0)
        hue = next(u for u in rep['underspecified'] if u['name'] == 'hue')
        self.assertEqual(hue['section_title'], 'Asking')
        self.assertEqual(hue['distinct'], 2)
        self.assertEqual([len(g[1]) for g in hue['groups']], [2, 1])
        self.assertEqual([u['name'] for u in rep['underspecified']], ['hue'])     # the root, not what follows
        self.assertIn('doubled', [i['name'] for i in rep['inherited']])          # the kernel step inherits it
        text = P.report_text(rep)
        self.assertIn('does not reproduce', text)
        self.assertIn(f'paper line {hue["paper_line"]} (Asking): hue', text)

    def test_a_failed_cohort_is_coverage_not_disagreement(self):
        same = lambda p, q: {'answer': 'blue'}                        # noqa: E731

        def runner(source, by):
            if by == 'fake:down':
                class Down:
                    def call(self, req):
                        return {'ok': False, 'error': 'quota: paused (outage)', 'fatal': True}
                return {'report': SR.Run(source, {}, Down(), {'by': by}).execute()}
            return runner_for({'fake:a': same, 'fake:b': same})(source, by)
        rep = P.reproduce(PAPER, ['fake:a', 'fake:b', 'fake:down'], runner)
        self.assertFalse(rep['reproduces'])                         # not every cohort finished
        self.assertTrue(rep['results_reproduce'])                   # but every finished one agrees
        self.assertEqual(rep['underspecified'], [])
        self.assertEqual((rep['coverage']['finished'], rep['coverage']['of']), (2, 3))
        self.assertIn('outage', rep['coverage']['failed'][0]['error'])
        self.assertEqual((rep['model_statements'], rep['model_reproduced']), (1, 1))

    def test_results_can_reproduce_while_a_reading_differs(self):
        paper = PAPER.replace('let doubled = [hue, hue].\nshow doubled.', 'ask note: Text "Any remark?"\nshow hue.')
        rep = P.reproduce(paper, ['fake:a', 'fake:b'], runner_for({
            'fake:a': lambda p, q: {'answer': 'blue' if 'primary' in p.split('STATEMENT', 1)[-1] else 'none'},
            'fake:b': lambda p, q: {'answer': 'blue' if 'primary' in p.split('STATEMENT', 1)[-1] else 'a remark'}}))
        self.assertFalse(rep['reproduces'])
        self.assertTrue(rep['results_reproduce'])
        self.assertEqual([u['name'] for u in rep['underspecified']], ['note'])
        self.assertIn('RESULTS REPRODUCE', P.report_text(rep))

    def test_each_cohort_starts_fresh(self):
        seen = []
        same = lambda p, q: {'answer': 'blue'}                        # noqa: E731
        P.reproduce(PAPER, ['fake:a', 'fake:b'], runner_for({'fake:a': same, 'fake:b': same}, seen))
        self.assertEqual([len(reqs) for _by, reqs in seen], [1, 1])    # no cohort reused another's answers

    def test_a_failed_cohort_means_no_reproduction(self):
        same = lambda p, q: {'answer': 'blue'}                        # noqa: E731
        broken = lambda p, q: {'answer': 'green'}                     # noqa: E731  (not a primary: invalid)
        rep = P.reproduce(PAPER, ['fake:a', 'fake:b'], runner_for({'fake:a': same, 'fake:b': broken}))
        self.assertFalse(rep['reproduces'])
        self.assertEqual(rep['cohorts'][1]['status'], 'failed')
        with self.assertRaises(P.PaperError):
            P.reproduce(PAPER, ['fake:a'], runner_for({'fake:a': same}))


if __name__ == '__main__':
    unittest.main()
