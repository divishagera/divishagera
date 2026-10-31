#!/usr/bin/env python3
"""The Digital Atelier — generates every SVG plate used by README.md.

    python build/build.py           # build from data/ (offline)
    python build/build.py --live    # also pull the contribution calendar + push dates from GitHub
                                    # (needs GITHUB_TOKEN; used by .github/workflows/field-log.yml)

Each plate is written twice: assets/<name>.svg (Direction A, light) and
assets/<name>-dark.svg (Direction B, dark). Fonts are subset per plate and embedded,
so the images render identically on github.com without loading anything external.
"""
import base64, io, json, math, os, random, sys, datetime as dt
from html import escape
from fontTools.ttLib import TTFont
from fontTools import subset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "build", "fonts")
OUT = os.path.join(ROOT, "assets")
DATA = os.path.join(ROOT, "data")
W = 830          # README column width
PAD = 36
COL = 196        # left edge of a work's body column

THEMES = {
    "light": dict(paper="#f2eee5", paper2="#e9e4d8", ink="#16150f", graphite="#6d685d", rule="#cbc3b1", accent="#9a6a1c"),
    "dark":  dict(paper="#141416", paper2="#1b1b1f", ink="#ececec", graphite="#9d9da6", rule="#2c2c33", accent="#b4afc8"),
}
FONTS = {  # key: (file, css family stack)
    "is":  ("is.woff2",  "serif"),
    "isi": ("isi.woff2", "serif"),
    "ar4": ("ar4.woff2", "sans-serif"),
    "ar5": ("ar5.woff2", "sans-serif"),
    "ar8": ("ar8.woff2", "sans-serif"),
    "mo4": ("mo4.woff2", "monospace"),
    "mo5": ("mo5.woff2", "monospace"),
}
_metrics = {}


def metrics(key):
    if key not in _metrics:
        f = TTFont(os.path.join(FONT_DIR, FONTS[key][0]))
        _metrics[key] = (f.getBestCmap(), f["hmtx"].metrics, f["head"].unitsPerEm)
    return _metrics[key]


