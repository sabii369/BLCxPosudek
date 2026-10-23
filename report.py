"""HTML protokol s podrobným postupem výpočtu, grafy a souhrnem využití."""
from __future__ import annotations

import base64
import datetime as dt
import html
import json
import re
from pathlib import Path

from . import __version__
from .grafy import vykresli_vse
from .protokol import Krok, Obrazek, Tabulka, VysledekPosudku, fmt

_SUB = re.compile(r"_\{([^{}]*)\}")
_SUP = re.compile(r"\^\{([^{}]*)\}")


def _mat(s: str) -> str:
    """Převod zápisu x_{i}, x^{2} na HTML indexy (text je již escapovaný nebo důvěryhodný)."""
    if not s:
        return ""
    for _ in range(3):
        s = _SUB.sub(r"<sub>\1</sub>", s)
        s = _SUP.sub(r"<sup>\1</sup>", s)
    return s


CSS = """
:root{--ink:#0b0b0b;--ink2:#52514e;--line:#d9d8d4;--surf:#fcfcfb;--soft:#f1f0ec;--accent:#2a78d6;
--ok:#0a7d0a;--okbg:#e7f5e7;--bad:#b42323;--badbg:#fbe9e9;--warn:#8a5a00;--warnbg:#fff4dc;}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--ink:#f0efec;--ink2:#c3c2b7;
--line:#3a3a37;--surf:#1a1a19;--soft:#262624;--accent:#3987e5;--ok:#5fd35f;--okbg:#14301a;--bad:#ff8a8a;
--badbg:#3a1717;--warn:#f3c255;--warnbg:#3a2d10;}
 img{background:#fcfcfb;}}
*{box-sizing:border-box}
body{margin:0;background:var(--surf);color:var(--ink);font:14px/1.5 "Segoe UI",system-ui,sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 4px}
h2{font-size:20px;margin:36px 0 10px;padding-bottom:4px;border-bottom:2px solid var(--line)}
h3{font-size:16px;margin:24px 0 8px}
.meta{color:var(--ink2);margin-bottom:20px}
table{border-collapse:collapse;width:100%;margin:8px 0 16px;font-size:13px;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}
td.num{text-align:right}
th{background:var(--soft);font-weight:600;text-align:center}
td:first-child,th:first-child{text-align:left}
caption{caption-side:top;text-align:left;font-weight:600;color:var(--ink2);padding:4px 0}
.steps td{text-align:left}
.steps td.v{text-align:right;white-space:nowrap;font-weight:600}
.steps td.f{font-family:"Cambria Math","Times New Roman",serif;font-size:15px}
.steps td.d{color:var(--ink2);font-family:"Cambria Math","Times New Roman",serif}
.steps td.r{color:var(--ink2);white-space:nowrap;font-size:12px}
.chk{display:flex;gap:12px;align-items:center;border:1px solid var(--line);border-left:5px solid var(--ok);
background:var(--okbg);padding:6px 12px;margin:6px 0;border-radius:4px}
.chk.bad{border-left-color:var(--bad);background:var(--badbg)}
.chk .n{flex:1}.chk .e{font-weight:700;white-space:nowrap}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:700}
.tag.ok{color:var(--ok);background:var(--okbg)}.tag.bad{color:var(--bad);background:var(--badbg)}
.bar{height:8px;background:var(--soft);border-radius:4px;min-width:90px;position:relative}
.bar i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--ok)}
.bar i.w{background:#eda100}.bar i.b{background:var(--bad)}
figure{margin:12px 0 20px}figure img{max-width:100%;border:1px solid var(--line);border-radius:4px}
figcaption{color:var(--ink2);font-size:13px;margin-top:4px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:12px 0}
.card{border:1px solid var(--line);border-radius:6px;padding:12px;background:var(--soft)}
.card .big{font-size:28px;font-weight:700}.card .lbl{color:var(--ink2)}
.toc a{color:var(--accent);text-decoration:none}.toc li{margin:2px 0}
.wrap{overflow-x:auto}
@media print{h2{page-break-before:always}.chk,figure,table{page-break-inside:avoid}}
"""


TAG_OK_ALL = '<span class="tag ok">VŠE VYHOVUJE</span>'
TAG_BAD_ALL = '<span class="tag bad">NĚKTERÉ NEVYHOVUJÍ</span>'
TAG_ANO = '<span class="tag ok">ano</span>'
TAG_NE = '<span class="tag bad">ne</span>'


_NUM = re.compile(r"^[−\-+]?[\d∞]")


def _td(c) -> str:
    t = c if isinstance(c, str) else fmt(c)
    cls = ' class="num"' if _NUM.match(t) else ""
    return f"<td{cls}>{_mat(html.escape(t))}</td>"


def _img(path: Path, embed: bool) -> str:
    if embed:
        b64 = base64.b64encode(path.read_bytes()).decode()
        return f"data:image/png;base64,{b64}"
    return f"obrazky/{path.name}"


