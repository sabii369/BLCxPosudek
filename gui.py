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
from .materialy import BETONARSKA_VYZTUZ, PREDPINACI_VYZTUZ, Beton, PredpinaciVyztuz
from .model import Nastaveni
from .protokol import fmt
from .toml_zapis import dumps as toml_dumps
from .vstup import model_ze_slovniku, nacti_soubor

TRIDY_BETONU = ["C20/25", "C25/30", "C30/37", "C35/45", "C40/50", "C45/55", "C50/60", "C55/67",
                "C60/75", "C70/85", "C80/95", "C90/105"]

PRIKLAD = Path(__file__).resolve().parents[1] / "examples" / "nosnik_I_20m_dodatecne.toml"

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
    "zatizeni": {"stale": [{"nazev": "Ostatní stálé", "q": 10.0, "t": 60}],
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
    "a_dek": "Hloubka dekomprese od kabelu [mm]", "r_sup": "r_sup (prázdné = dle typu)",
    "r_inf": "r_inf (prázdné = dle typu)", "gamma_P": "γ_P", "gamma_G": "γ_G,sup",
    "gamma_G_inf": "γ_G,inf", "xi": "ξ (6.10b)", "kombinace_msu": "Kombinace MSÚ",
    "cot_theta_min": "cot θ min", "cot_theta_max": "cot θ max", "kanalky": "Kanálky (b_w,nom)",
    "pruhyb_limit": "Mezní průhyb L/…", "relaxace_t_max_h": "Relaxace – max. čas [h]",
    "hlavni_napeti": "Posoudit hlavní napětí",
}
VOLBY_NASTAVENI = {
    "tah_predpeti": ["fctm", "fctk005", "0"], "tah_provoz": ["fctm", "fctk005", "0"],
    "dekomprese": ["casta", "kvazistala", "zadna"], "dekomprese_rezim": ["krajni", "kabel"],
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
                w = ttk.Entry(self, textvariable=v, width=18 if typ != "str" else 40)
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
            else:
                self.prom[k].set(_na_text(v))

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
            else:
                if v.strip() != "":
                    out[k] = _cislo(v) if typ == "choice" and k == "trida_relaxace" else v
        return out


class Tabulka(ttk.Frame):
    """Editovatelná tabulka. sloupce = [(klíč, popisek, šířka, typ, volby)].

    typ: str | float | optfloat | int | choice | pary | seznam. Klíče řádků, které tabulka nezobrazuje,
    se zachovají.
    """

    def __init__(self, master, sloupce, pri_zmene=None, vyska: int = 6, **kw):
        super().__init__(master, **kw)
        self.sloupce = sloupce
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

    def ziskej(self) -> list[dict]:
        out = []
        for n, iid in enumerate(self.tree.get_children(), 1):
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
            out.append(r)
        return out

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
            ("Ecm", "E_cm [MPa] (prázdné = tab. 3.1)", "optfloat", None),
            ("objemova_tiha", "Objemová tíha [kN/m³]", "optfloat", None),
            ("gamma_c", "γ_c", "optfloat", None), ("alpha_cc", "α_cc", "optfloat", None)],
            sloupcu=2, pri_zmene=self._info_materialy)
        self.f_beton.pack(fill="x")
        lf = ttk.LabelFrame(f, text="Předpínací výztuž (prázdné hodnoty = předvolba typu)", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_predp = Formular(lf, [
            ("typ", "Typ", "choice", list(PREDPINACI_VYZTUZ)), ("fpk", "f_pk [MPa]", "optfloat", None),
            ("fp01k", "f_p0,1k [MPa]", "optfloat", None), ("Ep", "E_p [MPa]", "optfloat", None),
            ("Ap_lano", "A_p lana [mm²]", "optfloat", None), ("d_lana", "Průměr lana [mm]", "optfloat", None),
            ("trida_relaxace", "Třída relaxace", "choice", ["1", "2", "3"]),
            ("rho1000", "ρ1000 [%]", "optfloat", None), ("gamma_s", "γ_s", "optfloat", None)],
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
            ("pocet_napinani", "Počet kroků napínání", "optint", None)], sloupcu=3, pri_zmene=self._naplanuj_nahled)
        self.f_nosnik.pack(fill="x")
        lf = ttk.LabelFrame(horni, text="Předem předpjaté prvky", padding=6)
        lf.pack(side="left", fill="x", padx=(8, 0))
        self.f_predem = Formular(lf, [("relaxace_pred_uvolnenim_h", "Čas do uvolnění [h]", "optfloat", None),
                                      ("eta_p1", "η_p1", "optfloat", None), ("alpha1", "α1", "optfloat", None),
                                      ("alpha2", "α2", "optfloat", None)], sloupcu=2)
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
            ("d_kanalku", "∅ kanálku", 70, "optfloat", None)], pri_zmene=self._naplanuj_nahled, vyska=5)
        self.t_kabely.pack(fill="both", expand=True)
        ttk.Label(lf, foreground="#52514e", text=(
            "parabola: z vlevo / z vrchol / z vpravo (+ x vrcholu, výchozí L/2); primka: z vlevo (+ z vpravo); "
            "polygon: body „0:530; 3.18:115; 8.78:115; 11.96:530“ a volitelně poloměry zaoblení „0; 29; 29; 0“.")
                  ).pack(anchor="w")
        self.g_kabely = Graf(z, figsize=(9, 2.6))
        self.g_kabely.pack(fill="both", expand=True)

    def _zalozka_vyztuz(self):
        z = ttk.Frame(self.nb, padding=8)
        self.nb.add(z, text="4  Výztuž")
        lf = ttk.LabelFrame(z, text="Podélná betonářská výztuž", padding=6)
        lf.pack(fill="both", expand=True)
        self.t_vyztuz = Tabulka(lf, [("nazev", "Název", 160, "str", None), ("z", "z [mm]", 90, "float", None),
                                     ("As", "A_s [mm²]", 90, "float", None)], pri_zmene=self._naplanuj_nahled)
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
                                   ("od", "od [m]", 70, "optfloat", None), ("do", "do [m]", 70, "optfloat", None)])
        self.t_smyk.pack(fill="both", expand=True)

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
                                   ("t_konec", "Konec životnosti [dny]", "float", None)])
        self.f_cas.pack(fill="x")
        lf = ttk.LabelFrame(z, text="Stálá zatížení (vlastní tíha nosníku se počítá automaticky)", padding=6)
        lf.pack(fill="both", expand=True, pady=6)
        self.t_stale = Tabulka(lf, [
            ("nazev", "Název", 200, "str", None), ("q", "q [kN/m]", 70, "optfloat", None),
            ("od", "od [m]", 60, "optfloat", None), ("do", "do [m]", 60, "optfloat", None),
            ("bremena", "Břemena F:x; … [kN:m]", 170, "pary", None), ("t", "t vnesení [dny]", 90, "optfloat", None),
            ("gamma", "γ_G,sup", 60, "optfloat", None), ("gamma_inf", "γ_G,inf", 60, "optfloat", None)], vyska=5)
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
            ("skupina", "Skupina", 80, "str", None)], vyska=5)
        self.t_prom.pack(fill="both", expand=True)

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
            if vych is not None and typ != "bool":
                popis += f"   (výchozí {vych})"
            pole.append((fl.name, popis, typ, vych if typ == "bool" else VOLBY_NASTAVENI.get(fl.name)))
        ttk.Label(f, text="Prázdné pole = výchozí hodnota podle doporučení ČSN EN 1992-1-1.",
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
        self.f_nastaveni.nastav(d.get("posouzeni", {}))
        self._prepni_prurez()
        self._info_materialy()
        self._naplanuj_nahled()

    def ziskej_data(self) -> dict:
        d = copy.deepcopy(self.data)
        d["projekt"] = {**d.get("projekt", {}), **self.f_projekt.ziskej()}
        d["beton"] = self.f_beton.ziskej()
        d["predpinaci_vyztuz"] = self.f_predp.ziskej()
        d["betonarska_vyztuz"] = self.f_bet.ziskej()
        d["prurez"] = self._prurez_data()
        d["nosnik"] = self.f_nosnik.ziskej()
        d["predem"] = self.f_predem.ziskej()
        d["kabel"] = self.t_kabely.ziskej()
        d["vyztuz"] = self.t_vyztuz.ziskej()
        d["smykova_vyztuz"] = self.t_smyk.ziskej()
        d["prostredi"] = self.f_prostredi.ziskej()
        d["casova_osa"] = self.f_cas.ziskej()
        prom = []
        for r in self.t_prom.ziskej():
            sily, roz = r.pop("sily", None), r.pop("rozestupy", None)
            if sily:
                r["pohyblive"] = {"sily": sily, "rozestupy": roz or []}
            prom.append(r)
        d["zatizeni"] = {**d.get("zatizeni", {}), "stale": self.t_stale.ziskej(), "promenne": prom}
        d["posouzeni"] = self.f_nastaveni.ziskej()
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
        # kabely
        fig = self.g_kabely.fig
        fig.clear()
        ax = fig.add_subplot(111)
        ax.fill_between([0, m.L], 0, P.h, color="#e9eef6", lw=0)
        ax.axhline(P.zt, color="#52514e", lw=0.8, ls="-.")
        for j, k in enumerate(m.kabely):
            ax.plot(k.geometrie.x, k.geometrie.z, color=grafy.C[j % 8], lw=2, label=k.nazev)
        for xs_ in ((m.L - m.L0) / 2, (m.L + m.L0) / 2):
            ax.plot([xs_], [-0.06 * P.h], marker="^", ms=9, color="#52514e")
        ax.set_xlim(-0.2, m.L + 0.2)
        ax.set_ylim(-0.12 * P.h, 1.05 * P.h)
        ax.set_xlabel("x [m]")
        ax.set_ylabel("z [mm]")
        ax.legend(ncol=max(len(m.kabely), 1), fontsize=8, loc="upper center")
        fig.tight_layout()
        self.g_kabely.canvas.draw_idle()

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
        det.configure(text=f"{len(pos)} posudků" + ("" if ok else f", nevyhovuje {nok}"))
        self.lbl_souhrn.configure(text=("✔ VYHOVUJE" if ok else "✘ NEVYHOVUJE"),
                                  foreground="#0a7d0a" if ok else "#b42323")
        self._seznam_grafu = self._sestav_seznam_grafu(model)
        self.cb_graf.configure(values=list(self._seznam_grafu))
        self.var_graf.set("Souhrn využití")
        self._zobraz_graf("Souhrn využití")
        self.nb.select(self.z_vysledky)
        self.after(50, lambda: self.pan_vys.sashpos(0, int(self.pan_vys.winfo_width() * 0.47)))
        self.stav.set(f"Výpočet dokončen – {len(pos)} posudků, "
                      f"{'vše vyhovuje' if ok else f'{nok} nevyhovuje'}.")

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