def tw(text, key, size, ls=0.0):
    cmap, hmtx, upm = metrics(key)
    adv = sum(hmtx.get(cmap.get(ord(c), ".notdef"), (upm // 2, 0))[0] for c in text)
    return adv * size / upm + ls * len(text)


def wrap(text, key, size, width, ls=0.0, first_width=None):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        limit = first_width if (first_width and not lines) else width
        if tw(trial, key, size, ls) <= limit or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


class SVG:
    """Collects markup + the characters used per font, then emits a self-contained SVG."""

    def __init__(self, T, h, label):
        self.T, self.h, self.label, self.parts, self.used, self.css = T, h, label, [], {}, []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, font="mo4", size=11, fill="ink", anchor="start", ls=0.0, upper=False, extra="", cls=""):
        s = s.upper() if upper else s
        self.used.setdefault(font, set()).update(s)
        col = self.T.get(fill, fill)
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        l = f' letter-spacing="{ls:g}"' if ls else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" class="{font}{" " + cls if cls else ""}" font-size="{size}" fill="{col}"{a}{l}{extra}>{escape(s)}</text>')

    def rich(self, x, y, runs, font, size, fill="ink", extra=""):
        """runs: list of (text, colorKey) on one line."""
        spans = []
        for t, c in runs:
            self.used.setdefault(font, set()).update(t)
            spans.append(f'<tspan fill="{self.T.get(c, c)}">{escape(t)}</tspan>')
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" class="{font}" font-size="{size}" fill="{self.T[fill]}"{extra}>{"".join(spans)}</text>')

    def mono(self, x, y, s, size=10, fill="graphite", anchor="start", weight=4):
        self.text(x, y, s, f"mo{weight}", size, fill, anchor, ls=round(size * 0.06, 2), upper=True)

    def line(self, x1, y1, x2, y2, c="rule", w=1, extra=""):
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{self.T.get(c, c)}" stroke-width="{w}"{extra}/>')

    def rect(self, x, y, w, h, fill="none", stroke=None, sw=1, extra=""):
        s = f' stroke="{self.T.get(stroke, stroke)}" stroke-width="{sw}"' if stroke else ""
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{self.T.get(fill, fill)}"{s}{extra}/>')

    def fontface(self):
        out = []
        for key, chars in self.used.items():
            chars = set(chars) | {" "}
            f = TTFont(os.path.join(FONT_DIR, FONTS[key][0]))
            opts = subset.Options()
            opts.flavor = "woff2"
            opts.layout_features = ["kern", "liga", "calt"]
            opts.name_IDs = []
            opts.notdef_outline = True
            sub = subset.Subsetter(opts)
            sub.populate(unicodes=[ord(c) for c in chars])
            sub.subset(f)
            buf = io.BytesIO()
            f.flavor = "woff2"
            f.save(buf)
            b64 = base64.b64encode(buf.getvalue()).decode()
            out.append(f'@font-face{{font-family:"{key}";src:url(data:font/woff2;base64,{b64}) format("woff2")}}'
                       f'.{key}{{font-family:"{key}",{FONTS[key][1]}}}')
        return "".join(out)

    def render(self):
        T = self.T
        css = self.fontface() + "".join(self.css) + \
            "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        frame = (f'<rect x="0.5" y="0.5" width="{W-1}" height="{self.h-1}" fill="{T["paper"]}" stroke="{T["rule"]}"/>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{self.h}" viewBox="0 0 {W} {self.h}" '
                f'role="img" aria-label="{escape(self.label)}"><title>{escape(self.label)}</title>'
                f'<style>{css}</style>{frame}{"".join(self.parts)}</svg>')


def sec_head(g, y, num, title_runs, right):
    g.mono(PAD, y, num, 11)
    g.rich(106, y + 2, title_runs, "is", 34)
    g.mono(W - PAD, y, right, 11, anchor="end")


# ───────────────────────────── plates ─────────────────────────────

def plate_cover(T):
    g = SVG(T, 610, "Divisha Gera — The Digital Atelier. An ongoing study of systems, signals and things worth building.")
    g.mono(PAD, 44, "Vol. 03 · Issue 05", 11)
    g.text(W / 2, 44, "THE DIGITAL ATELIER", "ar8", 11, anchor="middle", ls=4.6)
    g.mono(W - PAD, 44, "Bengaluru · 2026", 11, anchor="end")
    g.line(PAD, 58, W - PAD, 58, "ink", 2)

    # name, rising out of two clipped slots
    g.css.append(".rise{animation:rise 1.2s cubic-bezier(.2,.7,.1,1) both}.rise2{animation-delay:.18s}"
                 "@keyframes rise{from{transform:translateY(140px)}}")
    g.add('<defs><clipPath id="n1"><rect x="0" y="66" width="830" height="146"/></clipPath>'
          '<clipPath id="n2"><rect x="0" y="212" width="830" height="130"/></clipPath></defs>')
    g.add('<g clip-path="url(#n1)">')
    g.text(PAD - 4, 200, "Divisha", "is", 152, ls=-5.3, cls="rise")
    g.add('</g><g clip-path="url(#n2)">')
    gx = 172
    g.text(gx, 322, "Gera", "isi", 152, ls=-5.3, cls="rise rise2")
    g.add('</g>')
    g.text(gx + tw("Gera", "isi", 152, -5.3) + 14, 254, "AI / ML · SYSTEMS", "mo5", 11, "accent", ls=0.7)

    # spike raster, scrolling
    rx, ry, rw, rh, n = PAD, 360, 434, 92, 16
    rowh = rh / n
    for i in range(n + 1):
        g.line(rx, ry + i * rowh, rx + rw, ry + i * rowh, "rule", 0.6, ' opacity=".55"')
    rnd = random.Random(7)
    ticks_ink, ticks_acc = [], []
    for i in range(n):
        rate = 0.016 + 0.05 * abs(math.sin(i * 1.7))
        x = rnd.random() * 20
        while x < rw:
            burst = 2.6 if math.sin(x * 0.03 + i * 0.4) > 0.6 else 1
            x += rnd.expovariate(rate * burst)
            if x >= rw:
                break
            d = f"M{x:.1f} {ry + i*rowh + 1.5:.1f}v{rowh - 3:.2f}"
            (ticks_acc if i in (5, 11) else ticks_ink).append(d)
    g.css.append(".scroll{animation:scroll 22s linear infinite}@keyframes scroll{to{transform:translateX(-434px)}}")
    g.add(f'<defs><clipPath id="rc"><rect x="{rx}" y="{ry}" width="{rw}" height="{rh}"/></clipPath></defs>')
    tile = (f'<path d="{"".join(ticks_ink)}" stroke="{T["ink"]}" stroke-width="1.6"/>'
            f'<path d="{"".join(ticks_acc)}" stroke="{T["accent"]}" stroke-width="1.6"/>')
    g.add(f'<g clip-path="url(#rc)"><g class="scroll"><g transform="translate({rx},0)">{tile}</g>'
          f'<g transform="translate({rx + rw},0)">{tile}</g></g></g>')
    g.mono(rx, ry + rh + 20, "fig. 0 — spike raster, 16 units", 10)
    g.mono(rx + rw, ry + rh + 20, "t →", 10, anchor="end")

    # lede
    lx, lw = 496, W - PAD - 496
    words = "An ongoing study of systems, signals and things worth building.".split()
    acc_from = words.index("things")
    lines = wrap(" ".join(words), "isi", 26, lw)
    k = 0
    base = ry + rh + 20 - (len(lines) - 1) * 29
    for li, l in enumerate(lines):
        runs = []
        for wd in l.split():
            runs.append((wd + " ", "accent" if k >= acc_from else "ink"))
            k += 1
        g.rich(lx, base + li * 29, runs, "isi", 26)

    # colophon strip
    y0 = 496
    g.line(PAD, y0, W - PAD, y0, "rule")
    cols = [("Location", ["12.97° N, 77.59° E", "Bengaluru, IN"]),
            ("Study", ["B.E. AI & ML, 3rd year", "MS Ramaiah Inst. of Tech."]),
            ("On the bench", ["ReTrace for SIH 2026", "An ICEE 2026 paper"]),
            ("Status", ["Open to internships", ""])]
    cw = (W - 2 * PAD) / 4
    for i, (lab, vals) in enumerate(cols):
        x = PAD + i * cw
        g.mono(x, y0 + 22, lab, 10)
        for j, v in enumerate(vals):
            if not v:
                continue
            if lab == "Status":
                g.css.append(".pulse{animation:pulse 2.4s ease-in-out infinite}@keyframes pulse{50%{opacity:.25}}")
                g.add(f'<circle class="pulse" cx="{x + 4}" cy="{y0 + 40}" r="4" fill="{T["accent"]}"/>')
                g.text(x + 14, y0 + 44, v, "ar4", 13)
            else:
                g.text(x, y0 + 44 + j * 18, v, "ar4", 13)
    toc = [("i", "Foreword"), ("ii", "Catalogue of works"), ("iii", "Paper"), ("iv", "Instruments"),
           ("v", "Field log"), ("vi", "Colophon")]
    x = PAD
    for num, name in toc:
        g.text(x, 584, num.upper(), "mo5", 10.5, "ink", ls=0.6)
        x += tw(num.upper(), "mo5", 10.5, 0.6) + 6
        g.text(x, 584, name.upper(), "mo4", 10.5, "graphite", ls=0.6)
        x += tw(name.upper(), "mo4", 10.5, 0.6) + 22
    return g


def plate_foreword(T):
    g = SVG(T, 0, "Foreword — about Divisha")
    sec_head(g, 66, "i.", [("Foreword", "ink")], "p. 02")
    # aside
    ay = 112
    for lab, val in [("Subject", "Engineering × mathematics"), ("Method", "Take it apart, then build"),
                     ("Also", "Vice Chair, IEEE CIS student chapter, MSRIT")]:
        g.mono(PAD, ay, lab, 10, "ink", 5)
        for i, l in enumerate(wrap(val.upper(), "mo4", 10, 128, 0.6)):
            g.text(PAD, ay + 16 + i * 15, l, "mo4", 10, "graphite", ls=0.6)
            last = ay + 16 + i * 15
        ay = last + 30
    bx, bw, lh = 214, W - PAD - 214, 25
    paras = ["I study artificial intelligence and machine learning in Bengaluru. Most of what I make sits where "
             "engineering meets mathematics: small models, signal processing, data pipelines, and the systems "
             "that hold them together.",
             "I care about how things work down to the part people usually skip, whether that is an OS scheduler, "
             "a parallel loop or a spiking neuron. Then I try to build something that solves a problem a real "
             "person has."]
    y = 120
    # drop cap
    g.text(bx - 2, y + 30, "I", "is", 72, "accent")
    first = paras[0][2:]
    lines = []
    cur, n = "", 0
    for word in first.split():
        limit = bw - 40 if len(lines) < 2 else bw
        trial = (cur + " " + word).strip()
        if tw(trial, "ar4", 16) <= limit or not cur:
            cur = trial
        else:
            lines.append(cur); cur = word
    lines.append(cur)
    for i, l in enumerate(lines):
        g.text(bx + (36 if i < 2 else 0), y + i * lh, l, "ar4", 16)
    y += len(lines) * lh + 12
    for l in wrap(paras[1], "ar4", 16, bw):
        g.text(bx, y, l, "ar4", 16); y += lh
    y += 14
    q = wrap("Systems engineering, parallel computing and software are where I spend my time. "
             "AI and ML are what I am still learning to do well.", "isi", 21, bw - 30)
    g.line(bx + 1, y - 18, bx + 1, y + (len(q) - 1) * 26 + 8, "accent", 2)
    for i, l in enumerate(q):
        g.text(bx + 16, y + i * 26, l, "isi", 21)
    end = max(y + (len(q) - 1) * 26 + 34, ay)
    g.line(186, 100, 186, end - 20, "rule")
    g.h = end
    return g


def plate_catalogue_head(T):
    g = SVG(T, 104, "Catalogue of works")
    sec_head(g, 62, "ii.", [("Catalogue of ", "ink"), ("works", "accent")], "6 works · 2025–26")
    g.line(PAD, 88, W - PAD, 88, "ink", 2)
    return g


# ── figures for works: each returns height, draws into g at (x, y, w)

def fig_nse(g, x, y, w):
    T = g.T
    rows = [("a", "top-gainers-losers", 248, "OK"), ("b", "upper-band-hitters", 106, "OK · 1W"),
            ("c", "volume-gainers", 25, "OK"), ("d", "52-week-high", 60, "OK")]
    cx = [x + 20, x + 44, x + 206, x + w - 130, x + w - 76]
    g.mono(cx[0], y + 30, "#", 9.5); g.mono(cx[1], y + 30, "Dataset", 9.5); g.mono(cx[2], y + 30, "Rows", 9.5)
    g.mono(cx[3], y + 30, "n", 9.5); g.mono(cx[4], y + 30, "Status", 9.5)
    g.line(x + 20, y + 40, x + w - 20, y + 40, "rule", 1, ' stroke-dasharray="1 3"')
    g.css.append(".grow{transform-box:fill-box;transform-origin:left;animation:grow 1.6s cubic-bezier(.2,.7,.1,1) both}"
                 "@keyframes grow{from{transform:scaleX(0)}}")
    bw = cx[3] - cx[2] - 24
    for i, (k, name, n, st) in enumerate(rows):
        yy = y + 64 + i * 32
        g.text(cx[0], yy, k, "mo4", 12)
        g.text(cx[1], yy, name, "mo4", 12)
        g.rect(cx[2], yy - 9, bw * n / 248, 8, "ink", extra=f' class="grow" style="animation-delay:{.15*i:.2f}s"')
        g.text(cx[3], yy, str(n), "mo4", 12)
        g.text(cx[4], yy, st, "mo4", 12, "accent")
        g.line(x + 20, yy + 13, x + w - 20, yy + 13, "rule", 1, ' stroke-dasharray="1 3"')
    fy = y + 64 + 4 * 32 + 14
    lab = "RECONCILIATION"
    lw = tw(lab, "mo4", 10.5, .6) + 14
    g.rect(x + 20, fy - 6, lw, 22, stroke="accent")
    g.text(x + 27, fy + 9, lab, "mo4", 10.5, "accent", ls=.6)
    for i, l in enumerate(wrap("NSE's page header says 107. The table holds 106. The pipeline caught it.",
                               "mo4", 11.5, w - lw - 50)):
        g.text(x + 32 + lw, fy + 9 + i * 17, l, "mo4", 11.5)
    return fy + 40 - y


def fig_ecg(g, x, y, w):
    T, h = g.T, 200
    for gx in range(0, int(w), 20):
        g.line(x + gx + .5, y, x + gx + .5, y + h, "rule", 1, f' opacity="{.9 if gx % 100 == 0 else .4}"')
    beat = w / 4
    def v(t):
        p = t % 1
        G = lambda m, s, a: a * math.exp(-((p - m) ** 2) / (2 * s * s))
        return G(.18, .025, .12) - G(.37, .008, .12) + G(.4, .011, 1) - G(.43, .009, .25) + G(.68, .04, .28)
    base, amp = y + 104, 72
    pts, on, off, prev = [], [], [], 0
    for px in range(0, int(2 * w) + 1):
        t = px / beat
        val = v(t + .07 * math.sin((math.floor(t) % 4) * 2.1))
        pts.append(f"{px:.0f} {base - val * amp:.1f}")
        d = val - prev
        if abs(d) > .045 and px > 0:
            (on if d > 0 else off).append(f"M{px} {y + h - 43}v14" if d > 0 else f"M{px} {y + h - 25}v14")
        prev = val
    g.add(f'<defs><clipPath id="ec"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath></defs>')
    g.css.append(f".ecg{{animation:ecg 9s linear infinite}}@keyframes ecg{{to{{transform:translateX(-{w:.1f}px)}}}}")
    g.line(x, y + h - 36 + .5, x + w, y + h - 36 + .5, "rule")
    g.line(x, y + h - 18 + .5, x + w, y + h - 18 + .5, "rule")
    g.add(f'<g clip-path="url(#ec)"><g class="ecg"><g transform="translate({x},0)">'
          f'<path d="M{" L".join(pts)}" fill="none" stroke="{T["ink"]}" stroke-width="1.5"/>'
          f'<path d="{"".join(on)}" stroke="{T["accent"]}" stroke-width="1.6"/>'
          f'<path d="{"".join(off)}" stroke="{T["ink"]}" stroke-width="1.6"/></g></g></g>')
    g.mono(x + 10, y + 16, "Lead II · mV", 9)
    g.mono(x + 10, y + h - 50, "Delta encoder → on / off", 9)
    return h


def fig_sayonara(g, x, y, w):
    T = g.T
    cols, rows, gap = 48, 8, 2
    cs = (w - 40 - gap * (cols - 1)) / cols
    P, hold = 4.0, 3.0
    total = 3 * P + hold
    f = lambda t: f"{100 * t / total:.2f}%"
    g.css.append(
        f".s{{animation:wipe {total}s linear infinite}}"
        f"@keyframes wipe{{0%{{fill:{T['rule']}}}0.01%{{fill:{T['paper']};opacity:1}}"
        f"{f(P)}{{fill:{T['paper']};opacity:1}}{f(P+.01)}{{fill:{T['ink']};opacity:1}}"
        f"{f(2*P)}{{fill:{T['ink']};opacity:1}}{f(2*P+.01)}{{fill:{T['accent']};opacity:1}}"
        f"{f(3*P)}{{fill:{T['accent']};opacity:1}}100%{{fill:{T['accent']};opacity:1}}}}")
    rnd = random.Random(3)
    cells = []
    for i in range(cols * rows):
        r, c = divmod(i, cols)
        d = P * i / (cols * rows)
        cells.append(f'<rect class="s" x="{x + 20 + c * (cs + gap):.1f}" y="{y + 18 + r * (cs + gap):.1f}" '
                     f'width="{cs:.1f}" height="{cs:.1f}" fill="{T["rule"]}" opacity="{.35 + .65 * rnd.random():.2f}" '
                     f'style="animation-delay:{d:.3f}s"/>')
    g.add("".join(cells))
    ly = y + 18 + rows * (cs + gap) + 22
    labels = [("Pass 1 · 0x00", "paper", 0), ("Pass 2 · 0xFF", "ink", 1), ("Pass 3 · random", "accent", 2),
              ("Verify · entropy check", None, 3)]
    lx = x + 20
    for i, (lab, col, k) in enumerate(labels):
        a, b = (k * P, (k + 1) * P) if k < 3 else (3 * P, total)
        g.css.append(f".L{k}{{animation:L{k} {total}s linear infinite}}@keyframes L{k}{{0%,{f(a)}{{opacity:.45}}"
                     f"{f(a+.01)},{f(b)}{{opacity:1}}{f(b+.01)},100%{{opacity:.45}}}}")
        g.add(f'<g class="L{k}">')
        if col:
            g.rect(lx, ly - 9, 9, 9, col, stroke="accent" if col == "accent" else "ink")
        else:
            g.rect(lx, ly - 9, 9, 9, stroke="ink")
        g.text(lx + 15, ly, lab.upper(), "mo4", 10, "ink", ls=.5)
        g.add("</g>")
        lx += 15 + tw(lab.upper(), "mo4", 10, .5) + 22
    return ly + 16 - y


def fig_radcloud(g, x, y, w):
    T, h = g.T, 200
    for yy in (38, 100, 162):
        g.line(x, y + yy, x + w, y + yy, "rule")
    g.mono(x + 14, y + 26, "In · Terraform + billing CSV", 9)
    names = ["Discovery", "Mapping", "Risk", "FinOps", "Watchdog"]
    bw, gap = 96, (w - 28 - 5 * 96) / 4
    g.css.append(".flow{stroke-dasharray:4 5;animation:flow 1.2s linear infinite}@keyframes flow{to{stroke-dashoffset:-18}}")
    for i, nm in enumerate(names):
        bx = x + 14 + i * (bw + gap)
        last = i == 4
        g.line(bx + bw / 2, y + 38, bx + bw / 2, y + 68, "rule")
        if i < 4:
            g.line(bx + bw, y + 100, bx + bw + gap, y + 100, "accent", 1.5, ' class="flow"')
        g.rect(bx, y + 68, bw, 64, "ink" if last else "paper", stroke="ink")
        g.mono(bx + 9, y + 86, f"A{i+1}", 9, "paper" if last else "graphite")
        g.text(bx + 9, y + 118, nm.upper(), "mo5", 11.5, "paper" if last else "ink", ls=.8)
    lb = x + 14 + 4 * (bw + gap)
    for k in range(3):
        cx = lb + 18 + k * 30
        g.line(cx, y + 132, cx, y + 162, "ink")
        g.add(f'<circle cx="{cx}" cy="{y + 162}" r="3" fill="{T["accent"]}"/>')
    g.mono(x + 14, y + 186, "Out · runbook · watchdog · iac_bundle", 9)
    return h


def fig_retrace(g, x, y, w):
    import numpy as np, contourpy
    T, h = g.T, 260
    hills = [(.22, .35, .28, 1), (.62, .6, .24, .9), (.85, .2, .18, .6), (.45, .9, .2, .5)]
    u = np.linspace(0, 1, 150); v = np.linspace(0, 1, 66)
    U, V = np.meshgrid(u, v)
    Z = sum(k * np.exp(-((U - cx) ** 2 + (V - cy) ** 2 * 1.6) / (2 * r * r)) for cx, cy, r, k in hills)
    Z = Z + .05 * np.sin(U * 14) * np.cos(V * 11)
    gen = contourpy.contour_generator(U * w + x, V * h + y, Z)
    minor, major = [], []
    for L in range(1, 15):
        for seg in gen.lines(L * .075):
            d = "M" + "L".join(f"{p[0]:.1f} {p[1]:.1f}" for p in seg[::2])
            (major if L % 5 == 0 else minor).append(d)
    g.add(f'<defs><clipPath id="tc"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath></defs><g clip-path="url(#tc)">'
          f'<path d="{"".join(minor)}" fill="none" stroke="{T["rule"]}" stroke-width=".8"/>'
          f'<path d="{"".join(major)}" fill="none" stroke="{T["graphite"]}" stroke-width=".8"/></g>')
    for i in range(1, 6):
        g.mono(x + i * w / 6, y + h - 8, f"77.{590 + i*2}°E", 8.5, anchor="middle")
    g.mono(x + 8, y + 16, "12.981°N", 8.5); g.mono(x + 8, y + h - 22, "12.962°N", 8.5)
    tp = lambda t: (.06 + .88 * t, .55 + .22 * math.sin(t * 6.3) - .12 * t)
    true_pts, est_pts = [], []
    for i in range(0, 251):
        t = i / 250
        a, b = tp(t)
        true_pts.append(f"{x + a*w:.1f} {y + b*h:.1f}")
        du, dv = .018 * t * t * math.sin(t * 3), .06 * t * t
        est_pts.append(f"{x + (a+du)*w:.1f} {y + (b+dv)*h:.1f}")
    g.add(f'<defs><clipPath id="rv"><rect x="{x}" y="{y}" width="0" height="{h}">'
          f'<animate attributeName="width" values="0;{w};{w}" keyTimes="0;.8;1" dur="9s" repeatCount="indefinite"/>'
          f'</rect></clipPath></defs><g clip-path="url(#rv)">'
          f'<path d="M{" L".join(true_pts)}" fill="none" stroke="{T["ink"]}" stroke-width="2"/>'
          f'<path d="M{" L".join(est_pts)}" fill="none" stroke="{T["accent"]}" stroke-width="1.6" stroke-dasharray="5 4"/></g>')
    a, b = tp(0)
    g.rect(x + a * w - 4, y + b * h - 4, 8, 8, stroke="ink")
    a, b = tp(1)
    ex, ey = x + a * w, y + b * h
    g.add(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="{T["ink"]}"/>')
    g.rect(ex - 104, ey - 24, 94, 16, "paper")
    g.text(ex - 100, ey - 12, "GNSS: NO FIX", "mo4", 9.5, "ink", ls=.4)
    return h


def fig_orbit(g, x, y, w):
    T, h = g.T, 290
    cx, cy = x + w / 2, y + 145
    g.add(f'<ellipse cx="{cx}" cy="{cy}" rx="96" ry="96" fill="none" stroke="{T["rule"]}"/>')
    g.css.append(".orb{stroke-dasharray:2 6;animation:orb 6s linear infinite}@keyframes orb{to{stroke-dashoffset:-80}}")
    g.add(f'<ellipse class="orb" cx="{cx}" cy="{cy}" rx="170" ry="114" fill="none" stroke="{T["graphite"]}"/>')
    outer = f"M{cx-262} {cy}a262 128 0 1 0 524 0a262 128 0 1 0 -524 0"
    g.add(f'<path d="{outer}" fill="none" stroke="{T["rule"]}"/>')
    g.add(f'<circle r="3.5" fill="{T["ink"]}"><animateMotion dur="24s" repeatCount="indefinite" path="{outer}"/></circle>')
    g.add(f'<circle cx="{cx}" cy="{cy}" r="40" fill="{T["ink"]}"/>')
    g.text(cx, cy + 4, "HOME", "mo5", 10, "paper", "middle", ls=1.5)
    for nm, rx, ry, ang in [("Tasks", 96, 96, -.5), ("Roadmaps", 96, 96, 2.4), ("Expenses", 262, 128, .35), ("Nutrition", 262, 128, 3.6)]:
        px, py = cx + rx * math.cos(ang), cy + ry * math.sin(ang)
        g.add(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{T["accent"]}"/>')
        g.text(px + (10 if math.cos(ang) >= 0 else -10), py + 4, nm.upper(), "mo5", 10.5, "ink",
               "start" if math.cos(ang) >= 0 else "end", ls=1)
    g.mono(x + 14, y + h - 12, "Class hours → tasks only", 8.5)
    g.mono(x + w - 14, y + h - 12, "Commute 10 min", 8.5, anchor="end")
    return h


WORKS = [
    dict(slug="01-nse", no="01", role=["Solo", "Oct 2026"], title="NSE Market Data",
         line="A config-driven pipeline that writes four clean, validated CSVs for every NSE trading day.",
         meta=[("Field", "Data engineering"), ("Stack", "Python · requests · PyYAML · SQLite · Docker"),
               ("Proof", "135 tests · 90% branch coverage"), ("Repo", ("nse-market-data-", "downloader ↗"))],
         fig=fig_nse, cap=("fig. 1 — live run, 30-Oct-2026 15:30 IST, final snapshot", "4 / 4 datasets")),
    dict(slug="02-cortexcore", no="02", role=["Team", "2025"], title="CortexCore",
         line="A spiking neural network that reads ECG signals and flags irregular heart rhythms.",
         meta=[("Field", "Neuromorphic ML · biosignals"), ("Stack", "Python · PyTorch · snnTorch"),
               ("Result", "G-mean 88.16% (team README)"), ("Repo", "Private, team-owned")],
         fig=fig_ecg, cap=("fig. 2 — ECG trace (top) encoded as spike events (bottom)", "illustrative signal")),
    dict(slug="03-sayonara", no="03", role=["Team", "SIH 2025"], title="Sayonara",
         line="Secure, verifiable data wiping for HDD, SSD and NVMe drives, with signed wipe certificates.",
         meta=[("Field", "Systems · security"), ("Stack", "Rust · TypeScript · bootable Linux"),
               ("Methods", "DoD 5220.22-M · Gutmann · NVMe sanitize"), ("Repo", "Sayonara ↗")],
         fig=fig_sayonara, cap=("fig. 3 — a DoD 3-pass wipe sweeping 384 sectors", "15 s loop")),
    dict(slug="04-radcloud", no="04", role=["Team", "Apr 2026"], title="RadCloud",
         line="LLM agents that read cloud configs and billing data to find waste and migration risk.",
         meta=[("Field", "Agents · FinOps"), ("Stack", "FastAPI · AWS Bedrock · React · Vite · Tailwind"),
               ("Repo", ("Ryan-gomezzz/", "Radcloud ↗"))],
         fig=fig_radcloud, cap=("fig. 4 — five-agent orchestration, each stage an LLM call", "Claude via Bedrock")),
    dict(slug="05-retrace", no="05", role=["Team Sin-Tax", "SIH 2026"], title="ReTrace",
         line="An Android dead-reckoning app that keeps tracking position where GNSS cannot reach.",
         meta=[("Field", "Navigation · sensor fusion"), ("Brief", "ISRO, PS SIH26168"), ("Stack", "Android · AI/ML"),
               ("Status", "In progress")],
         fig=fig_retrace, cap=("fig. 5 — true path (solid) against dead-reckoned estimate (dashed)", "illustrative")),
    dict(slug="06-orbit", no="06", role=["Solo", "2026"], title="Orbit",
         line="A personal operating system for the week, built around one rule: nothing gets scheduled during class.",
         meta=[("Field", "Product · personal tools"), ("Stack", "React · PWA · Netlify"), ("Repo", "Private")],
         fig=fig_orbit, cap=("fig. 6 — Home at the centre, four sections in orbit", "iOS-first")),
]


def plate_work(T, wk):
    g = SVG(T, 0, f'{wk["no"]} {wk["title"]} — {wk["line"]}')
    top = 30
    g.text(PAD - 2, top + 54, wk["no"], "is", 66, ls=-2)
    for i, r in enumerate(wk["role"]):
        g.mono(PAD, top + 82 + i * 14, r, 9.5)
    g.text(COL, top + 32, wk["title"].upper(), "ar8", 29, ls=-.7)
    ly = top + 68
    for i, l in enumerate(wrap(wk["line"], "isi", 21, 360)):
        g.text(COL, ly + i * 25, l, "isi", 21)
    line_end = ly + i * 25
    mx = 600
    my = top + 12
    for lab, val in wk["meta"]:
        g.mono(mx, my, lab, 9.5)
        lines = list(val) if isinstance(val, tuple) else wrap(val, "ar4", 12.5, W - PAD - mx - 52)
        link = lines[-1].endswith("↗") or lab == "Status"
        for j, l in enumerate(lines):
            g.text(mx + 52, my + j * 16, l, "ar4", 12.5, "accent" if link else "ink")
            if link:
                g.line(mx + 52, my + j * 16 + 4, mx + 52 + tw(l, "ar4", 12.5), my + j * 16 + 4, "accent")
        my += j * 16 + 22
    g.line(mx - 14, top, mx - 14, my - 14, "rule")
    fy = max(line_end + 26, my)
    fx, fw = COL, W - PAD - COL
    g.rect(fx, fy, fw, 10, "paper2", extra=' id="figbg"')  # placeholder, resized below
    idx = len(g.parts) - 1
    fh = wk["fig"](g, fx, fy, fw)
    g.parts[idx] = f'<rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" fill="{T["paper2"]}" stroke="{T["rule"]}"/>'
    g.mono(fx, fy + fh + 18, wk["cap"][0], 9.5)
    g.mono(W - PAD, fy + fh + 18, wk["cap"][1], 9.5, anchor="end")
    g.h = fy + fh + 40
    return g


def plate_paper(T):
    g = SVG(T, 0, "Paper — Feed-Forward Spiking Networks Obey a Friis-Type Cascade Law. ICEE 2026.")
    sec_head(g, 66, "iii.", [("Paper", "ink")], "ICEE 2026 · Dec")
    y = 124
    for l in wrap("Feed-Forward Spiking Networks Obey a Friis-Type Cascade Law", "is", 28, 520):
        g.text(PAD, y, l, "is", 28); y += 31
    for l in wrap("Fidelity ceilings and a fan-in design rule for biosignal processing", "isi", 20, 640):
        g.text(PAD, y + 2, l, "isi", 20, "graphite"); y += 24
    fx, fy, fw, fh = PAD, y + 12, W - 2 * PAD, 236
    g.rect(fx, fy, fw, fh, "paper2", "rule")
    Y = lambda val: fy + 196 - (val - .6) * 380
    g.line(fx + 16, Y(.775), fx + fw - 16, Y(.775), "accent", 1, ' stroke-dasharray="3 4"')
    g.mono(fx + fw - 18, Y(.775) - 8, "Fidelity ceiling", 9, "accent", "end")
    g.mono(fx + 16, fy + 20, "Signal fidelity ↓   depth →", 9)
    g.mono(fx + fw - 18, fy + 20, "Early layers dominate · fan-in sets the loss per stage", 9, anchor="end")
    f, pts = 1.0, []
    for i in range(7):
        pts.append((fx + 40 + i * 112, f))
        f = .78 + (f - .78) * .45 - .005 * i
    for i in range(6):
        bx = fx + 40 + i * 112 + 26
        g.rect(bx, fy + 202, 60, 22, "ink" if i == 0 else "none", stroke="ink")
        g.text(bx + 30, fy + 217, f"L{i+1}", "mo4", 9.5, "paper" if i == 0 else "ink", "middle")
    d = "M" + " L".join(f"{px:.1f} {Y(v):.1f}" for px, v in pts)
    g.add(f'<path d="{d}" fill="none" stroke="{T["ink"]}" stroke-width="1.6" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1">'
          f'<animate attributeName="stroke-dashoffset" values="1;0;0" keyTimes="0;.45;1" dur="6s" repeatCount="indefinite"/></path>')
    for px, v in pts:
        g.add(f'<circle cx="{px:.1f}" cy="{Y(v):.1f}" r="3.5" fill="{T["paper"]}" stroke="{T["ink"]}"/>')
    g.mono(pts[0][0] + 10, Y(1) + 4, "Input", 9)
    g.mono(PAD, fy + fh + 18, "fig. 7 — schematic: as with noise in Friis's chain of amplifiers, early stages set the ceiling", 9.5)
    g.mono(W - PAD, fy + fh + 36, "Presenting author · Dec 2026", 9.5, anchor="end")
    g.h = fy + fh + 58
    return g


def plate_instruments(T):
    g = SVG(T, 0, "Instruments — computing, development, exploration")
    sec_head(g, 66, "iv.", [("Instruments", "ink")], "no badges")
    groups = [("COMPUTING", ["Data structures & algorithms", "Object-oriented programming", "Operating systems",
                             "Database systems", "Computer networks"]),
              ("DEVELOPMENT", ["C++", "Python", "JavaScript", "TypeScript", "React", "SQL"]),
              ("EXPLORATION", ["Artificial intelligence", "Machine learning", "Parallel computing",
                               "Systems engineering", "Product development"])]
    cw = (W - 2 * PAD) / 3
    bottom = 0
    for gi, (head, items) in enumerate(groups):
        x = PAD + gi * cw + (18 if gi else 0)
        if gi:
            g.line(PAD + gi * cw, 104, PAD + gi * cw, 330, "rule")
        g.text(x, 118, head, "ar8", 11.5, ls=3.6)
        y = 134
        for k, it in enumerate(items):
            g.line(x, y, x + cw - 36, y, "rule")
            g.mono(x, y + 20, f"{k+1:02d}", 9.5)
            ls = wrap(it, "is", 20, cw - 70)
            for j, l in enumerate(ls):
                g.text(x + 28, y + 24 + j * 22, l, "is", 20)
            y += 14 + len(ls) * 22 + 4
        bottom = max(bottom, y)
    g.h = bottom + 30
    return g


def plate_fieldlog(T, repos, cal):
    g = SVG(T, 0, "Field log — contribution calendar and repository timeline")
    end = dt.date.fromisoformat(cal["end"]) if cal else dt.date.today()
    start = end - dt.timedelta(days=364)
    while start.weekday() != 6:
        start -= dt.timedelta(days=1)
    sec_head(g, 66, "v.", [("Field ", "ink"), ("log", "accent")],
             f'{start.strftime("%b %Y")} → {end.strftime("%b %Y")}')
    live = bool(cal and cal.get("days"))
    left = "Contribution calendar · restyled"
    right = (f'{cal["total"]} contributions in the last year' if live else "■ verified push")
    g.mono(PAD, 104, left, 9.5)
    g.mono(W - PAD, 104, right, 9.5, anchor="end")
    cell = (W - 2 * PAD) / 53
    days = cal["days"] if live else {}
    pushes = {r["pushed"] for r in repos}
    mx = max(days.values()) if days else 1
    d, i, months = start, 0, []
    rects = []
    while d <= end:
        wk, wd = divmod(i, 7)
        k = d.isoformat()
        cx, cy = PAD + wk * cell, 116 + wd * cell
        if live:
            n = days.get(k, 0)
            if n:
                lvl = min(4, 1 + int(3 * n / mx)) if mx > 1 else 4
                rects.append(f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{cell-2:.1f}" height="{cell-2:.1f}" fill="{T["accent"]}" opacity="{.25*lvl:.2f}"/>')
            else:
                rects.append(f'<rect x="{cx+.5:.1f}" y="{cy+.5:.1f}" width="{cell-3:.1f}" height="{cell-3:.1f}" fill="{T["paper2"]}" stroke="{T["rule"]}"/>')
        else:
            on = k in pushes
            rects.append(f'<rect x="{cx+.5:.1f}" y="{cy+.5:.1f}" width="{cell-3:.1f}" height="{cell-3:.1f}" '
                         f'fill="{T["accent"] if on else T["paper2"]}" stroke="{T["accent"] if on else T["rule"]}"/>')
        if d.day <= 7 and wd == 0:
            months.append((wk, d.strftime("%b")))
        d += dt.timedelta(days=1); i += 1
    g.add("".join(rects))
    for wk, m in months:
        g.mono(PAD + wk * cell, 116 + 7 * cell + 14, m, 9)
    note = ("Live from GitHub, refreshed daily." if live else
            "Showing verified push dates only until the daily workflow runs.")
    g.text(PAD, 116 + 7 * cell + 34, note, "mo4", 10, "graphite")

    # timeline
    ty = 116 + 7 * cell + 106
    t0, t1 = dt.date(2025, 5, 1), dt.date(end.year + (end.month == 12), end.month % 12 + 1, 1)
    X = lambda s: PAD + (dt.date.fromisoformat(s) - t0).days / (t1 - t0).days * (W - 2 * PAD)
    g.line(PAD, ty, W - PAD, ty, "ink")
    m = dt.date(2025, 6, 1)
    while m < t1:
        xx = X(m.isoformat())
        g.line(xx, ty - 4, xx, ty + 4, "ink")
        g.mono(xx, ty + 20, m.strftime("%b %y"), 8.5, anchor="middle")
        m = dt.date(m.year + (m.month + 3 > 12), (m.month + 2) % 12 + 1, 1)
    srt = sorted(repos, key=lambda r: r["pushed"])
    for i, r in enumerate(srt):
        xx = X(r["pushed"]); own = r["role"] in ("Owner", "Team")
        up = i % 2 == 0
        yy = ty - 24 - (i // 2 % 3) * 13 if up else ty + 42 + (i // 2 % 2) * 13
        g.line(xx, ty, xx, yy + (4 if up else -10), "rule")
        g.add(f'<circle cx="{xx:.1f}" cy="{ty}" r="{5 if own else 3.5}" fill="{T["accent"] if own else T["paper"]}" stroke="{T["ink"]}"/>')
        g.text(xx, yy, r["name"], "mo4", 9.5, "ink", "end" if xx > W - 170 else "start")
    g.mono(PAD, ty + 90, "● own / team-led   ○ collaborator   · plotted by last push", 9)

    # index
    iy = ty + 128
    heads = [("№", PAD), ("Repository", PAD + 40), ("Owner", PAD + 330), ("Role", PAD + 480), ("Last push", PAD + 620)]
    for hname, hx in heads:
        g.mono(hx, iy, hname, 9.5)
    g.line(PAD, iy + 9, W - PAD, iy + 9, "ink")
    for i, r in enumerate(sorted(repos, key=lambda r: r["pushed"], reverse=True)):
        yy = iy + 34 + i * 30
        g.text(PAD, yy, f"{i+1:02d}", "mo4", 10.5, "graphite")
        g.text(PAD + 40, yy, r["name"], "ar4", 13.5)
        g.text(PAD + 330, yy, r["owner"], "ar4", 13.5, "graphite")
        g.text(PAD + 480, yy, r["role"].upper(), "mo5", 9.5, ls=.5)
        g.text(PAD + 620, yy, dt.date.fromisoformat(r["pushed"]).strftime("%d %b %Y"), "ar4", 13.5)
        g.line(PAD, yy + 11, W - PAD, yy + 11, "rule")
    g.h = iy + 34 + len(repos) * 30 + 20
    return g


def plate_colophon(T):
    g = SVG(T, 0, "Colophon — LinkedIn /in/divisha-gera, LeetCode /u/divishaaaaaa, GitHub @divishagera")
    sec_head(g, 66, "vi.", [("Colophon", "ink")], "p. 12")
    y = 132
    for l in wrap("Correspondence welcome. Collaborations, internships, questions about spikes.", "isi", 40, 420):
        g.text(PAD, y, l, "isi", 40); y += 42
    lx, lw = 500, W - PAD - 500
    ly = y - 42 - 2 * 38 + 4
    for name, handle in [("LinkedIn", "/in/divisha-gera ↗"), ("LeetCode", "/u/divishaaaaaa ↗"), ("GitHub", "@divishagera ↗")]:
        g.text(lx, ly, name, "ar4", 14)
        g.text(lx + lw, ly, handle.upper(), "mo4", 10, "graphite", "end", ls=.6)
        g.line(lx, ly + 10, lx + lw, ly + 10, "rule")
        ly += 38
    fy = y + 6
    g.line(PAD, fy, W - PAD, fy, "ink", 2)
    g.mono(PAD, fy + 22, "Set in Instrument Serif, Archivo & IBM Plex Mono", 9.5)
    g.mono(W / 2 + 40, fy + 22, "Composed in Bengaluru", 9.5, anchor="middle")
    g.mono(W - PAD, fy + 22, "Ed. " + dt.date.today().strftime("%d·%m·%Y"), 9.5, anchor="end")
    g.h = fy + 42
    return g


# ───────────────────────────── live data ─────────────────────────────

def gh(url, token, body=None):
    import urllib.request
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"bearer {token}", "User-Agent": "atelier-build",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def refresh_live(repos_doc):
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GH_LOGIN", "divishagera")
    if not token:
        print("GITHUB_TOKEN not set; skipping live refresh")
        return
    q = ("query($l:String!){user(login:$l){contributionsCollection{contributionCalendar{totalContributions "
         "weeks{contributionDays{date contributionCount}}}}}}")
    res = gh("https://api.github.com/graphql", token, {"query": q, "variables": {"l": login}})
    c = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = {d["date"]: d["contributionCount"] for w in c["weeks"] for d in w["contributionDays"]}
    cal = {"end": max(days), "total": c["totalContributions"], "days": days}
    json.dump(cal, open(os.path.join(DATA, "calendar.json"), "w"))
    for r in repos_doc["repos"]:
        if not r.get("public"):
            continue
        try:
            info = gh(f'https://api.github.com/repos/{r["owner"]}/{r["name"]}', token)
            r["pushed"] = info["pushed_at"][:10]
        except Exception as e:  # keep the stored date
            print("skip", r["name"], e)
    json.dump(repos_doc, open(os.path.join(DATA, "repos.json"), "w"), indent=2)


def main():
    repos_doc = json.load(open(os.path.join(DATA, "repos.json")))
    if "--live" in sys.argv:
        refresh_live(repos_doc)
    cal_path = os.path.join(DATA, "calendar.json")
    cal = json.load(open(cal_path)) if os.path.exists(cal_path) else {"end": dt.date.today().isoformat()}
    os.makedirs(OUT, exist_ok=True)
    only_log = "--field-log-only" in sys.argv
    for theme, T in THEMES.items():
        suf = "" if theme == "light" else "-dark"
        plates = {"field-log": lambda: plate_fieldlog(T, repos_doc["repos"], cal)}
        if not only_log:
            plates.update({
                "00-cover": lambda: plate_cover(T),
                "01-foreword": lambda: plate_foreword(T),
                "02-catalogue": lambda: plate_catalogue_head(T),
                "08-paper": lambda: plate_paper(T),
                "09-instruments": lambda: plate_instruments(T),
                "11-colophon": lambda: plate_colophon(T),
            })
            for wk in WORKS:
                plates["work-" + wk["slug"]] = (lambda wk=wk: plate_work(T, wk))
        for name, fn in plates.items():
            svg = fn().render()
            open(os.path.join(OUT, f"{name}{suf}.svg"), "w").write(svg)
            print(f"{name}{suf}.svg  {len(svg)/1024:.0f} KB")


if __name__ == "__main__":
    main()
