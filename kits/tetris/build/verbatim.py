#!/usr/bin/env python3
"""How much of a built page was dictated by its spec sheet?

For each unit's code in the page's script, count the non-trivial lines (more than punctuation) and how many of them
appear verbatim in the sheet. Lines are compared after collapsing whitespace and dropping a trailing ';' or ','.
The page skeleton outside the script is the sheet's Assemble section, so it counts as dictated in full. A high share
means the sheet dictated the expressions and the models mostly supplied structure around them; it says nothing
about whether the page is correct (the harness says that).

    python3 kits/tetris/build/verbatim.py PAGE.html SHEET.md [--json]

Works for any spec-sheet page whose code is in one inline <script> (the Kirby kit's pages too).
"""
import json
import re
import sys


def norm(line):
    s = re.sub(r'\s+', ' ', line.strip())
    return s.rstrip(';,').strip()


def trivial(s):
    return not re.search(r'[A-Za-z0-9]', s) or s in ('return', 'else', '} else {', 'break', 'continue')


def main(html_path, sheet_path, as_json=False):
    html = open(html_path, encoding='utf-8').read()
    sheet = open(sheet_path, encoding='utf-8').read()
    m = re.search(r'<script>\n?(.*?)</script>', html, re.S)
    script = m.group(1) if m else ''
    hay = re.sub(r'\s+', ' ', sheet.replace('`', ' '))
    units, current = [], None
    for line in script.split('\n'):
        top = re.match(r'^(?:function\s+(\w+)|const\s+(\w+))', line)
        if top:
            current = {'name': top.group(1) or top.group(2), 'lines': 0, 'verbatim': 0, 'examples': []}
            units.append(current)
        if current is None:
            continue
        s = norm(line)
        if trivial(s):
            continue
        current['lines'] += 1
        if len(s) >= 12 and s in hay:
            current['verbatim'] += 1
            if len(current['examples']) < 3:
                current['examples'].append(s[:90])
    total = sum(u['lines'] for u in units)
    same = sum(u['verbatim'] for u in units)
    out = {'script_lines': total, 'verbatim_lines': same,
           'verbatim_share': round(same / total, 3) if total else None,
           'skeleton_lines': len([l for l in html.split('\n') if l.strip()]) - len([l for l in script.split('\n') if l.strip()]),
           'units': units}
    if as_json:
        print(json.dumps(out, indent=1))
        return
    print(f"script: {total} non-trivial lines, {same} verbatim in the sheet ({100 * same / max(1, total):.1f}%)")
    print(f"page skeleton (from the sheet's Assemble section): {out['skeleton_lines']} lines")
    for u in units:
        if u['lines']:
            print(f"  {u['name']:14s} {u['verbatim']:3d}/{u['lines']:3d}  " + ' | '.join(u['examples'][:2]))


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--json']
    if len(args) != 2:
        sys.exit('usage: verbatim.py PAGE.html SHEET.md [--json]')
    main(args[0], args[1], '--json' in sys.argv)