def _bar(eta: float) -> str:
    w = min(eta, 1.2) / 1.2 * 100
    cls = "" if eta <= 0.9 else ("w" if eta <= 1.0 else "b")
    return f'<div class="bar"><i class="{cls}" style="width:{w:.1f}%"></i></div>'


def _posudek_html(v: VysledekPosudku) -> str:
    cls = "" if v.vyhovuje else " bad"
    tag = '<span class="tag ok">VYHOVUJE</span>' if v.vyhovuje else '<span class="tag bad">NEVYHOVUJE</span>'
    misto = f", x = {fmt(v.x, 3)} m" if v.x is not None else ""
    komb = f", {v.kombinace}" if v.kombinace else ""
    pozn = f" <small>({html.escape(v.poznamka)})</small>" if v.poznamka else ""
    odk = f" <small>[{html.escape(v.odkaz)}]</small>" if v.odkaz else ""
    return (f'<div class="chk{cls}"><div class="n"><b>{html.escape(v.nazev)}</b>{odk}<br>'
            f'<small>{html.escape(v.faze)}{komb}{misto}</small>{pozn}</div>'
            f'<div>E<sub>d</sub> = {_mat(fmt(v.E_d))} {v.jednotka} ≤ R<sub>d</sub> = {_mat(fmt(v.R_d))} {v.jednotka}</div>'
            f'<div class="e">η = {v.vyuziti * 100:.1f} %</div>{tag}</div>')


def _souhrn(model) -> str:
    pos = model.protokol.posudky
    out = []
    for ms in ("MSÚ", "MSP"):
        p = [v for v in pos if v.mezni_stav == ms]
        if not p:
            continue
        mx = max(p, key=lambda v: v.vyuziti)
        ok = all(v.vyhovuje for v in p)
        out.append(f'<div class="card"><div class="lbl">{ms} – nejvyšší využití</div>'
                   f'<div class="big">{mx.vyuziti * 100:.0f} %</div>'
                   f'<div>{html.escape(mx.nazev)} ({html.escape(mx.faze)})</div>'
                   f'<div style="margin-top:6px">{TAG_OK_ALL if ok else TAG_BAD_ALL}</div></div>')
    cards = '<div class="cards">' + "".join(out) + "</div>"
    # agregace po skupinách
    rows = []
    for ms in ("MSÚ", "MSP"):
        skup: dict[str, list[VysledekPosudku]] = {}
        for v in pos:
            if v.mezni_stav == ms:
                skup.setdefault(v.skupina or v.nazev, []).append(v)
        for s, vs in skup.items():
            mx = max(vs, key=lambda v: v.vyuziti)
            rows.append(f"<tr><td>{ms}</td><td>{html.escape(s)}</td><td>{html.escape(mx.nazev)}</td>"
                        f"<td>{html.escape(mx.faze)}</td><td class=num>{fmt(mx.x, 3) if mx.x is not None else '–'}</td>"
                        f"<td class=num>{mx.vyuziti * 100:.1f} %</td><td>{_bar(mx.vyuziti)}</td>"
                        f"<td>{TAG_ANO if all(v.vyhovuje for v in vs) else TAG_NE}</td></tr>")
    tab = ('<div class="wrap"><table><caption>Využití podle mezních stavů a skupin posudků (maximum přes všechny fáze)'
           '</caption><tr><th>MS</th><th>Skupina</th><th>Rozhodující posudek</th><th>Fáze</th><th>x [m]</th>'
           '<th>η</th><th></th><th>Vyhovuje</th></tr>' + "".join(rows) + "</table></div>")
    full = []
    for v in pos:
        full.append(f"<tr><td>{v.mezni_stav}</td><td>{html.escape(v.nazev)}</td><td>{html.escape(v.faze)}</td>"
                    f"<td>{html.escape(v.kombinace)}</td><td class=num>{fmt(v.x, 3) if v.x is not None else '–'}</td>"
                    f"<td class=num>{_mat(fmt(v.E_d))}</td><td class=num>{_mat(fmt(v.R_d))}</td><td>{v.jednotka}</td>"
                    f"<td class=num>{v.vyuziti * 100:.1f} %</td><td>{_bar(v.vyuziti)}</td></tr>")
    tab2 = ('<details><summary>Všechny posudky ({} položek)</summary><div class="wrap"><table>'
            '<tr><th>MS</th><th>Posudek</th><th>Fáze</th><th>Kombinace</th><th>x [m]</th><th>E<sub>d</sub></th>'
            '<th>R<sub>d</sub></th><th></th><th>η</th><th></th></tr>{}</table></div></details>').format(
        len(pos), "".join(full))
    return cards + tab + tab2


