"""The intent interpreter web page (web/studio/symblic-intent.js): fake DOM and API, plus static rules.

Moved from tests/intent: the page is the original host's interpreter UI and talks to the host API
(integration/host/symblic_intent_api.py), but these checks need only Node.js and the page files. A test is
skipped when Node.js or one of the page files is not present.
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / 'web/studio'


def page(name):
    path = PAGES / name
    if not path.is_file():
        raise unittest.SkipTest(f'{path.relative_to(ROOT)} is not part of this checkout')
    return path.read_text()


class InterpreterPage(unittest.TestCase):
    def test_offline_journeys(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node is not installed')
        page('symblic-intent.js')
        result = subprocess.run([node, str(ROOT / 'tests/symblic_intent_page_check.js')],
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r'\d+ journeys passed')

    def test_untrusted_text_is_never_html(self):
        source = page('symblic-intent.js')
        for token in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval(', 'new Function'):
            self.assertNotIn(token, source)
        self.assertNotIn('requestAnimationFrame', source)
        self.assertEqual(source.count('fetch('), 1)
        self.assertIn("cache: 'no-store'", source)
        self.assertNotIn('localStorage', source)

    def test_page_additive_hook_is_local_and_before_boot(self):
        html = page('symblic.html')
        self.assertEqual(html.count('symblic-intent.js'), 1)
        self.assertEqual(html.count('symblic-intent.css'), 1)
        self.assertLess(html.index('symblic-intent.js'), html.index('symblic-page.js'))
        source = page('symblic-page.js')
        for name in ('write', 'interpreter', 'plan', 'runs', 'compare', 'tighten', 'language', 'evidence'):
            self.assertIn("{ id: '" + name + "'", source)
        self.assertLess(source.index("{ id: 'write'"), source.index("{ id: 'interpreter'"))

    def test_theme_and_mobile_input_rules(self):
        css = page('symblic-intent.css')
        self.assertFalse(re.search(r'#[a-fA-F0-9]{3,8}\b', css))
        self.assertIn('font-size: 16px', css)
        self.assertIn('min-height: 44px', css)
        self.assertIn('overflow-wrap: anywhere', css)
        self.assertIn('var(--', css)
        self.assertNotIn('!important', css)
        source = page('symblic-intent.js')
        self.assertIn('readonly:', source)
        # Handoff links are followed only after the page's own URL check accepts them.
        self.assertRegex(source, r'function safe\w*Url\(')


if __name__ == '__main__':
    unittest.main()
