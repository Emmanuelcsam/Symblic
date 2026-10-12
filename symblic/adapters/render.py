"""Deterministic drawings: the same arguments give the same SVG bytes on every machine.

No floating point reaches the output: geometry is computed with Decimal arithmetic (symblic's own sin/cos,
not the platform's libm), every coordinate is rounded half-even to two decimals, attributes are written in
a fixed order, and colours are resolved from a fixed table. So `flower(petals=5, color="gold")` has one
fingerprint on every machine and CPU architecture, and from whichever agent produced the arguments.

    flower(petals, color, center, shape, layers, length, width, rotation, leaves, stem, size, background)
    rose(k, color, size)            the polar rose r = cos(k θ)
    polygon(sides, color, size)

Depends on: symblic.kernel.language. Used by: the `draw` statement and the flower, rose and polygon builtins
(symblic.kernel.language), and symblic.adapters.geometry.
"""

from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction

from symblic.kernel import language as S

COLORS = {
    'red': '#d7263d', 'crimson': '#b5172f', 'scarlet': '#e03a1e', 'pink': '#f08bb4', 'rose': '#e0607e',
    'magenta': '#c2187a', 'orange': '#ff6b35', 'coral': '#ff7f6b', 'peach': '#ffb38a', 'yellow': '#f6c90e',
    'gold': '#e8a317', 'amber': '#f0a202', 'cream': '#f5ecd7', 'white': '#fbfaf6', 'ivory': '#f7f3e3',
    'lavender': '#b8a1d9', 'violet': '#7b4fb0', 'purple': '#6a2c91', 'indigo': '#3f3a8c', 'blue': '#2f6fd6',
    'sky': '#7fb8e6', 'teal': '#2a9d8f', 'green': '#3f8f4a', 'leaf': '#4f8a3c', 'olive': '#6b7f2a',
    'brown': '#6b4226', 'chocolate': '#4a2c17', 'black': '#1a1a1a', 'grey': '#8a8a8a', 'gray': '#8a8a8a',
    'paper': '#f4f1eb', 'none': 'none',
}
SHAPES = ('round', 'pointed', 'heart', 'teardrop', 'spatula', 'fringed')
GOLDEN_ANGLE = Decimal('137.50776405003785464634873962')


class RenderError(S.SymblicError):
    pass


def _dec(v) -> Decimal:
    if isinstance(v, bool):
        raise RenderError('expected a number, got true/false', kind='type')
    if isinstance(v, (int, Fraction)):
        return S.num_to_dec(v)
    if isinstance(v, Decimal):
        return v
    if isinstance(v, str):
        try:
            return S.num_to_dec(S._coerce_num(v, 'value'))
        except S.SymblicError:
            pass
    raise RenderError(f'expected a number, got {S.type_name(v)}', kind='type')


