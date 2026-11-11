"""Grafické rozhraní (tkinter) pro posudek nosníku z předpjatého betonu.

Spuštění:  python -m pb_posudek.gui   (nebo  python -m pb_posudek  bez argumentů)
"""
from __future__ import annotations

import copy
import gc
import json
import os
import sys
import threading
import traceback
import webbrowser
from dataclasses import MISSING, fields
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Polygon

from . import __version__, grafy
from .materialy import (BETONARSKA_VYZTUZ, DRUHY_PREDPINACI_VYZTUZE, PREDPINACI_VYZTUZ, RELAXACE_RHO1000, Beton,
                        BetonarskaVyztuz, PredpinaciVyztuz)
from .model import Nastaveni
from .protokol import fmt
from .toml_zapis import dumps as toml_dumps
from .vstup import _prurez, geometrie_kabelu, model_ze_slovniku, nacti_soubor
from .zatizeni import DRUHY_KOMBINACI

TRIDY_BETONU = ["C20/25", "C25/30", "C30/37", "C35/45", "C40/50", "C45/55", "C50/60", "C55/67",
                "C60/75", "C70/85", "C80/95", "C90/105"]

PRIKLAD = Path(__file__).resolve().parents[1] / "examples" / "nosnik_I_20m_kombinace.toml"

VYCHOZI = {
    "projekt": {"nazev": "Nový nosník", "popis": "", "autor": ""},
    "beton": {"trida": "C45/55", "cement": "N", "objemova_tiha": 25.0},
    "predpinaci_vyztuz": {"typ": "Y1860S7-15,7"},
    "betonarska_vyztuz": {"typ": "B500B"},
    "prurez": {"vrstvy": [[400, 400, 150], [400, 150, 100], [150, 150, 500], [150, 500, 100], [500, 500, 150]]},
    "nosnik": {"L": 15.5, "L0": 15.0, "predpeti": "dodatecne", "charakteristiky": "brutto", "pocet_rezu": 41},
    "kabel": [{"nazev": "K1", "pocet_lan": 12, "geometrie": "parabola", "z_L": 500, "z_S": 120, "z_P": 500,
               "sigma_max": 1440, "napinani": "oba", "mu": 0.19, "k": 0.005, "pokluz": 6.0, "d_kanalku": 80}],
    "vyztuz": [{"nazev": "4Ø16", "z": 45, "As": 804}],
    "smykova_vyztuz": [{"Asw": 157, "s": 150, "alpha": 90}],
    "prostredi": {"RH": 70, "t_s": 1},
    "casova_osa": {"t0": 7, "t_provoz": 120, "t_konec": 36500},
    "zatizeni": {"zpusob": "kombinace", "obsahuje_vlastni_tihu": False, "t_vneseni": 60,
                 "kombinace": [{"druh": "6.10a", "q": 21.9}, {"druh": "6.10b", "q": 23.5},
                               {"druh": "char", "q": 16.0}, {"druh": "casta", "q": 14.0},
                               {"druh": "kvazistala", "q": 12.4}],
                 "stale": [{"nazev": "Ostatní stálé", "q": 10.0, "t": 60}],
                 "promenne": [{"nazev": "Užitné", "q": 8.0, "psi0": 0.7, "psi1": 0.5, "psi2": 0.3, "gamma": 1.5}]},
    "posouzeni": {},
}

POPISKY_NASTAVENI = {
    "k1_nap": "k1 – napínání (·f_pk)", "k2_nap": "k2 – napínání (·f_p0,1k)",
    "k7": "k7 – po zakotvení (·f_pk)", "k8": "k8 – po zakotvení (·f_p0,1k)",
    "k_predpeti": "Tlak při vnesení předpětí (·f_ck(t))", "k1": "Tlak – charakteristická (·f_ck)",
    "k2": "Tlak – kvazistálá (·f_ck)", "k5": "Napětí v předp. výztuži (·f_pk)",
    "tah_predpeti": "Mez tahu – předpětí a výstavba", "tah_provoz": "Mez tahu – provoz (charakt.)",
    "dekomprese": "Dekomprese – kombinace", "dekomprese_rezim": "Dekomprese – vlákno",
    "zbytkova_zivotnost": "Zbytková životnost [roky] (tab. 12.3 → dekomprese, trhliny)",
    "trhliny": "Šířka trhlin – kombinace", "w_max": "Omezení šířky trhlin w_max [mm]",
    "xi_p": "ξ soudržnost předp. výztuže (prázdné = tab. 6.2)",
    "a_dek": "Hloubka dekomprese od kabelu [mm]", "r_sup": "r_sup (prázdné = dle typu)",
    "r_inf": "r_inf (prázdné = dle typu)", "gamma_P": "γ_P", "gamma_G": "γ_G,sup",
    "gamma_G_inf": "γ_G,inf", "xi": "ξ (6.10b)", "kombinace_msu": "Kombinace MSÚ",
    "cot_theta_min": "cotg θ min", "cot_theta_max": "cotg θ max", "kanalky": "Kanálky (b_w,nom)",
    "pruhyb_limit": "Mezní průhyb L/…", "relaxace_t_max_h": "Relaxace – max. čas [h]",
    "hlavni_napeti": "Posoudit hlavní napětí",
}
VOLBY_NASTAVENI = {
    "tah_predpeti": ["fctm", "fctk005", "0"], "tah_provoz": ["fctm", "fctk005", "0"],
    "dekomprese": ["casta", "kvazistala", "zadna"], "dekomprese_rezim": ["krajni", "kabel"],
    "zbytkova_zivotnost": ["", "50", "15-30", "10"], "trhliny": ["char", "casta", "kvazistala", "zadna"],
    "kombinace_msu": ["6.10ab", "6.10"], "kanalky": ["ocel", "plast"],
}


# ---------------------------------------------------------------------------
# pomocné převody
# ---------------------------------------------------------------------------

def _cislo(s: str):
    s = str(s).strip().replace(",", ".").replace(" ", "").replace(" ", "")
    if s == "":
        return None
    v = float(s)
    return int(v) if v.is_integer() and "." not in s and "e" not in s.lower() else v


def _na_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _pary_na_text(p) -> str:
    return "; ".join(f"{a:g}:{b:g}" for a, b in p) if p else ""


def _text_na_pary(s: str):
    s = s.strip()
    if not s:
        return None
    out = []
    for cast in s.replace("\n", ";").split(";"):
        cast = cast.strip()
        if not cast:
            continue
        sep = ":" if ":" in cast else "@"
        a, b = cast.split(sep)
        out.append([float(a.replace(",", ".")), float(b.replace(",", "."))])
    return out


def _seznam_na_text(p) -> str:
    return "; ".join(f"{a:g}" for a in p) if p else ""


def _text_na_seznam(s: str):
    s = s.strip()
    if not s:
        return None
    return [float(a.strip().replace(",", ".")) for a in s.split(";") if a.strip()]


# ---------------------------------------------------------------------------
# widgety
# ---------------------------------------------------------------------------

class Formular(ttk.Frame):
    """Formulář: pole = [(klíč, popisek, typ, volby)]; typ: str|float|optfloat|int|optint|choice|bool.

    U typu bool je ve „volby“ výchozí hodnota.
    """

    def __init__(self, master, pole, sloupcu: int = 1, pri_zmene=None, **kw):
        super().__init__(master, **kw)
        self.pole = pole
        self.prom: dict[str, tk.Variable] = {}
        self.widgety: dict[str, tk.Widget] = {}
        self.pri_zmene = pri_zmene
        for i, (k, popis, typ, volby) in enumerate(pole):
            r, c = divmod(i, sloupcu)
            ttk.Label(self, text=popis).grid(row=r, column=2 * c, sticky="w", padx=(4, 6), pady=2)
            if typ == "bool":
                v = tk.BooleanVar()
                w = ttk.Checkbutton(self, variable=v)
            elif typ == "choice":
                v = tk.StringVar()
                w = ttk.Combobox(self, textvariable=v, values=volby, width=16)
            else:
                v = tk.StringVar()
                w = ttk.Entry(self, textvariable=v, width=18 if typ not in ("str", "pary") else 40)
            w.grid(row=r, column=2 * c + 1, sticky="we", padx=(0, 14), pady=2)
            self.prom[k] = v
            self.widgety[k] = w
            if pri_zmene:
                v.trace_add("write", lambda *_: self.pri_zmene())
        for c in range(sloupcu):
            self.columnconfigure(2 * c + 1, weight=1)

    def nastav(self, d: dict):
        for k, popis, typ, volby in self.pole:
            v = d.get(k)
            if typ == "bool":
                self.prom[k].set(bool(volby) if v is None else bool(v))
            elif typ == "pary":
                self.prom[k].set(_pary_na_text(v))
            else:
                self.prom[k].set(_na_text(v))

    def doplnit(self, d: dict, prepsat: bool = False):
        """Vyplní pole hodnotami z d – prázdná pole vždy, ostatní jen při prepsat=True."""
        for k, v in d.items():
            if k not in self.prom or v is None:
                continue
            var = self.prom[k]
            if isinstance(var, tk.BooleanVar):
                continue
            if prepsat or not str(var.get()).strip():
                var.set(_na_text(v))

    def ziskej(self) -> dict:
        out = {}
        for k, popis, typ, volby in self.pole:
            v = self.prom[k].get()
            if typ == "bool":
                out[k] = bool(v)
                continue
            if typ in ("float", "optfloat", "int", "optint"):
                try:
                    c = _cislo(v)
                except ValueError:
                    raise ValueError(f"Pole „{popis}“: neplatné číslo „{v}“")
                if c is None:
                    if typ in ("float", "int"):
                        raise ValueError(f"Pole „{popis}“ je povinné.")
                    continue
                out[k] = int(c) if typ in ("int", "optint") else float(c)
            elif typ == "pary":
                try:
                    pary = _text_na_pary(v)
                except ValueError:
                    raise ValueError(f"Pole „{popis}“: neplatný zápis „{v}“ (např. 1200:2; 800:0)")
                if pary:
                    out[k] = pary
            else:
                if v.strip() != "":
                    out[k] = _cislo(v) if typ == "choice" and k == "trida_relaxace" else v
        return out