def sestav_html(model, obrazky: dict[str, str], adr_obr: Path, embed: bool = True) -> str:
    P = model.protokol
    parts = []
    toc = []
    c1 = c2 = 0
    for kap in P.kapitoly:
        if kap.uroven == 1:
            c1 += 1
            c2 = 0
            num = f"{c1}"
            tagh = "h2"
        else:
            c2 += 1
            num = f"{c1}.{c2}"
            tagh = "h3"
        aid = f"k{num.replace('.', '_')}"
        toc.append((kap.uroven, num, kap.nazev, aid))
        parts.append(f'<{tagh} id="{aid}">{num} {html.escape(kap.nazev)}</{tagh}>')
        steps: list[str] = []

        def flush():
            if steps:
                parts.append('<div class="wrap"><table class="steps">' + "".join(steps) + "</table></div>")
                steps.clear()

        for typ, obj in kap.polozky:
            if typ == "krok":
                k: Krok = obj
                val = obj.vysledek
                vs = "" if val is None else (_mat(fmt(val)) + (f" {k.jednotka}" if k.jednotka else ""))
                eq = " = " if (k.vzorec or k.dosazeni) and vs else ""
                steps.append(f'<tr><td>{html.escape(k.popis)}</td><td class="f">{_mat(html.escape(k.vzorec))}</td>'
                             f'<td class="d">{"= " + _mat(html.escape(k.dosazeni)) if k.dosazeni else ""}</td>'
                             f'<td class="v">{eq}{vs}</td><td class="r">{html.escape(k.odkaz)}</td></tr>')
                continue
            flush()
            if typ == "text":
                if obj:
                    parts.append(f"<p>{_mat(obj)}</p>")
            elif typ == "tabulka":
                t: Tabulka = obj
                h = "".join(f"<th>{_mat(html.escape(str(c)))}</th>" for c in t.hlavicka)
                rows = "".join("<tr>" + "".join(_td(c) for c in r) + "</tr>" for r in t.radky)
                parts.append(f'<div class="wrap"><table><caption>{html.escape(t.popisek)}</caption>'
                             f"<tr>{h}</tr>{rows}</table></div>")
            elif typ == "obrazek":
                o: Obrazek = obj
                if o.soubor in obrazky:
                    src = _img(adr_obr / obrazky[o.soubor], embed)
                    parts.append(f'<figure><img src="{src}" alt="{html.escape(o.popisek)}">'
                                 f"<figcaption>{html.escape(o.popisek)}</figcaption></figure>")
            elif typ == "posudek":
                parts.append(_posudek_html(obj))
        flush()
    toc_html = "<ul class='toc'>" + "".join(
        f"<li style='margin-left:{(u - 1) * 18}px'><a href='#{a}'>{n} {html.escape(t)}</a></li>" for u, n, t, a in toc
    ) + "</ul>"
    vyuz = ""
    if "vyuziti" in obrazky:
        vyuz = (f'<figure><img src="{_img(adr_obr / obrazky["vyuziti"], embed)}" alt="Souhrn využití">'
                "<figcaption>Využití jednotlivých posudků (maximum přes fáze); zelená η ≤ 90 %, žlutá ≤ 100 %, "
                "červená &gt; 100 %</figcaption></figure>")
    pr = model.projekt
    meta = (f"Vypracoval: {html.escape(pr.get('autor', '') or '–')} · Datum: {dt.date.today():%d. %m. %Y} · "
            f"pb_posudek {__version__} · ČSN EN 1990, ČSN EN 1992-1-1, ČSN EN 1992-2")
    return f"""<!doctype html><html lang="cs"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(P.nazev)}</title><style>{CSS}</style></head><body><main>
<h1>{html.escape(P.nazev)}</h1><div class="meta">{meta}</div>
<h2 id="souhrn">Souhrn posouzení</h2>
{_souhrn(model)}
{vyuz}
<h2>Obsah</h2>{toc_html}
{''.join(parts)}
<p class="meta" style="margin-top:40px">Upozornění: výsledky je nutné ověřit odpovědnou osobou. Zjednodušení a předpoklady
výpočtu jsou uvedeny v jednotlivých kapitolách.</p>
</main></body></html>"""


def uloz_protokol(model, adresar: str | Path = "vystup", embed: bool = True) -> Path:
    adr = Path(adresar)
    adr.mkdir(parents=True, exist_ok=True)
    adr_obr = adr / "obrazky"
    if not model.protokol.posudky:
        model.spocitej()
    obr = vykresli_vse(model, adr_obr)
    html_s = sestav_html(model, obr, adr_obr, embed)
    out = adr / "protokol.html"
    out.write_text(html_s, encoding="utf-8")
    vys = dict(
        projekt=model.projekt,
        posudky=[v.as_dict() for v in model.protokol.posudky],
        x=model.x.tolist(),
        faze=[dict(nazev=f.nazev, t=f.t, P_kN=(-model._sily_predpeti(f.sigma)[0]).tolist(),
                   sigma_p=[s.tolist() for s in f.sigma]) for f in model.faze],
    )
    (adr / "vysledky.json").write_text(json.dumps(vys, ensure_ascii=False, indent=1, default=float),
                                       encoding="utf-8")
    return out
