"""Finite client conformance gates use synthetic candidates and no model/store."""
import json
import re
import unittest
from pathlib import Path

from symblic.kernel import language as S
from symblic.english import pixel_checks as C
from symblic.js import check as JS
from symblic.kernel.run import Run


@unittest.skipUnless(JS.available(), 'Local JavaScript sandbox unavailable')
class PixelChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads(Path(__file__).resolve().parents[1].joinpath('fixtures', 'symblic-pixel-program.json').read_text())
        assert fixture['test_only'] is True
        cls.functions = {re.match(r'function ([A-Za-z]+)\(', line)[1]: line
                         for line in fixture['implementation'].splitlines() if line.startswith('function ')}
        cls.host = C.bootstrap({'width': 800, 'height': 600, 'radius': 5, 'fixed_y': 300})

    def closure(self, target):
        found = []
        def visit(name):
            for dependency in C.DEPENDENCIES[name]:
                visit(dependency)
            if name not in found:
                found.append(name)
        visit(target)
        return found

    def test_native_quoted_sources_and_every_gate_without_model(self):
        lines = ['program Pixel conformance plumbing.', 'use profile=verified, context=none.',
                 'given pixel_vm_boot: Text.',
                 'let pixel_vm_parser = ' + C._literal(self.host['parser_source']) + '.']
        lines.extend('let unit_' + name + ' = ' + C._literal(self.functions[name]) + '.' for name in C.ABI)
        for name in C.ABI:
            names = self.closure(name)
            lines.extend(C.gate_lines(name, ['unit_' + n for n in names], names, retained=True))
        lines.extend(C.gate_lines('assembly', ['unit_' + n for n in C.ABI], list(C.ABI), retained=True))
        report = Run('\n'.join(lines) + '\n', self.host['inputs'], None, {'profile': 'verified'}).execute()
        self.assertEqual('done', report['status'], report.get('error'))
        self.assertEqual(0, report['calls'])

    def test_invalid_candidates_are_data_and_refused_at_their_unit(self):
        cases = [
            ('delta', "'use strict';\n" + self.functions['delta'], '', 'top level'),
            ('delta', 'function delta(a,b){for(let i=0;i<1;i++){continue;}return a-b;}', '', 'ContinueStatement'),
            ('nextX', 'function nextX(p){if(p===null||p===undefined)return 0;if(p===799)return 0;return p+1;}', '', 'unknown or forbidden'),
            ('whitePixels', 'function whitePixels(cx,cy){const result=[];for(let y=0;y<600;y++){for(let x=0;x<800;x++){if(inside(x,y,cx,cy))result.push(y*800+x);}}return result;}', '', 'budget'),
            ('whitePixels', self.functions['whitePixels'].replace('const box = bounds(cx, cy)', 'const bounds = bounds(cx, cy)'), '', 'local binding'),
            ('drawPixels', self.functions['drawPixels'].replace('return buffer;', 'buffer[479999]=0;return buffer;'), ',0,1', '479999'),
            ('drawPixels', self.functions['drawPixels'].replace('return buffer;', 'buffer[0]=1;return buffer;'), ',0,1', 'pixel 0'),
            ('delta', 'globalThis.pixelCheck=function(){return true;};' + self.functions['delta'], '', 'top level'),
        ]
        for target, candidate, suffix, expected in cases:
            with self.subTest(target=target, reason=expected):
                names = self.closure(target)
                bodies = tuple(candidate if name == target else self.functions[name] for name in names)
                source = (self.host['parser_source'] + '\n' + self.host['inputs'][C.INPUT_NAME]
                          + '\nvar pixelSources = ' + S.show(bodies) + ';\n')
                call = 'pixelCheck(' + json.dumps(target) + ',' + json.dumps(names) + suffix + ')'
                result = JS.evaluate(source, [call])[0]
                self.assertIs(result.get('ok'), False, result)
                if expected == 'budget' and 'timed out' in result.get('error', ''):
                    # on a heavily loaded machine the sandbox's 3 s wall limit can fire before the interpreter's step
                    # budget; the brute-force candidate is refused either way
                    continue
                self.assertIn(expected, result.get('error', ''))


if __name__ == '__main__':
    unittest.main()