class Tabulka(ttk.Frame):
    """Editovatelná tabulka. sloupce = [(klíč, popisek, šířka, typ, volby)].

    typ: str | float | optfloat | int | choice | pary | seznam. Klíče řádků, které tabulka nezobrazuje,
    se zachovají.
    """

    def __init__(self, master, sloupce, pri_zmene=None, vyska: int = 6, vychozi: dict | None = None, **kw):
        super().__init__(master, **kw)
        self.sloupce = sloupce
        self.vychozi = vychozi or {}
        self.pri_zmene = pri_zmene
        self._navic: dict[str, dict] = {}
        klice = [s[0] for s in sloupce]
        fr = ttk.Frame(self)
        fr.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(fr, columns=klice, show="headings", height=vyska, selectmode="browse")
        for k, popis, sirka, typ, volby in sloupce:
            self.tree.heading(k, text=popis)
            self.tree.column(k, width=sirka, anchor="e" if typ in ("float", "optfloat", "int") else "w",
                             stretch=typ in ("str", "pary", "seznam"))
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tree.yview)
        sbx = ttk.Scrollbar(fr, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb.set, xscrollcommand=sbx.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        sbx.grid(row=1, column=0, sticky="ew")
        fr.rowconfigure(0, weight=1)
        fr.columnconfigure(0, weight=1)
        tl = ttk.Frame(self)
        tl.pack(fill="x", pady=(3, 0))
        ttk.Button(tl, text="+ Přidat", command=self.pridej).pack(side="left")
        ttk.Button(tl, text="Duplikovat", command=self.duplikuj).pack(side="left", padx=3)
        ttk.Button(tl, text="− Odebrat", command=self.odeber).pack(side="left")
        ttk.Button(tl, text="▲", width=3, command=lambda: self.posun(-1)).pack(side="left", padx=(8, 0))
        ttk.Button(tl, text="▼", width=3, command=lambda: self.posun(1)).pack(side="left")
        ttk.Label(tl, text="dvojklik = úprava buňky, Tab = další buňka", foreground="#52514e").pack(side="right")
        self.tree.bind("<Double-1>", self._edituj)
        self._editor = None

    # --- data -----------------------------------------------------------
    def nastav(self, radky: list[dict]):
        self.tree.delete(*self.tree.get_children())
        self._navic.clear()
        for r in radky or []:
            self._vloz(r)

    def _vloz(self, r: dict, index="end"):
        r = {**{k: v for k, v in self.vychozi.items() if r.get(k) in (None, "")}, **{k: v for k, v in r.items()
                                                                                  if v not in (None, "")}}
        hodnoty = []
        for k, popis, sirka, typ, volby in self.sloupce:
            v = r.get(k)
            if typ == "pary":
                hodnoty.append(_pary_na_text(v))
            elif typ == "seznam":
                hodnoty.append(_seznam_na_text(v))
            else:
                hodnoty.append(_na_text(v))
        iid = self.tree.insert("", index, values=hodnoty)
        self._navic[iid] = {k: v for k, v in r.items() if k not in {s[0] for s in self.sloupce}}
        return iid

    def ziskej_surove(self) -> list[dict]:
        """Řádky jako slovníky textů (prázdné buňky vynechány) včetně skrytých klíčů."""
        out = []
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            r = dict(self._navic.get(iid, {}))
            for (k, popis, sirka, typ, volby), v in zip(self.sloupce, vals):
                if str(v).strip():
                    r[k] = _text_na_pary(str(v)) if typ == "pary" else (
                        _text_na_seznam(str(v)) if typ == "seznam" else
                        (_cislo(v) if typ in ("float", "optfloat", "int") else str(v)))
            out.append(r)
        return out

    def ziskej(self) -> list[dict]:
        return [self._radek(n, iid) for n, iid in enumerate(self.tree.get_children(), 1)]

    def ziskej_radky(self) -> list[tuple[int, dict | None, str | None]]:
        """Každý řádek zvlášť: (číslo řádku, slovník nebo None, text chyby nebo None)."""
        out = []
        for n, iid in enumerate(self.tree.get_children(), 1):
            try:
                out.append((n, self._radek(n, iid), None))
            except ValueError as e:
                out.append((n, None, str(e)))
        return out

    def _radek(self, n: int, iid) -> dict:
        vals = self.tree.item(iid, "values")
        r = dict(self._navic.get(iid, {}))
        for (k, popis, sirka, typ, volby), v in zip(self.sloupce, vals):
            v = str(v)
            try:
                if typ in ("float", "optfloat", "int"):
                    c = _cislo(v)
                    if c is None:
                        if typ != "optfloat":
                            raise ValueError("povinná hodnota")
                        r.pop(k, None)
                        continue
                    r[k] = int(c) if typ == "int" else float(c)
                elif typ == "pary":
                    p = _text_na_pary(v)
                    if p is None:
                        r.pop(k, None)
                    else:
                        r[k] = p
                elif typ == "seznam":
                    p = _text_na_seznam(v)
                    if p is None:
                        r.pop(k, None)
                    else:
                        r[k] = p
                elif v.strip():
                    r[k] = v
                else:
                    r.pop(k, None)
            except ValueError as e:
                raise ValueError(f"Řádek {n}, sloupec „{popis}“: neplatná hodnota „{v}“ ({e})")
        return r

    # --- úpravy -----------------------------------------------------------
    def _zmena(self):
        if self.pri_zmene:
            self.pri_zmene()

    def pridej(self):
        vzor = {}
        deti = self.tree.get_children()
        if deti:
            try:
                vzor = self.ziskej()[-1]
            except ValueError:
                vzor = {}
            if "nazev" in vzor:
                vzor["nazev"] = f"{vzor['nazev']}*"
        iid = self._vloz(vzor)
        self.tree.selection_set(iid)
        self._zmena()

    def duplikuj(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        r = self.ziskej()[idx]
        iid = self._vloz(copy.deepcopy(r), idx + 1)
        self.tree.selection_set(iid)
        self._zmena()

    def odeber(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self._navic.pop(iid, None)
        self._zmena()

    def posun(self, d):
        sel = self.tree.selection()
        if not sel:
            return
        i = self.tree.index(sel[0])
        self.tree.move(sel[0], "", max(i + d, 0))
        self._zmena()

    def _edituj(self, event=None, iid=None, col=None):
        if event is not None:
            if self.tree.identify_region(event.x, event.y) != "cell":
                return
            iid = self.tree.identify_row(event.y)
            col = int(self.tree.identify_column(event.x)[1:]) - 1
        if not iid:
            return
        self.tree.see(iid)
        bbox = self.tree.bbox(iid, f"#{col + 1}")
        if not bbox:
            return
        k, popis, sirka, typ, volby = self.sloupce[col]
        hodn = self.tree.item(iid, "values")[col]
        var = tk.StringVar(value=hodn)
        if typ == "choice":
            w = ttk.Combobox(self.tree, textvariable=var, values=volby)
        else:
            w = ttk.Entry(self.tree, textvariable=var)
        x, y, wdt, hgt = bbox
        w.place(x=x, y=y, width=max(wdt, 80), height=hgt)
        w.focus_set()
        if isinstance(w, ttk.Entry):
            w.select_range(0, "end")
        self._editor = w

        def potvrd(_=None, dalsi=0):
            if self._editor is not w:
                return
            vals = list(self.tree.item(iid, "values"))
            vals[col] = var.get()
            self.tree.item(iid, values=vals)
            w.destroy()
            self._editor = None
            self._zmena()
            if dalsi:
                nc = col + dalsi
                if 0 <= nc < len(self.sloupce):
                    self._edituj(iid=iid, col=nc)
            return "break"

        def zrus(_=None):
            w.destroy()
            self._editor = None

        w.bind("<Return>", potvrd)
        w.bind("<KP_Enter>", potvrd)
        w.bind("<Tab>", lambda e: potvrd(dalsi=1))
        w.bind("<Shift-Tab>", lambda e: potvrd(dalsi=-1))
        w.bind("<Escape>", zrus)
        w.bind("<FocusOut>", lambda e: potvrd() if typ != "choice" else None)
        if typ == "choice":
            w.bind("<<ComboboxSelected>>", potvrd)


class Graf(ttk.Frame):
    """Plátno matplotlib s nástrojovou lištou (zoom, posun, uložení)."""

    def __init__(self, master, figsize=(6, 4), lista=True, **kw):
        super().__init__(master, **kw)
        self.fig = Figure(figsize=figsize, dpi=96)
        self._vytvor_platno(lista)

    def _vytvor_platno(self, lista=True):
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
        self.toolbar = None
        if lista:
            self.toolbar = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
            self.toolbar.update()
            self.toolbar.pack(side="bottom", fill="x")

    def zobraz(self, fig: Figure):
        """Nahradí obsah jiným objektem Figure (rozvržení se přepočítá při každé změně velikosti)."""
        old = self.fig
        fig.set_layout_engine("tight")
        self.canvas.get_tk_widget().destroy()
        if self.toolbar:
            self.toolbar.destroy()
        self.fig = fig
        self._vytvor_platno(True)
        self.canvas.draw_idle()
        del old


KOMB_ZALOZKY = [("6.10a", "MSÚ 6.10a"), ("6.10b", "MSÚ 6.10b"), ("char", "Charakteristická"),
                ("casta", "Častá"), ("kvazistala", "Kvazistálá"), ("6.10", "MSÚ 6.10 (místo 6.10a/b)")]
SLOUPCE_KOMB = ["x", "M_max", "M_min", "V_max", "V_min"]


def _parsuj_schranku(text: str) -> list[list[float]]:
    """Řádky čísel ze schránky (Excel, SCIA – tabulátor, středník nebo mezery; desetinná čárka i tečka)."""
    radky = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if "\t" in ln:
            casti = ln.split("\t")
        elif ";" in ln:
            casti = ln.split(";")
        else:
            casti = ln.split()
        try:
            radky.append([float(c.strip().replace("\u202f", "").replace(" ", "").replace(",", "."))
                          for c in casti if c.strip()])
        except ValueError:
            continue  # záhlaví nebo text
    return radky


class KombinacePanel(ttk.Frame):
    """Přímé zadání kombinací: pro každou kombinaci spojité zatížení q nebo tabulka vnitřních sil."""

    def __init__(self, master, pri_zmene=None, **kw):
        super().__init__(master, **kw)
        self.pri_zmene = pri_zmene or (lambda: None)
        hl = ttk.Frame(self)
        hl.pack(fill="x", pady=(0, 4))
        self.var_g0 = tk.BooleanVar(value=False)
        ttk.Checkbutton(hl, text="Kombinace obsahují vlastní tíhu nosníku g0 (program ji odečte)",
                        variable=self.var_g0, command=self.pri_zmene).pack(side="left")
        ttk.Label(hl, text="   Kvazistálá kombinace působí od stáří t [dny]:").pack(side="left")
        self.var_tv = tk.StringVar()
        ttk.Entry(hl, textvariable=self.var_tv, width=8).pack(side="left", padx=4)
        ttk.Label(hl, text="(prázdné = uvedení do provozu)", foreground="#52514e").pack(side="left")
        self.var_tv.trace_add("write", lambda *_: self.pri_zmene())
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.karty: dict[str, dict] = {}
        for druh, nazev in KOMB_ZALOZKY:
            fr = ttk.Frame(self.nb, padding=6)
            self.nb.add(fr, text=nazev)
            rez = tk.StringVar(value="q")
            r = ttk.Frame(fr)
            r.pack(fill="x")
            ttk.Label(r, text="Zadání:").pack(side="left")
            ram_q = ttk.Frame(fr)
            ram_t = ttk.Frame(fr)
            k = dict(rezim=rez, ram_q=ram_q, ram_t=ram_t)
            for val, txt in (("q", "náhradní spojité zatížení q"), ("tabulka", "tabulka vnitřních sil M, V")):
                ttk.Radiobutton(r, text=txt, value=val, variable=rez,
                                command=lambda d=druh: self._prepni(d)).pack(side="left", padx=4)
            k["fq"] = Formular(ram_q, [("q", "q [kN/m]", "optfloat", None), ("od", "od x [m]", "optfloat", None),
                                       ("do", "do x [m]", "optfloat", None)], sloupcu=3, pri_zmene=self.pri_zmene)
            k["fq"].pack(fill="x", pady=4)
            br = ttk.Frame(ram_q)
            br.pack(fill="x")
            ttk.Label(br, text="Osamělá břemena F:x; … [kN:m]").pack(side="left")
            k["bremena"] = tk.StringVar()
            ttk.Entry(br, textvariable=k["bremena"], width=50).pack(side="left", padx=4)
            k["bremena"].trace_add("write", lambda *_: self.pri_zmene())
            ttk.Label(ram_q, foreground="#52514e", text=(
                "q působí na celé délce nosníku (není-li zadáno od–do); vnitřní síly se spočtou na prostém nosníku "
                "s převislými konci.")).pack(anchor="w", pady=4)
            k["tab"] = Tabulka(ram_t, [
                ("x", "x [m]", 70, "float", None), ("M_max", "M_max [kNm]", 95, "float", None),
                ("M_min", "M_min [kNm]", 95, "optfloat", None), ("V_max", "V_max [kN]", 95, "optfloat", None),
                ("V_min", "V_min [kN]", 95, "optfloat", None)], pri_zmene=self.pri_zmene, vyska=8)
            k["tab"].pack(fill="both", expand=True)
            bt = ttk.Frame(ram_t)
            bt.pack(fill="x", pady=(4, 0))
            ttk.Button(bt, text="Vložit ze schránky (Excel / SCIA)",
                       command=lambda d=druh: self._vloz_schranku(d)).pack(side="left")
            ttk.Button(bt, text="Vymazat tabulku", command=lambda d=druh: self._vymaz(d)).pack(side="left", padx=4)
            ttk.Label(bt, foreground="#52514e", text=(
                "sloupce: x, M  |  x, M, V  |  x, M_max, M_min, V_max  |  x, M_max, M_min, V_max, V_min")
                      ).pack(side="left", padx=6)
            self.karty[druh] = k
            self._prepni(druh)

    def _prepni(self, druh: str):
        k = self.karty[druh]
        k["ram_q"].pack_forget()
        k["ram_t"].pack_forget()
        (k["ram_q"] if k["rezim"].get() == "q" else k["ram_t"]).pack(fill="both", expand=True)
        self.pri_zmene()

    def _vymaz(self, druh: str):
        self.karty[druh]["tab"].nastav([])
        self.pri_zmene()

    def _vloz_schranku(self, druh: str):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("Schránka", "Schránka neobsahuje text.")
            return
        radky = _parsuj_schranku(text)
        if not radky:
            messagebox.showwarning("Schránka", "Ve schránce nejsou číselné řádky.")
            return
        n = max(len(r) for r in radky)
        mapa = {2: ["x", "M_max"], 3: ["x", "M_max", "V_max"], 4: ["x", "M_max", "M_min", "V_max"]}.get(
            n, SLOUPCE_KOMB)
        data = [{c: v for c, v in zip(mapa, r)} for r in radky if len(r) >= 2]
        self.karty[druh]["tab"].nastav(data)
        self.karty[druh]["rezim"].set("tabulka")
        self._prepni(druh)
        messagebox.showinfo("Schránka", f"Vloženo {len(data)} řádků, sloupce: {', '.join(mapa[:n])}.")

    def nastav(self, zat: dict):
        self.var_g0.set(bool(zat.get("obsahuje_vlastni_tihu", False)))
        self.var_tv.set(_na_text(zat.get("t_vneseni")))
        kv = {k.get("druh"): k for k in zat.get("kombinace", [])}
        for druh, k in self.karty.items():
            d = kv.get(druh, {})
            if d.get("x") is not None:
                k["rezim"].set("tabulka")
                n = len(d["x"])
                k["tab"].nastav([{c: d[c][i] for c in SLOUPCE_KOMB if d.get(c) is not None} for i in range(n)])
                k["fq"].nastav({})
                k["bremena"].set("")
            else:
                k["rezim"].set("q")
                k["fq"].nastav(d)
                k["bremena"].set(_pary_na_text(d.get("bremena")))
                k["tab"].nastav([])
            self._prepni(druh)

    def ziskej(self) -> dict:
        out = {"obsahuje_vlastni_tihu": self.var_g0.get()}
        if self.var_tv.get().strip():
            try:
                out["t_vneseni"] = float(_cislo(self.var_tv.get()))
            except ValueError:
                raise ValueError(f"Čas působení kvazistálé kombinace: neplatné číslo „{self.var_tv.get()}“")
        komb = []
        for druh, nazev in KOMB_ZALOZKY:
            k = self.karty[druh]
            if k["rezim"].get() == "tabulka":
                try:
                    radky = k["tab"].ziskej()
                except ValueError as e:
                    raise ValueError(f"Kombinace {nazev}: {e}")
                if not radky:
                    continue
                d = {"druh": druh}
                for c in SLOUPCE_KOMB:
                    vals = [r.get(c) for r in radky]
                    if all(v is None for v in vals):
                        continue
                    if any(v is None for v in vals):
                        raise ValueError(f"Kombinace {nazev}: sloupec {c} je vyplněn jen částečně.")
                    d[c] = vals
                komb.append(d)
            else:
                d = {"druh": druh, **k["fq"].ziskej()}
                try:
                    br = _text_na_pary(k["bremena"].get())
                except ValueError:
                    raise ValueError(f"Kombinace {nazev}: neplatná břemena „{k['bremena'].get()}“ (zápis F:x; F:x)")
                if br:
                    d["bremena"] = br
                if "q" in d or br:
                    komb.append(d)
        out["kombinace"] = komb
        return out


# ---------------------------------------------------------------------------
# hlavní okno
# ---------------------------------------------------------------------------

class Aplikace(tk.Tk):
    def __init__(self, soubor: str | None = None):
        super().__init__()
        self.title(f"PB posudek {__version__} – nosník z předpjatého betonu")
        self.geometry("1360x860")
        self.minsize(1050, 680)
        self.soubor: Path | None = None
        self.data: dict = {}
        self.model = None
        self.vystup = Path.cwd() / "vystup"
        self._zaneprazdnen = False
        self._nahled_job = None
        self._grafy_cache: dict[str, Figure] = {}
        self._styl()
        self._menu()
        self._lista()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self._zalozka_materialy()
        self._zalozka_prurez()
        self._zalozka_nosnik()
        self._zalozka_vyztuz()
        self._zalozka_zatizeni()
        self._zalozka_nastaveni()
        self._zalozka_vysledky()
        self.stav = tk.StringVar(value="Připraveno")
        sb = ttk.Frame(self)
        sb.pack(fill="x", side="bottom")
        self.progress = ttk.Progressbar(sb, mode="indeterminate", length=160)
        ttk.Label(sb, textvariable=self.stav, anchor="w").pack(side="left", fill="x", padx=6)
        self.bind("<F5>", lambda e: self.spocitej())
        self.bind("<Control-s>", lambda e: self.uloz())
        self.bind("<Control-o>", lambda e: self.otevri())
        self.protocol("WM_DELETE_WINDOW", self._konec)
        if soubor:
            self.nacti(Path(soubor))
        elif PRIKLAD.exists():
            self.nacti(PRIKLAD)
            self.soubor = None
            self.vystup = Path.cwd() / "vystup"
            self.title(self.title() + " – příklad")
        else:
            self.nastav_data(copy.deepcopy(VYCHOZI))

    # --- vzhled -----------------------------------------------------------
    def _styl(self):
        st = ttk.Style(self)
        if "vista" in st.theme_names():
            st.theme_use("vista")
        elif "clam" in st.theme_names():
            st.theme_use("clam")
        st.configure(".", font=("Segoe UI", 9))
        st.configure("Treeview", rowheight=22)
        st.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        st.configure("Velky.TLabel", font=("Segoe UI", 20, "bold"))
        st.configure("Nadpis.TLabel", font=("Segoe UI", 10, "bold"))
        st.configure("Akce.TButton", font=("Segoe UI", 10, "bold"))

    def _menu(self):
        m = tk.Menu(self)
        s = tk.Menu(m, tearoff=False)
        s.add_command(label="Nový", command=self.novy)
        s.add_command(label="Otevřít…", accelerator="Ctrl+O", command=self.otevri)
        s.add_command(label="Uložit", accelerator="Ctrl+S", command=self.uloz)
        s.add_command(label="Uložit jako…", command=lambda: self.uloz(jako=True))
        s.add_separator()
        s.add_command(label="Konec", command=self._konec)
        m.add_cascade(label="Soubor", menu=s)
        v = tk.Menu(m, tearoff=False)
        v.add_command(label="Spočítat", accelerator="F5", command=self.spocitej)
        v.add_command(label="Vytvořit HTML protokol", command=self.protokol)
        v.add_command(label="Otevřít výstupní složku", command=self.otevri_slozku)
        m.add_cascade(label="Výpočet", menu=v)
        n = tk.Menu(m, tearoff=False)
        n.add_command(label="O programu", command=lambda: messagebox.showinfo(
            "O programu", f"PB posudek {__version__}\nPosudek nosníku z předpjatého betonu podle ČSN EN 1992-1-1, "
                          "ČSN EN 1992-2 a ČSN EN 1990.\n\nVýsledky je nutné ověřit odpovědnou osobou."))
        m.add_cascade(label="Nápověda", menu=n)
        self.config(menu=m)

    def _lista(self):
        tb = ttk.Frame(self)
        tb.pack(fill="x", padx=6, pady=4)
        ttk.Button(tb, text="Nový", command=self.novy).pack(side="left")
        ttk.Button(tb, text="Otevřít…", command=self.otevri).pack(side="left", padx=3)
        ttk.Button(tb, text="Uložit", command=self.uloz).pack(side="left")
        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=8)
        self.btn_vypocet = ttk.Button(tb, text="▶  Spočítat (F5)", style="Akce.TButton", command=self.spocitej)
        self.btn_vypocet.pack(side="left")
        self.btn_protokol = ttk.Button(tb, text="HTML protokol", command=self.protokol)
        self.btn_protokol.pack(side="left", padx=3)
        ttk.Button(tb, text="Výstupní složka", command=self.otevri_slozku).pack(side="left")
        self.lbl_souhrn = ttk.Label(tb, text="", style="Nadpis.TLabel")
        self.lbl_souhrn.pack(side="right", padx=6)

    # --- záložky vstupů ---------------------------------------------------
    def _skrol(self, nazev: str) -> ttk.Frame:
        """Záložka se svislým posuvníkem."""
        vnejsi = ttk.Frame(self.nb)
        self.nb.add(vnejsi, text=nazev)
        cv = tk.Canvas(vnejsi, highlightthickness=0)
        sb = ttk.Scrollbar(vnejsi, orient="vertical", command=cv.yview)
        vnitrni = ttk.Frame(cv, padding=8)
        okno = cv.create_window((0, 0), window=vnitrni, anchor="nw")
        vnitrni.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(okno, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return vnitrni

    def _zalozka_materialy(self):
        f = self._skrol("1  Projekt a materiály")
        lf = ttk.LabelFrame(f, text="Projekt", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_projekt = Formular(lf, [("nazev", "Název", "str", None), ("autor", "Vypracoval", "str", None),
                                       ("popis", "Popis", "str", None)])
        self.f_projekt.pack(fill="x")
        lf = ttk.LabelFrame(f, text="Beton", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_beton = Formular(lf, [
            ("trida", "Třída betonu", "choice", TRIDY_BETONU), ("cement", "Cement (S/N/R)", "choice", ["S", "N", "R"]),
            ("Ecm", "E_cm [MPa] (tab. 3.1)", "optfloat", None),
            ("objemova_tiha", "Objemová tíha [kN/m³]", "optfloat", None),
            ("gamma_c", "γ_c", "optfloat", None), ("alpha_cc", "α_cc", "optfloat", None)],
            sloupcu=2, pri_zmene=self._info_materialy)
        self.f_beton.pack(fill="x")
        lf = ttk.LabelFrame(f, text="Předpínací výztuž (hodnoty se doplní podle typu, lze je přepsat)", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_predp = Formular(lf, [
            ("typ", "Typ", "choice", list(PREDPINACI_VYZTUZ)),
            ("druh", "Druh (drat → E_p 205 GPa, lano → 195 GPa)", "choice", list(DRUHY_PREDPINACI_VYZTUZE)),
            ("fpk", "f_pk [MPa]", "optfloat", None),
            ("fp01k", "f_p0,1k [MPa]", "optfloat", None), ("Ep", "E_p [MPa]", "optfloat", None),
            ("Ap_lano", "A_p lana / drátu [mm²]", "optfloat", None), ("d_lana", "Průměr [mm]", "optfloat", None),
            ("trida_relaxace", "Třída relaxace", "choice", ["1", "2", "3"]),
            ("rho1000", "ρ1000 [%]", "optfloat", None), ("gamma_s", "γ_s", "optfloat", None),
            ("taznost", "Tažnost neoslabená ε_uk [‰]", "optfloat", None),
            ("taznost_oslabena", "Tažnost oslabená korozí ε_uk,red [‰] (prázdné = bez oslabení)", "optfloat", None),
            ("zpevneni", "Zpevnění (stoupající větev diagramu)", "bool", True)],
            sloupcu=2, pri_zmene=self._info_materialy)
        self.f_predp.pack(fill="x")
        lf = ttk.LabelFrame(f, text="Betonářská výztuž", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_bet = Formular(lf, [("typ", "Typ", "choice", list(BETONARSKA_VYZTUZ)),
                                   ("fyk", "f_yk [MPa]", "optfloat", None), ("Es", "E_s [MPa]", "optfloat", None),
                                   ("gamma_s", "γ_s", "optfloat", None)], sloupcu=2)
        self.f_bet.pack(fill="x")
        lf = ttk.LabelFrame(f, text="Odvozené charakteristiky", padding=6)
        lf.pack(fill="x", pady=4)
        self.lbl_mat = ttk.Label(lf, text="", justify="left", font=("Consolas", 9))
        self.lbl_mat.pack(anchor="w")
        ttk.Label(f, foreground="#52514e", text=(
            "Po změně třídy betonu nebo typu výztuže se závislé hodnoty (E_cm; f_pk, f_p0,1k, E_p, A_p, třída relaxace, "
            "ρ1000; f_yk, E_s) automaticky přepíší hodnotami podle ČSN EN 1992-1-1 / předvolby; lze je ručně upravit."
        )).pack(anchor="w", pady=4)
        self.f_beton.prom["trida"].trace_add("write", lambda *_: self._zmena_typu("beton"))
        self.f_predp.prom["typ"].trace_add("write", lambda *_: self._zmena_typu("predp"))
        self.f_predp.prom["trida_relaxace"].trace_add("write", lambda *_: self._zmena_typu("relaxace"))
        self.f_predp.prom["druh"].trace_add("write", lambda *_: self._zmena_typu("druh"))
        self.f_bet.prom["typ"].trace_add("write", lambda *_: self._zmena_typu("bet"))

    # --- výchozí hodnoty --------------------------------------------------
    @staticmethod
    def _vych_beton(trida: str) -> dict | None:
        try:
            b = Beton(trida=trida)
        except ValueError:
            return None
        return {"Ecm": float(round(b.Ecm)), "objemova_tiha": 25.0, "gamma_c": 1.5, "alpha_cc": 1.0, "cement": "N"}

    @staticmethod
    def _vych_predp(typ: str) -> dict | None:
        if typ not in PREDPINACI_VYZTUZ:
            return None
        p = PredpinaciVyztuz(typ)
        return {"druh": p.druh, "fpk": p.fpk, "fp01k": p.fp01k, "Ep": p.Ep, "Ap_lano": p.Ap_lano,
                "d_lana": p.d_lana, "trida_relaxace": p.trida_relaxace, "rho1000": p.rho1000,
                "gamma_s": p.gamma_s, "taznost": p.taznost, "zpevneni": p.zpevneni}

    @staticmethod
    def _vych_bet(typ: str) -> dict | None:
        if typ not in BETONARSKA_VYZTUZ:
            return None
        s = BetonarskaVyztuz(typ)
        return {"fyk": s.fyk, "Es": s.Es, "gamma_s": s.gamma_s}

    def _vych_nastaveni(self) -> dict:
        out = {}
        for fl in fields(Nastaveni):
            if fl.default is not MISSING and fl.default is not None and not isinstance(fl.default, bool):
                out[fl.name] = fl.default
        predem = self.f_nosnik.prom["predpeti"].get().startswith("predem")
        out["r_sup"], out["r_inf"] = (1.05, 0.95) if predem else (1.10, 0.90)
        return out

    VYCH_NOSNIK = {"predpeti": "dodatecne", "charakteristiky": "brutto", "pocet_rezu": 41}
    VYCH_PREDEM = {"eta_p1": 3.2, "alpha1": 1.25, "alpha2": 0.19, "eta_p2": 1.2}
    VYCH_PROSTREDI = {"RH": 70.0, "t_s": 3.0}
    VYCH_CAS = {"t0": 7.0, "t_provoz": 120.0, "t_konec": 36500.0}

    def _zmena_typu(self, co: str):
        """Po změně třídy / typu přepíše závislé hodnoty (při načítání souboru jen doplní prázdná pole)."""
        if getattr(self, "_nacitani", False):
            return
        if co == "beton":
            v = self._vych_beton(self.f_beton.prom["trida"].get())
            if v:
                self.f_beton.doplnit({"Ecm": v["Ecm"]}, prepsat=True)
        elif co == "predp":
            v = self._vych_predp(self.f_predp.prom["typ"].get())
            if v:
                v.pop("gamma_s")
                self.f_predp.doplnit(v, prepsat=True)
        elif co == "druh":
            druh = self.f_predp.prom["druh"].get().strip().lower().replace("á", "a")
            if druh in DRUHY_PREDPINACI_VYZTUZE:
                self.f_predp.doplnit({"Ep": DRUHY_PREDPINACI_VYZTUZE[druh]}, prepsat=True)
        elif co == "relaxace":
            try:
                t = int(_cislo(self.f_predp.prom["trida_relaxace"].get()))
            except (TypeError, ValueError):
                return
            if t in RELAXACE_RHO1000:
                self.f_predp.doplnit({"rho1000": RELAXACE_RHO1000[t]}, prepsat=True)
        elif co == "bet":
            v = self._vych_bet(self.f_bet.prom["typ"].get())
            if v:
                v.pop("gamma_s")
                self.f_bet.doplnit(v, prepsat=True)
        elif co == "predpeti":
            stare = {"r_sup": (1.05, 1.10), "r_inf": (0.95, 0.90)}
            nove = self._vych_nastaveni()
            for k, moznosti in stare.items():
                try:
                    akt = _cislo(self.f_nastaveni.prom[k].get())
                except ValueError:
                    continue
                if akt is None or any(abs(akt - m) < 1e-9 for m in moznosti):
                    self.f_nastaveni.doplnit({k: nove[k]}, prepsat=True)

    def _doplnit_vychozi(self):
        """Doplní do prázdných polí výchozí hodnoty (po načtení souboru)."""
        vb = self._vych_beton(self.f_beton.prom["trida"].get())
        if vb:
            self.f_beton.doplnit(vb)
        vp = self._vych_predp(self.f_predp.prom["typ"].get())
        if vp:
            self.f_predp.doplnit(vp)
        else:
            self.f_predp.doplnit({"gamma_s": 1.15, "druh": "lano", "taznost": 35.0})
        vs = self._vych_bet(self.f_bet.prom["typ"].get())
        if vs:
            self.f_bet.doplnit(vs)
        self.f_nosnik.doplnit(self.VYCH_NOSNIK)
        self.f_predem.doplnit(self.VYCH_PREDEM)
        self.f_prostredi.doplnit(self.VYCH_PROSTREDI)
        self.f_cas.doplnit(self.VYCH_CAS)
        self.f_nastaveni.doplnit(self._vych_nastaveni())
        for t in (self.t_kabely, self.t_smyk, self.t_stale, self.t_prom):
            t.nastav(t.ziskej_surove())

    @staticmethod
    def _bez_vychozich(d: dict, vych: dict | None) -> dict:
        """Vynechá hodnoty shodné s výchozími (soubor zůstane přehledný, E_cm se nebere jako zadaný)."""
        if not vych:
            return d
        out = {}
        for k, v in d.items():
            w = vych.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and isinstance(w, (int, float)):
                tol = 0.5 if k == "Ecm" else 1e-9 * max(1.0, abs(w))
                if abs(v - w) <= tol:
                    continue
            elif w is not None and v == w and k not in ("typ", "trida"):
                continue
            out[k] = v
        return out

    def _info_materialy(self):
        try:
            b = self.f_beton.ziskej()
            be = Beton(trida=b.get("trida", "C45/55"), cement=b.get("cement", "N"), Ecm_zadany=b.get("Ecm"),
                       gamma_c=b.get("gamma_c", 1.5), alpha_cc=b.get("alpha_cc", 1.0))
            p = self.f_predp.ziskej()
            pv = PredpinaciVyztuz(**{k: v for k, v in p.items() if k in {f.name for f in fields(PredpinaciVyztuz)}})
            self.lbl_mat.configure(text=(
                f"Beton {be.trida}:  f_ck = {be.fck:g}   f_cm = {be.fcm:g}   f_ctm = {be.fctm:.2f}   "
                f"f_ctk,0,05 = {be.fctk005:.2f}   E_cm = {be.Ecm:.0f}   f_cd = {be.fcd:.2f}   f_ctd = {be.fctd:.2f} MPa\n"
                f"Předpínací výztuž {pv.typ}:  f_pk = {pv.fpk:g}   f_p0,1k = {pv.fp01k:g}   E_p = {pv.Ep:g} MPa   "
                f"A_p = {pv.Ap_lano:g} mm²   třída relaxace {pv.trida_relaxace}, ρ1000 = {pv.rho1000:g} %\n"
                f"{'Dráty' if pv.druh == 'drat' else 'Lana'}, diagram MSÚ {'se zpevněním' if pv.zpevneni else 'bez zpevnění'}:"
                f"   f_pd = {pv.fpd:.0f} MPa   ε_uk = {pv.taznost:g} ‰   ε_ud = 0,9·ε_uk = {pv.eps_ud * 1e3:.1f} ‰"
                f"   σ_p(ε_ud) = {float(pv.sigma_msu(pv.eps_ud)):.0f} MPa\n"
                + (f"Oslabená korozí (sklon zpevnění se nemění):   ε_uk,red = {pv.taznost_oslabena:g} ‰   "
                   f"ε_ud,red = {pv.eps_ud_red * 1e3:.1f} ‰   σ_p(ε_ud,red) = {float(pv.sigma_msu(pv.eps_ud_red)):.0f} MPa\n"
                   if pv.oslabena_taznost else "") +
                f"σ_p,max = min(0,8·f_pk; 0,9·f_p0,1k) = {min(0.8 * pv.fpk, 0.9 * pv.fp01k):.0f} MPa,   "
                f"σ_pm0 ≤ min(0,75·f_pk; 0,85·f_p0,1k) = {min(0.75 * pv.fpk, 0.85 * pv.fp01k):.0f} MPa"))
        except Exception as e:  # noqa: BLE001
            self.lbl_mat.configure(text=f"⚠ {e}")

    def _zalozka_prurez(self):
        z = ttk.Frame(self.nb, padding=8)
        self.nb.add(z, text="2  Průřez")
        lev = ttk.Frame(z)
        lev.pack(side="left", fill="both", expand=False)
        pr = ttk.Frame(z)
        pr.pack(side="left", fill="both", expand=True, padx=(10, 0))
        rf = ttk.Frame(lev)
        rf.pack(fill="x")
        ttk.Label(rf, text="Způsob zadání:").pack(side="left")
        self.rezim_prurezu = tk.StringVar(value="vrstvy")
        for val, txt in (("vrstvy", "lichoběžníkové vrstvy"), ("obrys", "obrys (polygon)"), ("obdelnik", "obdélník")):
            ttk.Radiobutton(rf, text=txt, value=val, variable=self.rezim_prurezu,
                            command=self._prepni_prurez).pack(side="left", padx=4)
        self.pr_ramec = ttk.Frame(lev)
        self.pr_ramec.pack(fill="both", expand=True, pady=6)
        self.t_vrstvy = Tabulka(self.pr_ramec, [
            ("b_d", "b dole [mm]", 90, "float", None), ("b_h", "b nahoře [mm]", 90, "float", None),
            ("h", "výška [mm]", 90, "float", None)], pri_zmene=self._naplanuj_nahled, vyska=12)
        self.t_obrys = Tabulka(self.pr_ramec, [("y", "y [mm]", 90, "float", None), ("z", "z [mm]", 90, "float", None)],
                               pri_zmene=self._naplanuj_nahled, vyska=12)
        self.var_otvory = tk.StringVar()
        self.f_obdelnik = Formular(self.pr_ramec, [("b", "šířka b [mm]", "float", None),
                                                   ("h", "výška h [mm]", "float", None)],
                                   pri_zmene=self._naplanuj_nahled)
        self.ram_otvory = ttk.Frame(self.pr_ramec)
        ttk.Label(self.ram_otvory, text="Otvory – JSON seznam polygonů [[[y,z],…], …]:").pack(anchor="w")
        e = ttk.Entry(self.ram_otvory, textvariable=self.var_otvory)
        e.pack(fill="x")
        self.var_otvory.trace_add("write", lambda *_: self._naplanuj_nahled())
        dol = ttk.Frame(lev)
        dol.pack(fill="x")
        ttk.Label(dol, text="Obvod vystavený vysychání u [mm] (prázdné = celý obvod):").pack(side="left")
        self.var_obvod = tk.StringVar()
        ttk.Entry(dol, textvariable=self.var_obvod, width=10).pack(side="left", padx=4)
        self.lbl_prurez = ttk.Label(lev, text="", justify="left", font=("Consolas", 9))
        self.lbl_prurez.pack(anchor="w", pady=6)
        self.g_prurez = Graf(pr, figsize=(5, 5))
        self.g_prurez.pack(fill="both", expand=True)

    def _prepni_prurez(self):
        for w in (self.t_vrstvy, self.t_obrys, self.f_obdelnik, self.ram_otvory):
            w.pack_forget()
        r = self.rezim_prurezu.get()
        if r == "vrstvy":
            self.t_vrstvy.pack(fill="both", expand=True)
        elif r == "obrys":
            self.t_obrys.pack(fill="both", expand=True)
            self.ram_otvory.pack(fill="x", pady=4)
        else:
            self.f_obdelnik.pack(fill="x")
        self._naplanuj_nahled()

    def _zalozka_nosnik(self):
        z = ttk.Frame(self.nb, padding=8)
        self.nb.add(z, text="3  Nosník a předpětí")
        horni = ttk.Frame(z)
        horni.pack(fill="x")
        lf = ttk.LabelFrame(horni, text="Nosník", padding=6)
        lf.pack(side="left", fill="x", expand=True)
        self.f_nosnik = Formular(lf, [
            ("L", "Délka nosníku L [m]", "float", None), ("L0", "Rozpětí L0 [m]", "optfloat", None),
            ("predpeti", "Předpětí", "choice", ["dodatecne", "predem"]),
            ("charakteristiky", "Průřezové char.", "choice", ["brutto", "idealni"]),
            ("pocet_rezu", "Počet řezů", "optint", None),
            ("pocet_napinani", "Počet kroků napínání", "optint", None),
            ("postup_napinani", "Postup napínání σ:min; …", "pary", None)], sloupcu=3,
            pri_zmene=self._naplanuj_nahled)
        self.f_nosnik.pack(fill="x")
        self.f_nosnik.prom["predpeti"].trace_add("write", lambda *_: self._zmena_typu("predpeti"))
        lf = ttk.LabelFrame(horni, text="Předem předpjaté prvky", padding=6)
        lf.pack(side="left", fill="x", padx=(8, 0))
        self.f_predem = Formular(lf, [("relaxace_pred_uvolnenim_h", "Čas do uvolnění [h]", "optfloat", None),
                                      ("eta_p1", "η_p1", "optfloat", None), ("alpha1", "α1", "optfloat", None),
                                      ("alpha2", "α2", "optfloat", None), ("eta_p2", "η_p2", "optfloat", None)],
                                 sloupcu=2)
        self.f_predem.pack(fill="x")
        lf = ttk.LabelFrame(z, text="Kabely / skupiny lan  (z = výška od spodního okraje [mm], x [m])", padding=6)
        lf.pack(fill="both", expand=True, pady=6)
        self.t_kabely = Tabulka(lf, [
            ("nazev", "Název", 70, "str", None), ("pocet_lan", "Lan", 45, "int", None),
            ("geometrie", "Geometrie", 85, "choice", ["parabola", "polygon", "primka"]),
            ("z_L", "z vlevo", 60, "optfloat", None), ("z_S", "z vrchol", 60, "optfloat", None),
            ("z_P", "z vpravo", 60, "optfloat", None), ("x_S", "x vrcholu", 65, "optfloat", None),
            ("body", "Polygon – body x:z; …", 200, "pary", None), ("polomery", "Poloměry R [m]; …", 110, "seznam", None),
            ("sigma_max", "σ_p,max", 65, "float", None),
            ("napinani", "Napínání", 70, "choice", ["levy", "pravy", "oba"]), ("mu", "μ", 50, "optfloat", None),
            ("k", "k [rad/m]", 65, "optfloat", None), ("pokluz", "Pokluz [mm]", 70, "optfloat", None),
            ("d_kanalku", "∅ kanálku", 70, "optfloat", None),
            ("postup", "Postup napínání σ:min; … (jen tento kabel)", 200, "pary", None)],
            pri_zmene=self._naplanuj_nahled, vyska=5,
            vychozi={"geometrie": "parabola", "napinani": "levy", "mu": 0.19, "k": 0.005, "pokluz": 6.0,
                     "d_kanalku": 0.0})
        self.t_kabely.pack(fill="both", expand=True)
        ttk.Label(lf, foreground="#52514e", text=(
            "parabola: z vlevo / z vrchol / z vpravo (+ x vrcholu, výchozí L/2); primka: z vlevo (+ z vpravo); "
            "polygon: body „0:530; 3.18:115; 8.78:115; 11.96:530“ a volitelně poloměry zaoblení „0; 29; 29; 0“.\n"
            "Postup napínání (dodatečné předpětí): napětí na lisu [MPa]:doba podržení [min] postupně, např. "
            "„1200:2; 800:0; 1325.4:5“, nakonec se kabel napne na σ_p,max a zakotví. Pole „Postup napínání“ "
            "u nosníku platí pro všechny kabely, sloupec v tabulce jen pro daný kabel."), justify="left"
                  ).pack(anchor="w")
        self.g_kabely = Graf(z, figsize=(9, 2.6))
        self.g_kabely.pack(fill="both", expand=True)

    def _zalozka_vyztuz(self):
        z = ttk.Frame(self.nb, padding=8)
        self.nb.add(z, text="4  Výztuž")
        lf = ttk.LabelFrame(z, text="Podélná betonářská výztuž", padding=6)
        lf.pack(fill="both", expand=True)
        self.t_vyztuz = Tabulka(lf, [("nazev", "Název", 160, "str", None), ("z", "z [mm]", 90, "float", None),
                                     ("As", "A_s [mm²]", 90, "float", None),
                                     ("phi", "Ø [mm] (trhliny)", 100, "optfloat", None)], pri_zmene=self._naplanuj_nahled)
        self.t_vyztuz.pack(fill="both", expand=True)
        kal = ttk.Frame(lf)
        kal.pack(fill="x", pady=4)
        ttk.Label(kal, text="Kalkulačka A_s:  počet").pack(side="left")
        self.var_n = tk.StringVar(value="4")
        self.var_fi = tk.StringVar(value="16")
        ttk.Entry(kal, textvariable=self.var_n, width=5).pack(side="left", padx=3)
        ttk.Label(kal, text="× Ø [mm]").pack(side="left")
        ttk.Entry(kal, textvariable=self.var_fi, width=5).pack(side="left", padx=3)
        self.lbl_as = ttk.Label(kal, text="")
        self.lbl_as.pack(side="left", padx=6)

        def prepocti(*_):
            try:
                n, fi = float(self.var_n.get()), float(self.var_fi.get())
                self.lbl_as.configure(text=f"= {n * np.pi * fi ** 2 / 4:.0f} mm²")
            except ValueError:
                self.lbl_as.configure(text="")
        self.var_n.trace_add("write", prepocti)
        self.var_fi.trace_add("write", prepocti)
        prepocti()
        lf = ttk.LabelFrame(z, text="Smyková výztuž (úseky od–do v m; prázdné = celý nosník)", padding=6)
        lf.pack(fill="both", expand=True, pady=6)
        self.t_smyk = Tabulka(lf, [("Asw", "A_sw [mm²] (všechny střižnosti)", 190, "float", None),
                                   ("s", "s [mm]", 80, "float", None), ("alpha", "α [°]", 70, "optfloat", None),
                                   ("od", "od [m]", 70, "optfloat", None), ("do", "do [m]", 70, "optfloat", None)],
                              vychozi={"alpha": 90.0})
        self.t_smyk.pack(fill="both", expand=True)
        lf = ttk.LabelFrame(z, text="Oslabení výztuže korozí – zmenšení plochy [%] (uplatní se v posudku pro "
                                    "aktuální stáří a na konci životnosti)", padding=6)
        lf.pack(fill="x", pady=(0, 6))
        self.f_degradace = Formular(lf, [
            ("oslabeni_predpinaci", "Oslabení předpínací výztuže [%]", "optfloat", None),
            ("oslabeni_betonarske", "Oslabení betonářské výztuže [%]", "optfloat", None),
            ("oslabeni_smykove", "Oslabení smykové výztuže [%]", "optfloat", None)], sloupcu=3)
        self.f_degradace.pack(fill="x")
        ttk.Label(lf, foreground="#52514e", text=(
            "Předpínací výztuž: zmenší se předpínací síla P = σ_p·A_p (napětí ve zbylé výztuži se nemění) i A_p "
            "v MSÚ; betonářská a smyková výztuž: plocha v MSÚ. Platí od aktuálního stáří (karta 5), bez něj jen "
            "pro konec životnosti. Tažnost předpínací výztuže oslabená korozí se zadává na kartě 1 a platí "
            "ve stejných fázích.")).pack(anchor="w")

    def _zalozka_zatizeni(self):
        z = ttk.Frame(self.nb, padding=8)
        self.nb.add(z, text="5  Zatížení a čas")
        horni = ttk.Frame(z)
        horni.pack(fill="x")
        lf = ttk.LabelFrame(horni, text="Prostředí", padding=6)
        lf.pack(side="left", fill="x", expand=True)
        self.f_prostredi = Formular(lf, [("RH", "Relativní vlhkost RH [%]", "float", None),
                                         ("t_s", "Konec ošetřování t_s [dny]", "float", None)])
        self.f_prostredi.pack(fill="x")
        lf = ttk.LabelFrame(horni, text="Časová osa (stáří betonu)", padding=6)
        lf.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.f_cas = Formular(lf, [("t0", "Napínání / uvolnění t0 [dny]", "float", None),
                                   ("t_provoz", "Uvedení do provozu [dny]", "float", None),
                                   ("t_akt", "Aktuální stáří [dny] (prázdné = neposuzovat)", "optfloat", None),
                                   ("t_konec", "Konec životnosti [dny]", "float", None)])
        self.f_cas.pack(fill="x")
        rf = ttk.Frame(z)
        rf.pack(fill="x", pady=(8, 2))
        ttk.Label(rf, text="Vnější zatížení:", style="Nadpis.TLabel").pack(side="left")
        self.zpusob_zat = tk.StringVar(value="kombinace")
        for val, txt in (("kombinace", "přímo kombinacemi (6.10a, 6.10b, charakteristická, častá, kvazistálá)"),
                         ("zatezovaci_stavy", "zatěžovacími stavy s automatickými kombinacemi")):
            ttk.Radiobutton(rf, text=txt, value=val, variable=self.zpusob_zat,
                            command=self._prepni_zatizeni).pack(side="left", padx=6)
        self.ram_zat = ttk.Frame(z)
        self.ram_zat.pack(fill="both", expand=True)
        self.p_komb = KombinacePanel(self.ram_zat, pri_zmene=self._naplanuj_nahled)
        self.g_komb = Graf(self.p_komb, figsize=(9, 2.6))
        self.g_komb.pack(fill="both", expand=True, pady=(6, 0))
        self.ram_zs = ttk.Frame(self.ram_zat)
        z = self.ram_zs
        lf = ttk.LabelFrame(z, text="Stálá zatížení (vlastní tíha nosníku se počítá automaticky)", padding=6)
        lf.pack(fill="both", expand=True, pady=6)
        self.t_stale = Tabulka(lf, [
            ("nazev", "Název", 200, "str", None), ("q", "q [kN/m]", 70, "optfloat", None),
            ("od", "od [m]", 60, "optfloat", None), ("do", "do [m]", 60, "optfloat", None),
            ("bremena", "Břemena F:x; … [kN:m]", 170, "pary", None), ("t", "t vnesení [dny]", 90, "optfloat", None),
            ("gamma", "γ_G,sup", 60, "optfloat", None), ("gamma_inf", "γ_G,inf", 60, "optfloat", None)], vyska=5,
            vychozi={"gamma": 1.35, "gamma_inf": 1.0})
        self.t_stale.pack(fill="both", expand=True)
        lf = ttk.LabelFrame(z, text="Proměnná zatížení (stejná „skupina“ = působí současně, např. LM1 = TS + UDL)",
                            padding=6)
        lf.pack(fill="both", expand=True)
        self.t_prom = Tabulka(lf, [
            ("nazev", "Název", 150, "str", None), ("q", "q [kN/m]", 65, "optfloat", None),
            ("od", "od [m]", 55, "optfloat", None), ("do", "do [m]", 55, "optfloat", None),
            ("bremena", "Pevná břemena F:x; …", 140, "pary", None),
            ("sily", "Pohyblivá břemena [kN]; …", 150, "seznam", None),
            ("rozestupy", "Rozestupy [m]; …", 110, "seznam", None),
            ("psi0", "ψ0", 45, "optfloat", None), ("psi1", "ψ1", 45, "optfloat", None),
            ("psi2", "ψ2", 45, "optfloat", None), ("gamma", "γ_Q", 50, "optfloat", None),
            ("skupina", "Skupina", 80, "str", None)], vyska=5,
            vychozi={"psi0": 0.0, "psi1": 0.0, "psi2": 0.0, "gamma": 1.5})
        self.t_prom.pack(fill="both", expand=True)

    def _prepni_zatizeni(self):
        self.p_komb.pack_forget()
        self.ram_zs.pack_forget()
        if self.zpusob_zat.get() == "kombinace":
            self.p_komb.pack(fill="both", expand=True)
        else:
            self.ram_zs.pack(fill="both", expand=True)
        self._naplanuj_nahled()

    def _zalozka_nastaveni(self):
        f = self._skrol("6  Nastavení posouzení")
        pole = []
        for fl in fields(Nastaveni):
            vych = fl.default if fl.default is not MISSING else None
            if isinstance(vych, bool):
                typ = "bool"
            elif fl.name in VOLBY_NASTAVENI:
                typ = "choice"
            else:
                typ = "optfloat"
            popis = POPISKY_NASTAVENI.get(fl.name, fl.name)
            if vych not in (None, "") and typ != "bool":
                popis += f"   (výchozí {vych})"
            pole.append((fl.name, popis, typ, vych if typ == "bool" else VOLBY_NASTAVENI.get(fl.name)))
        ttk.Label(f, text=("Hodnoty jsou předvyplněny podle doporučení ČSN EN 1992-1-1; r_sup a r_inf se mění podle "
                           "typu předpětí (5.10.9). Hodnoty shodné s výchozími se do souboru nezapisují."),
                  foreground="#52514e").pack(anchor="w", pady=(0, 6))
        self.f_nastaveni = Formular(f, pole, sloupcu=2)
        self.f_nastaveni.pack(fill="x")

    # --- výsledky -------------------------------------------------------
    def _zalozka_vysledky(self):
        z = ttk.Frame(self.nb, padding=8)
        self.nb.add(z, text="7  Výsledky")
        self.z_vysledky = z
        karty = ttk.Frame(z)
        karty.pack(fill="x")
        self.karty = {}
        for ms in ("MSÚ", "MSP", "Celkem"):
            k = ttk.LabelFrame(karty, text=f"{ms} – nejvyšší využití" if ms != "Celkem" else "Výsledek", padding=6)
            k.pack(side="left", fill="x", expand=True, padx=(0, 8))
            v = ttk.Label(k, text="–", style="Velky.TLabel")
            v.pack(anchor="w")
            d = ttk.Label(k, text="", foreground="#52514e")
            d.pack(anchor="w")
            self.karty[ms] = (v, d)
        self._fr_karty = karty
        # upozornění (nejsou posudky) – zobrazí se jen, existují-li
        self.lbl_upozorneni = ttk.Label(z, text="", foreground="#8a5a00", background="#fff4dc",
                                        wraplength=1100, justify="left", padding=6)
        pan = ttk.PanedWindow(z, orient="horizontal")
        pan.pack(fill="both", expand=True, pady=(8, 0))
        lev = ttk.Frame(pan)
        pan.add(lev, weight=2)
        sl = ("ms", "nazev", "eta", "faze", "komb", "x", "ed", "rd", "j")
        self.t_vys = ttk.Treeview(lev, columns=sl, show="headings", selectmode="browse")
        for k, t, w, a in (("ms", "MS", 40, "w"), ("nazev", "Posudek", 200, "w"), ("eta", "η", 56, "e"),
                           ("faze", "Fáze", 140, "w"), ("komb", "Kombinace", 90, "w"), ("x", "x [m]", 50, "e"),
                           ("ed", "E_d", 62, "e"), ("rd", "R_d", 62, "e"), ("j", "", 34, "w")):
            self.t_vys.heading(k, text=t, command=lambda c=k: self._serad(c))
            self.t_vys.column(k, width=w, anchor=a, stretch=k in ("nazev", "faze"))
        self.t_vys.tag_configure("ok", background="#e7f5e7")
        self.t_vys.tag_configure("warn", background="#fff4dc")
        self.t_vys.tag_configure("bad", background="#fbe9e9", foreground="#b42323")
        sb = ttk.Scrollbar(lev, orient="vertical", command=self.t_vys.yview)
        self.t_vys.configure(yscrollcommand=sb.set)
        self.t_vys.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.t_vys.bind("<<TreeviewSelect>>", self._vyber_posudek)
        prav = ttk.Frame(pan)
        pan.add(prav, weight=3)
        self.pan_vys = pan
        hl = ttk.Frame(prav)
        hl.pack(fill="x")
        ttk.Label(hl, text="Graf:").pack(side="left")
        self.var_graf = tk.StringVar()
        self.cb_graf = ttk.Combobox(hl, textvariable=self.var_graf, state="readonly", width=44)
        self.cb_graf.pack(side="left", padx=4)
        self.cb_graf.bind("<<ComboboxSelected>>", lambda e: self._zobraz_graf(self.var_graf.get()))
        self.lbl_detail = ttk.Label(prav, text="", foreground="#52514e", wraplength=640, justify="left")
        self.lbl_detail.pack(fill="x", pady=2)
        self.g_vys = Graf(prav, figsize=(8, 5))
        self.g_vys.pack(fill="both", expand=True)

    # --- data <-> formuláře --------------------------------------------
    def nastav_data(self, d: dict):
        self._nacitani = True
        try:
            self._nastav_data(d)
            self._doplnit_vychozi()
        finally:
            self._nacitani = False
        self._info_materialy()
        self._naplanuj_nahled()

    def _nastav_data(self, d: dict):
        self.data = copy.deepcopy(d)
        self.f_projekt.nastav(d.get("projekt", {}))
        self.f_beton.nastav(d.get("beton", {}))
        self.f_predp.nastav(d.get("predpinaci_vyztuz", {}))
        self.f_bet.nastav(d.get("betonarska_vyztuz", {}))
        pr = d.get("prurez", {})
        if "vrstvy" in pr:
            self.rezim_prurezu.set("vrstvy")
        elif "obrys" in pr:
            self.rezim_prurezu.set("obrys")
        else:
            self.rezim_prurezu.set("obdelnik")
        self.t_vrstvy.nastav([{"b_d": a, "b_h": b, "h": c} for a, b, c in pr.get("vrstvy", [])])
        self.t_obrys.nastav([{"y": a, "z": b} for a, b in pr.get("obrys", [])])
        self.var_otvory.set(json.dumps(pr["otvory"]) if pr.get("otvory") else "")
        self.f_obdelnik.nastav({"b": pr.get("b"), "h": pr.get("h")})
        self.var_obvod.set(_na_text(pr.get("obvod_vysychani")))
        self.f_nosnik.nastav(d.get("nosnik", {}))
        self.f_predem.nastav(d.get("predem", {}))
        self.t_kabely.nastav(d.get("kabel", []))
        self.t_vyztuz.nastav(d.get("vyztuz", []))
        self.t_smyk.nastav(d.get("smykova_vyztuz", []))
        self.f_degradace.nastav(d.get("degradace", {}))
        self.f_prostredi.nastav(d.get("prostredi", {}))
        self.f_cas.nastav(d.get("casova_osa", {}))
        zat = d.get("zatizeni", {})
        self.t_stale.nastav(zat.get("stale", []))
        prom = []
        for r in zat.get("promenne", []):
            r = dict(r)
            if "pohyblive" in r:
                r["sily"] = r["pohyblive"].get("sily")
                r["rozestupy"] = r["pohyblive"].get("rozestupy")
                r.pop("pohyblive")
            prom.append(r)
        self.t_prom.nastav(prom)
        self.p_komb.nastav(zat)
        self.zpusob_zat.set(zat.get("zpusob", "kombinace" if zat.get("kombinace") else "zatezovaci_stavy"))
        self._prepni_zatizeni()
        self.f_nastaveni.nastav(d.get("posouzeni", {}))
        self._prepni_prurez()

    def ziskej_data(self) -> dict:
        d = copy.deepcopy(self.data)
        d["projekt"] = {**d.get("projekt", {}), **self.f_projekt.ziskej()}
        beton = self.f_beton.ziskej()
        vb = self._vych_beton(beton.get("trida", ""))
        d["beton"] = self._bez_vychozich(beton, {k: v for k, v in (vb or {}).items() if k != "cement"})
        predp = self.f_predp.ziskej()
        d["predpinaci_vyztuz"] = self._bez_vychozich(predp, self._vych_predp(predp.get("typ", "")))
        bet = self.f_bet.ziskej()
        d["betonarska_vyztuz"] = self._bez_vychozich(bet, self._vych_bet(bet.get("typ", "")))
        d["prurez"] = self._prurez_data()
        d["nosnik"] = self.f_nosnik.ziskej()
        d["predem"] = self.f_predem.ziskej()
        d["kabel"] = self.t_kabely.ziskej()
        d["vyztuz"] = self.t_vyztuz.ziskej()
        d["smykova_vyztuz"] = self.t_smyk.ziskej()
        d["degradace"] = {k: v for k, v in self.f_degradace.ziskej().items() if v}
        d["prostredi"] = self.f_prostredi.ziskej()
        d["casova_osa"] = self.f_cas.ziskej()
        prom = []
        for r in self.t_prom.ziskej():
            sily, roz = r.pop("sily", None), r.pop("rozestupy", None)
            if sily:
                r["pohyblive"] = {"sily": sily, "rozestupy": roz or []}
            prom.append(r)
        zat = {k: v for k, v in d.get("zatizeni", {}).items()
               if k not in ("obsahuje_vlastni_tihu", "t_vneseni", "kombinace")}
        zat.update({"zpusob": self.zpusob_zat.get(), **self.p_komb.ziskej(),
                    "stale": self.t_stale.ziskej(), "promenne": prom})
        d["zatizeni"] = zat
        d["posouzeni"] = self._bez_vychozich(self.f_nastaveni.ziskej(), self._vych_nastaveni())
        d["posouzeni"] = {k: v for k, v in d["posouzeni"].items()
                          if not (k == "hlavni_napeti" and v is True)}
        if not d["kabel"]:
            raise ValueError("Zadejte alespoň jeden kabel.")
        return d

    def _prurez_data(self) -> dict:
        r = self.rezim_prurezu.get()
        out: dict = {}
        nazev = self.data.get("prurez", {}).get("nazev")
        if nazev:
            out["nazev"] = nazev
        if r == "vrstvy":
            out["vrstvy"] = [[x["b_d"], x["b_h"], x["h"]] for x in self.t_vrstvy.ziskej()]
            if not out["vrstvy"]:
                raise ValueError("Průřez: zadejte alespoň jednu vrstvu.")
        elif r == "obrys":
            out["obrys"] = [[x["y"], x["z"]] for x in self.t_obrys.ziskej()]
            if len(out["obrys"]) < 3:
                raise ValueError("Průřez: obrys musí mít alespoň 3 body.")
            if self.var_otvory.get().strip():
                try:
                    out["otvory"] = json.loads(self.var_otvory.get())
                except json.JSONDecodeError as e:
                    raise ValueError(f"Otvory: neplatný zápis ({e})")
        else:
            out.update(self.f_obdelnik.ziskej())
        if self.var_obvod.get().strip():
            out["obvod_vysychani"] = float(_cislo(self.var_obvod.get()))
        return out

    # --- náhledy ----------------------------------------------------------
    def _naplanuj_nahled(self):
        if self._nahled_job:
            self.after_cancel(self._nahled_job)
        self._nahled_job = self.after(350, self._nahled)

    def _nahled(self):
        self._nahled_job = None
        # vedení kabelů se kreslí samostatně – nesmí čekat na platnost celého modelu (zatížení, materiály …)
        try:
            self._nahled_kabely()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        try:
            d = self.ziskej_data()
            m = model_ze_slovniku(d)
        except Exception as e:  # noqa: BLE001
            self.lbl_prurez.configure(text=f"⚠ {e}")
            return
        P = m.prurez
        self.lbl_prurez.configure(text=(
            f"h   = {P.h:10.1f} mm\nA_c = {P.A:10.0f} mm²\nz_t = {P.zt:10.1f} mm (od spodu)\n"
            f"I_c = {P.I:10.4g} mm⁴\nW_h = {P.W_h:10.4g} mm³\nW_d = {P.W_d:10.4g} mm³\n"
            f"u   = {P.u:10.0f} mm,  h0 = {P.h0:.1f} mm\ng0  = {P.A * 1e-6 * m.beton.objemova_tiha:10.2f} kN/m\n"
            f"A_p = {m.Ap:10.0f} mm² ({sum(k.pocet_lan for k in m.kabely)} lan)"))
        # průřez
        fig = self.g_prurez.fig
        fig.clear()
        ax = fig.add_subplot(111)
        ax.add_patch(Polygon(P.obrys, closed=True, fc="#e9eef6", ec="#52514e", lw=1.2))
        for o in P.otvory:
            ax.add_patch(Polygon(o, closed=True, fc="white", ec="#52514e"))
        ax.axhline(P.zt, color="#52514e", lw=0.8, ls="-.")
        xs = m.L0 / 2 + (m.L - m.L0) / 2
        for j, k in enumerate(m.kabely):
            zz = float(k.geometrie.z_v(xs))
            r = max(k.d_kanalku / 2, P.h / 60)
            ax.add_patch(Circle((0, zz), r, fc=grafy.C[j % 8], ec="white", lw=1.2))
            ax.text(P.b_max * 0.08 + r, zz, k.nazev, va="center", fontsize=8)
        for v in m.vyztuz:
            w = P.sirka(v.z)[0]
            ax.plot([-w / 2 + 30, w / 2 - 30], [v.z, v.z], color="black", lw=2.5)
        ax.set_aspect("equal")
        y0, y1 = P.obrys[:, 0].min(), P.obrys[:, 0].max()
        ax.set_xlim(y0 - 0.1 * (y1 - y0), y1 + 0.25 * (y1 - y0))
        ax.set_ylim(-0.05 * P.h, 1.05 * P.h)
        ax.set_title("Průřez ve středu rozpětí (– · – těžiště)", fontsize=10)
        ax.set_xlabel("y [mm]")
        ax.set_ylabel("z [mm]")
        fig.tight_layout()
        self.g_prurez.canvas.draw_idle()
        self._nahled_kombinaci(m)

    def _nahled_kabely(self):
        """Náhled vedení kabelů jen z nosníku, průřezu a tabulky kabelů; chybné řádky se vypíší do grafu."""
        chyby: list[str] = []
        L = L0 = None
        try:
            n = self.f_nosnik.ziskej()
            L = float(n["L"])
            L0 = float(n.get("L0") or L)
            if L <= 0:
                raise ValueError("Délka nosníku L musí být kladná.")
        except Exception as e:  # noqa: BLE001
            chyby.append(str(e))
            L = None
        h = zt = None
        try:
            P = _prurez(self._prurez_data())
            h, zt = P.h, P.zt
        except Exception:  # noqa: BLE001
            pass  # chybu průřezu hlásí záložka Průřez; vedení kabelů lze nakreslit i bez něj
        cary = []
        if L:
            for c, r, chyba in self.t_kabely.ziskej_radky():
                if chyba is None:
                    try:
                        g, _ = geometrie_kabelu(r, L, c - 1)
                        cary.append((c, r.get("nazev") or f"K{c}", np.asarray(g.x), np.asarray(g.z)))
                        continue
                    except Exception as e:  # noqa: BLE001
                        chyba = str(e)
                chyby.append(chyba)
            if not self.t_kabely.tree.get_children():
                chyby.append("Zadejte alespoň jeden kabel.")
        if h is None:
            h = max([float(z.max()) for *_, z in cary] + [100.0]) * 1.15
        fig = self.g_kabely.fig
        fig.clear()
        ax = fig.add_subplot(111)
        Lk = L or 1.0
        if L:
            ax.fill_between([0, L], 0, h, color="#e9eef6", lw=0)
            for xs_ in ((L - L0) / 2, (L + L0) / 2):
                ax.plot([xs_], [-0.06 * h], marker="^", ms=9, color="#52514e")
        if zt is not None:
            ax.axhline(zt, color="#52514e", lw=0.8, ls="-.")
        for c, nazev, x, z in cary:
            ax.plot(x, z, color=grafy.C[(c - 1) % 8], lw=2, label=nazev)
        ax.set_xlim(-0.2, Lk + 0.2)
        ax.set_ylim(-0.12 * h, 1.05 * h)
        ax.set_xlabel("x [m]")
        ax.set_ylabel("z [mm]")
        if cary:
            ax.legend(ncol=len(cary), fontsize=8, loc="upper center")
        if chyby:
            ax.text(0.01, 0.97, "\n".join(f"⚠ {t}" for t in chyby[:4]), transform=ax.transAxes, va="top",
                    ha="left", fontsize=8, color="#b3261e",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#b3261e", alpha=0.9))
        fig.tight_layout()
        self.g_kabely.canvas.draw_idle()

    def _nahled_kombinaci(self, m):
        fig = self.g_komb.fig
        fig.clear()
        if not m.kombinace_vstup:
            self.g_komb.canvas.draw_idle()
            return
        axm, axv = fig.add_subplot(121), fig.add_subplot(122)
        xa = (m.L - m.L0) / 2
        x = np.union1d(np.linspace(0, m.L, 201), [xa, xa + m.L0])
        for j, k in enumerate(m.kombinace_vstup):
            try:
                o = k.obalka(x, m.L, xa, xa + m.L0)
            except Exception:  # noqa: BLE001
                continue
            c = grafy.C[j % 8]
            axm.plot(x, o.M_max, color=c, lw=1.6, label=DRUHY_KOMBINACI.get(k.druh, k.druh))
            if not np.allclose(o.M_min, o.M_max):
                axm.plot(x, o.M_min, color=c, lw=1.0, ls="--")
            axv.plot(x, o.V_max, color=c, lw=1.6)
            if not np.allclose(o.V_min, o.V_max):
                axv.plot(x, o.V_min, color=c, lw=1.0, ls="--")
        axm.invert_yaxis()
        axm.set(title="M ze zadaných kombinací [kNm]", xlabel="x [m]")
        axv.set(title="V ze zadaných kombinací [kN]", xlabel="x [m]")
        axm.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        self.g_komb.canvas.draw_idle()

    # --- soubory ----------------------------------------------------------
    def novy(self):
        self.soubor = None
        self.nastav_data(copy.deepcopy(VYCHOZI))
        self._vymaz_vysledky()
        self.title(f"PB posudek {__version__} – nový")

    def otevri(self):
        p = filedialog.askopenfilename(title="Otevřít vstupní soubor",
                                       filetypes=[("Vstupní data", "*.toml *.json"), ("Všechny soubory", "*.*")],
                                       initialdir=str(PRIKLAD.parent) if PRIKLAD.exists() else None)
        if p:
            self.nacti(Path(p))

    def nacti(self, p: Path):
        try:
            d = nacti_soubor(p)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Chyba při čtení", f"{p}\n\n{e}")
            return
        self.soubor = p
        self.vystup = p.parent / f"vystup_{p.stem}"
        self.nastav_data(d)
        self._vymaz_vysledky()
        self.title(f"PB posudek {__version__} – {p.name}")
        self.stav.set(f"Načteno: {p}")

    def uloz(self, jako: bool = False):
        try:
            d = self.ziskej_data()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Neplatná data", str(e))
            return
        if jako or self.soubor is None:
            p = filedialog.asksaveasfilename(title="Uložit vstupní soubor", defaultextension=".toml",
                                             filetypes=[("TOML", "*.toml"), ("JSON", "*.json")])
            if not p:
                return
            self.soubor = Path(p)
            self.vystup = self.soubor.parent / f"vystup_{self.soubor.stem}"
        d = {k: v for k, v in d.items() if v not in ({}, [], None)}
        try:
            if self.soubor.suffix.lower() == ".json":
                self.soubor.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                self.soubor.write_text("# Vstupní data – PB posudek\n" + toml_dumps(d), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Chyba při ukládání", str(e))
            return
        self.data = d
        self.title(f"PB posudek {__version__} – {self.soubor.name}")
        self.stav.set(f"Uloženo: {self.soubor}")

    # --- výpočet ----------------------------------------------------------
    def _busy(self, ano: bool, text: str = ""):
        self._zaneprazdnen = ano
        for b in (self.btn_vypocet, self.btn_protokol):
            b.state(["disabled"] if ano else ["!disabled"])
        if ano:
            self.progress.pack(side="right", padx=6, pady=2)
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()
        if text:
            self.stav.set(text)

    def _na_pozadi(self, prace, hotovo, text):
        if self._zaneprazdnen:
            return
        self._busy(True, text)
        vysledek = {}
        # Tk objekty se smí uvolňovat jen v hlavním vlákně – úklid předem a GC během výpočtu vypnout
        gc.collect()
        gc.disable()

        def beh():
            try:
                vysledek["ok"] = prace()
            except Exception as e:  # noqa: BLE001
                vysledek["chyba"] = e
                vysledek["tb"] = traceback.format_exc()

        th = threading.Thread(target=beh, daemon=True)
        th.start()

        def kontrola():
            if th.is_alive():
                self.after(100, kontrola)
                return
            gc.enable()
            self._busy(False)
            if "chyba" in vysledek:
                self.stav.set("Chyba výpočtu")
                messagebox.showerror("Chyba výpočtu", f"{vysledek['chyba']}\n\n{vysledek['tb'][-1500:]}")
            else:
                hotovo(vysledek["ok"])
        self.after(100, kontrola)

    def spocitej(self):
        try:
            d = self.ziskej_data()
            model = model_ze_slovniku(d)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Neplatná vstupní data", str(e))
            return

        def prace():
            model.spocitej()
            return model
        self._na_pozadi(prace, self._zobraz_vysledky, "Probíhá výpočet…")

    def protokol(self):
        if self.model is None:
            try:
                d = self.ziskej_data()
                model = model_ze_slovniku(d)
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Neplatná vstupní data", str(e))
                return
        else:
            model = self.model
        cil = self.vystup

        def prace():
            from .report import uloz_protokol
            if not model.protokol.posudky:
                model.spocitej()
            return uloz_protokol(model, cil)

        def hotovo(p):
            if self.model is not model:
                self._zobraz_vysledky(model)
            self.stav.set(f"Protokol uložen: {p}")
            webbrowser.open(Path(p).resolve().as_uri())
        self._na_pozadi(prace, hotovo, "Vytvářím HTML protokol…")

    def otevri_slozku(self):
        self.vystup.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(self.vystup)  # noqa: S606
        else:
            webbrowser.open(self.vystup.resolve().as_uri())

    # --- zobrazení výsledků ----------------------------------------------
    def _vymaz_vysledky(self):
        self.model = None
        self.t_vys.delete(*self.t_vys.get_children())
        for v, d in self.karty.values():
            v.configure(text="–", foreground="")
            d.configure(text="")
        self.lbl_souhrn.configure(text="")
        self.lbl_upozorneni.configure(text="")
        self.lbl_upozorneni.pack_forget()
        self._zavri_grafy()
        self.cb_graf.configure(values=[])
        self.var_graf.set("")

    def _zavri_grafy(self):
        import matplotlib.pyplot as plt
        for f in self._grafy_cache.values():
            plt.close(f)
        self._grafy_cache.clear()

    def _zobraz_vysledky(self, model):
        self._vymaz_vysledky()
        self.model = model
        pos = model.protokol.posudky
        self._radky = []
        for v in pos:
            tag = "ok" if v.vyuziti <= 0.9 else ("warn" if v.vyhovuje else "bad")
            vals = (v.mezni_stav, v.nazev, f"{v.vyuziti * 100:.1f} %", v.faze, v.kombinace,
                    fmt(v.x, 3) if v.x is not None else "–", fmt(v.E_d), fmt(v.R_d), v.jednotka)
            iid = self.t_vys.insert("", "end", values=vals, tags=(tag,))
            self._radky.append((iid, v))
        for ms in ("MSÚ", "MSP"):
            p = [v for v in pos if v.mezni_stav == ms]
            if p:
                mx = max(p, key=lambda v: v.vyuziti)
                lab, det = self.karty[ms]
                lab.configure(text=f"{mx.vyuziti * 100:.0f} %",
                              foreground="#0a7d0a" if mx.vyhovuje else "#b42323")
                det.configure(text=f"{mx.nazev} – {mx.faze}")
        ok = all(v.vyhovuje for v in pos)
        nok = sum(not v.vyhovuje for v in pos)
        lab, det = self.karty["Celkem"]
        lab.configure(text="VYHOVUJE" if ok else "NEVYHOVUJE", foreground="#0a7d0a" if ok else "#b42323")
        upoz = model.protokol.upozorneni
        det.configure(text=f"{len(pos)} posudků" + ("" if ok else f", nevyhovuje {nok}")
                      + (f"; upozornění {len(upoz)}" if upoz else ""))
        if upoz:
            self.lbl_upozorneni.configure(text="\n".join("⚠ " + t for t in upoz))
            self.lbl_upozorneni.pack(fill="x", pady=(8, 0), after=self._fr_karty)
        self.lbl_souhrn.configure(text=("✔ VYHOVUJE" if ok else "✘ NEVYHOVUJE"),
                                  foreground="#0a7d0a" if ok else "#b42323")
        self._seznam_grafu = self._sestav_seznam_grafu(model)
        self.cb_graf.configure(values=list(self._seznam_grafu))
        self.var_graf.set("Souhrn využití")
        self._zobraz_graf("Souhrn využití")
        self.nb.select(self.z_vysledky)
        self.after(50, lambda: self.pan_vys.sashpos(0, int(self.pan_vys.winfo_width() * 0.47)))
        self.stav.set(f"Výpočet dokončen – {len(pos)} posudků, "
                      f"{'vše vyhovuje' if ok else f'{nok} nevyhovuje'}"
                      + (f"; upozornění {len(upoz)} (karta Výsledky)." if upoz else "."))

    def _sestav_seznam_grafu(self, m) -> dict:
        g = grafy
        s = {"Souhrn využití": g.vyuziti, "Průřez": g.prurez, "Vedení kabelů": g.kabely,
             "Napětí v kabelech (ztráty)": g.napeti_kabelu, "Rozklad ztrát": g.ztraty_rozklad,
             "Předpínací síla v čase": g.sila_v_case, "Vnitřní síly": g.vnitrni_sily}
        for i, f in enumerate(m.faze):
            s[f"Napětí v betonu – {f.nazev}"] = ("faze", i)
        s.update({"Napětí po výšce průřezu": g.napeti_profil, "Hlavní napětí": g.hlavni_napeti,
                  "Průhyb": g.pruhyb, "MSÚ – ohybová únosnost": g.msu_ohyb,
                  "MSÚ – přetvoření v průřezu": g.msu_pretvoreni, "MSÚ – smyk": g.msu_smyk,
                  "Pracovní diagramy materiálů": g.diagramy_materialu})
        return s

    def _zobraz_graf(self, nazev: str):
        if not self.model or nazev not in self._seznam_grafu:
            return
        if self._zaneprazdnen:
            self.stav.set("Počkejte na dokončení běžící úlohy.")
            return
        fig = self._grafy_cache.get(nazev)
        if fig is None:
            fn = self._seznam_grafu[nazev]
            try:
                with grafy.vracet_obrazky():
                    if isinstance(fn, tuple):
                        figs = grafy.napeti_faze(self.model, None)
                        for n, f in zip([k for k, v in self._seznam_grafu.items() if isinstance(v, tuple)], figs):
                            self._grafy_cache[n] = f
                        fig = figs[fn[1]]
                    else:
                        fig = fn(self.model, None)
            except Exception as e:  # noqa: BLE001
                self.stav.set(f"Graf nelze vykreslit: {e}")
                return
            if fig is None:
                self.stav.set("Pro tento graf nejsou data.")
                return
            self._grafy_cache[nazev] = fig
        self.var_graf.set(nazev)
        self.g_vys.zobraz(fig)

    def _vyber_posudek(self, _=None):
        sel = self.t_vys.selection()
        if not sel or not self.model:
            return
        v = next(v for iid, v in self._radky if iid == sel[0])
        txt = (f"{v.nazev}  [{v.odkaz}]   E_d = {fmt(v.E_d)} {v.jednotka},  R_d = {fmt(v.R_d)} {v.jednotka},  "
               f"η = {v.vyuziti * 100:.1f} %   ({'vyhovuje' if v.vyhovuje else 'NEVYHOVUJE'})")
        if v.poznamka:
            txt += f"\n{v.poznamka}"
        self.lbl_detail.configure(text=txt)
        mapa = {"Ohyb": "MSÚ – ohybová únosnost", "Smyk": "MSÚ – smyk", "Hlavní napětí": "Hlavní napětí",
                "Průhyb": "Průhyb", "Napětí v předpínací výztuži": "Napětí v kabelech (ztráty)",
                "Křehký lom": "MSÚ – ohybová únosnost"}
        cil = mapa.get(v.skupina)
        if v.skupina in ("Napětí v betonu", "Dekomprese"):
            cil = f"Napětí v betonu – {v.faze}"
        if cil and cil in self._seznam_grafu and cil != self.var_graf.get():
            self._zobraz_graf(cil)

    def _serad(self, sloupec: str):
        polozky = [(self.t_vys.set(i, sloupec), i) for i in self.t_vys.get_children("")]

        def klic(t):
            s = t[0].replace("%", "").replace(" ", "").replace(",", ".").strip()
            try:
                return (0, float(s))
            except ValueError:
                return (1, s)
        obr = getattr(self, "_obr_razeni", {}).get(sloupec, False)
        polozky.sort(key=klic, reverse=not obr)
        for i, (_, iid) in enumerate(polozky):
            self.t_vys.move(iid, "", i)
        self._obr_razeni = {sloupec: not obr}

    def _konec(self):
        self._zavri_grafy()
        self.destroy()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    app = Aplikace(argv[0] if argv else None)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