def fmt(d: Decimal) -> str:
    with localcontext() as ctx:
        ctx.prec = 60
        q = Decimal(d).quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
    if q == 0:
        return '0'
    s = format(q, 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s


def color(value, default: str) -> str:
    v = str(value if value is not None else default).strip().lower()
    if v in COLORS:
        return COLORS[v]
    if len(v) in (4, 7) and v.startswith('#') and all(c in '0123456789abcdef' for c in v[1:]):
        if len(v) == 4:
            v = '#' + ''.join(c * 2 for c in v[1:])
        return v
    raise RenderError(f'unknown colour {value!r}: use a name ({", ".join(sorted(k for k in COLORS if k != "none"))}) '
                      f'or #rrggbb', kind='type')


def shade(hex_color: str, amount: Fraction) -> str:
    """Mix toward black (amount > 0) or white (amount < 0), exactly, in integer arithmetic."""
    if hex_color == 'none':
        return hex_color
    rgb = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    out = []
    for c in rgb:
        if amount >= 0:
            v = Fraction(c) * (1 - amount)
        else:
            v = Fraction(c) + (255 - c) * (-amount)
        out.append(max(0, min(255, int(v + Fraction(1, 2)))))
    return '#' + ''.join(f'{c:02x}' for c in out)


def _int(v, name, lo, hi, default):
    if v is None:
        return default
    if isinstance(v, bool) or not S.is_num(v) or S.norm_num(v) != int(v):
        raise RenderError(f'{name} must be a whole number', kind='type')
    v = int(v)
    if not lo <= v <= hi:
        raise RenderError(f'{name} must be from {lo} to {hi}', kind='type')
    return v


def _frac(v, name, lo, hi, default):
    if v is None:
        return Fraction(default)
    if isinstance(v, bool) or not S.is_num(v):
        raise RenderError(f'{name} must be a number', kind='type')
    f = Fraction(v)
    if not Fraction(lo) <= f <= Fraction(hi):
        raise RenderError(f'{name} must be from {lo} to {hi}', kind='type')
    return f


def _petal_path(shape: str, length: Decimal, half: Decimal) -> str:
    """One petal pointing up from the origin (y grows downward in SVG, so the tip is at -length)."""
    L, w = length, half
    p = lambda x, y: f'{fmt(x)},{fmt(y)}'
    if shape == 'round':
        return (f'M0,0 C{p(w, -L * Decimal("0.2"))} {p(w, -L)} {p(0, -L)} '
                f'C{p(-w, -L)} {p(-w, -L * Decimal("0.2"))} 0,0 Z')
    if shape == 'pointed':
        return (f'M0,0 C{p(w, -L * Decimal("0.3"))} {p(w * Decimal("0.6"), -L * Decimal("0.8"))} {p(0, -L)} '
                f'C{p(-w * Decimal("0.6"), -L * Decimal("0.8"))} {p(-w, -L * Decimal("0.3"))} 0,0 Z')
    if shape == 'heart':
        return (f'M0,0 C{p(w * Decimal("1.1"), -L * Decimal("0.25"))} {p(w * Decimal("1.15"), -L)} '
                f'{p(w * Decimal("0.4"), -L)} Q{p(w * Decimal("0.1"), -L)} {p(0, -L * Decimal("0.86"))} '
                f'Q{p(-w * Decimal("0.1"), -L)} {p(-w * Decimal("0.4"), -L)} '
                f'C{p(-w * Decimal("1.15"), -L)} {p(-w * Decimal("1.1"), -L * Decimal("0.25"))} 0,0 Z')
    if shape == 'teardrop':
        return (f'M0,0 C{p(w * Decimal("1.25"), -L * Decimal("0.45"))} {p(w * Decimal("0.5"), -L)} {p(0, -L)} '
                f'C{p(-w * Decimal("0.5"), -L)} {p(-w * Decimal("1.25"), -L * Decimal("0.45"))} 0,0 Z')
    if shape == 'spatula':
        return (f'M0,0 C{p(w * Decimal("0.3"), -L * Decimal("0.4"))} {p(w * Decimal("1.2"), -L * Decimal("0.6"))} '
                f'{p(w, -L * Decimal("0.9"))} Q{p(0, -L * Decimal("1.08"))} {p(-w, -L * Decimal("0.9"))} '
                f'C{p(-w * Decimal("1.2"), -L * Decimal("0.6"))} {p(-w * Decimal("0.3"), -L * Decimal("0.4"))} 0,0 Z')
    if shape == 'fringed':
        teeth = 5
        pts = [f'M0,0 C{p(w, -L * Decimal("0.25"))} {p(w, -L * Decimal("0.7"))} {p(w, -L * Decimal("0.85"))}']
        for i in range(teeth * 2 + 1):
            x = w - (2 * w * i) / (teeth * 2)
            y = -L if i % 2 == 0 else -L * Decimal('0.88')
            pts.append(f'L{p(x, y)}')
        pts.append(f'C{p(-w, -L * Decimal("0.7"))} {p(-w, -L * Decimal("0.25"))} 0,0 Z')
        return ' '.join(pts)
    raise RenderError(f'unknown petal shape {shape!r} (shapes: {", ".join(SHAPES)})', kind='type')


def flower(petals=None, color_=None, center=None, shape=None, layers=None, length=None, width=None,
           rotation=None, leaves=None, stem=None, size=None, background=None, spec=None, **kw):
    """A parametric flower. Every argument is optional; a record can be passed as the first argument or
    as spec= (the fields of a model's FlowerSpec answer)."""
    if isinstance(petals, dict) and spec is None:
        spec, petals = petals, None
    if spec is not None:
        if not isinstance(spec, dict):
            raise RenderError('flower(spec) needs a record', kind='type')
        merged = {k: v for k, v in spec.items()}
        merged.update({k: v for k, v in kw.items()})
        kw = merged
    color_ = kw.pop('color', color_)
    center = kw.pop('center', kw.pop('center_color', center))
    petals = kw.pop('petals', petals)
    shape = kw.pop('shape', kw.pop('petal_shape', shape))
    layers = kw.pop('layers', layers)
    length = kw.pop('length', kw.pop('petal_length', length))
    width = kw.pop('width', kw.pop('petal_width', width))
    rotation = kw.pop('rotation', rotation)
    leaves = kw.pop('leaves', leaves)
    stem = kw.pop('stem', stem)
    size = kw.pop('size', size)
    background = kw.pop('background', background)
    center_size = kw.pop('center_size', None)
    if kw:
        raise RenderError(f'flower has no parameter {sorted(kw)[0]!r}', kind='type')

    n = _int(petals, 'petals', 3, 36, 5)
    nl = _int(layers, 'layers', 1, 4, 1)
    shp = str(shape or 'round').strip().lower()
    if shp not in SHAPES:
        raise RenderError(f'unknown petal shape {shp!r} (shapes: {", ".join(SHAPES)})', kind='type')
    plen = _frac(length, 'length', Fraction(1, 5), 1, 1)
    pwid = _frac(width, 'width', Fraction(1, 10), 1, Fraction(3, 5))
    rot = _frac(rotation, 'rotation', -360, 360, 0)
    nleaves = _int(leaves, 'leaves', 0, 6, 2 if stem is not False else 0)
    has_stem = True if stem is None else bool(stem)
    sz = _int(size, 'size', 120, 1200, 400)
    csize = _frac(center_size, 'center_size', Fraction(1, 10), 1, Fraction(1, 4))
    petal_color = color(color_, 'gold')
    center_color = color(center, 'brown')
    bg = color(background, 'none')

    with localcontext() as ctx:
        ctx.prec = 40
        D = Decimal
        size_d = D(sz)
        cx = size_d / 2
        cy = size_d * (D('0.4') if has_stem else D('0.5'))
        R = size_d * (D('0.3') if has_stem else D('0.42'))
        r0 = R * _dec(csize)                       # centre disc radius
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sz} {sz}" width="{sz}" height="{sz}">']
        if bg != 'none':
            out.append(f'<rect x="0" y="0" width="{sz}" height="{sz}" fill="{bg}"/>')
        if has_stem:
            stem_col = COLORS['leaf']
            bottom = size_d * D('0.97')
            out.append(f'<path d="M{fmt(cx)},{fmt(cy)} Q{fmt(cx - size_d * D("0.06"))},{fmt((cy + bottom) / 2)} '
                       f'{fmt(cx)},{fmt(bottom)}" fill="none" stroke="{stem_col}" stroke-width="{fmt(size_d / 60)}" '
                       f'stroke-linecap="round"/>')
            for i in range(nleaves):
                t = D(i + 1) / D(nleaves + 1)
                ly = cy + (bottom - cy) * (D('0.25') + D('0.6') * t)
                side = 1 if i % 2 == 0 else -1
                ll = size_d * D('0.16')
                lw = size_d * D('0.05')
                ang = 55 * side
                out.append(f'<path d="M0,0 C{fmt(lw)},{fmt(-ll * D("0.3"))} {fmt(lw)},{fmt(-ll * D("0.8"))} 0,{fmt(-ll)} '
                           f'C{fmt(-lw)},{fmt(-ll * D("0.8"))} {fmt(-lw)},{fmt(-ll * D("0.3"))} 0,0 Z" '
                           f'transform="translate({fmt(cx - size_d * D("0.03") * (1 - t))} {fmt(ly)}) rotate({ang})" '
                           f'fill="{shade(stem_col, Fraction(-1, 10))}" stroke="{shade(stem_col, Fraction(1, 4))}" '
                           f'stroke-width="1"/>')
        for layer in range(nl):
            # outer layer first; each inner layer is shorter, offset by half a petal, a little darker
            scale = D(1) - D(layer) * D('0.22')
            plength = (R - r0 * D('0.5')) * _dec(plen) * scale
            half = (D(2) * PI_D() * (r0 + plength * D('0.45')) / D(n)) * _dec(pwid) / 2
            offset = (D(180) / D(n)) * (layer % 2)
            fill = shade(petal_color, Fraction(layer * 12, 100))
            stroke = shade(petal_color, Fraction(30 + layer * 8, 100))
            path = _petal_path(shp, plength, half)
            for i in range(n):
                ang = _dec(rot) + offset + D(360) * D(i) / D(n)
                out.append(f'<path d="{path}" transform="translate({fmt(cx)} {fmt(cy)}) rotate({fmt(ang)}) '
                           f'translate(0 {fmt(-r0 * D("0.5"))})" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
        out.append(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r0)}" fill="{center_color}" '
                   f'stroke="{shade(center_color, Fraction(3, 10))}" stroke-width="1"/>')
        # seeds in a sunflower (Vogel) spiral: radius c*sqrt(k), angle k * golden angle
        dots = max(8, min(144, int(r0 * r0 / 18)))
        c = r0 / D(dots).sqrt() * D('0.92')
        dot_r = max(D('0.8'), r0 / D(28))
        seed_col = shade(center_color, Fraction(-35, 100))
        for k in range(1, dots + 1):
            theta = S.num_to_dec(S.dec_to_num(GOLDEN_ANGLE * k * PI_D() / 180, 20))
            rad = c * D(k).sqrt()
            x = cx + rad * S.dec_cos(theta)
            y = cy + rad * S.dec_sin(theta)
            out.append(f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{fmt(dot_r)}" fill="{seed_col}"/>')
        out.append('</svg>')
    return '\n'.join(out)


def PI_D() -> Decimal:
    return S.PI()


def rose(k=None, color_=None, size=None, **kw):
    """The polar rose r = cos(kθ): k petals when k is odd, 2k when even."""
    color_ = kw.pop('color', color_)
    if kw:
        raise RenderError(f'rose has no parameter {sorted(kw)[0]!r}', kind='type')
    kk = _int(k, 'k', 1, 12, 4)
    sz = _int(size, 'size', 120, 1200, 400)
    col = color(color_, 'rose')
    with localcontext() as ctx:
        ctx.prec = 40
        D = Decimal
        c = D(sz) / 2
        R = D(sz) * D('0.45')
        steps = 360
        turns = 1 if kk % 2 else 2                # odd k closes after π, even after 2π: draw the full curve
        pts = []
        for i in range(steps * turns + 1):
            th = PI_D() * D(i) / D(steps)
            r = R * S.dec_cos(D(kk) * th)
            pts.append(f'{fmt(c + r * S.dec_cos(th))},{fmt(c + r * S.dec_sin(th))}')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sz} {sz}" width="{sz}" height="{sz}">\n'
            f'<path d="M{" L".join(pts)} Z" fill="{shade(col, Fraction(-30, 100))}" stroke="{col}" stroke-width="1.5"/>\n'
            f'</svg>')


def polygon(sides=None, color_=None, size=None, **kw):
    color_ = kw.pop('color', color_)
    if kw:
        raise RenderError(f'polygon has no parameter {sorted(kw)[0]!r}', kind='type')
    n = _int(sides, 'sides', 3, 64, 6)
    sz = _int(size, 'size', 120, 1200, 400)
    col = color(color_, 'orange')
    with localcontext() as ctx:
        ctx.prec = 40
        D = Decimal
        c = D(sz) / 2
        R = D(sz) * D('0.42')
        pts = []
        for i in range(n):
            th = -PI_D() / 2 + 2 * PI_D() * D(i) / D(n)
            pts.append(f'{fmt(c + R * S.dec_cos(th))},{fmt(c + R * S.dec_sin(th))}')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sz} {sz}" width="{sz}" height="{sz}">\n'
            f'<polygon points="{" ".join(pts)}" fill="{col}" stroke="{shade(col, Fraction(3, 10))}" stroke-width="2"/>\n'
            f'</svg>')
