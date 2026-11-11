"""
gui.py
======
Grafické rozhraní (Tkinter) pro Bridge Load Calculator – deskový model,
spojitý nosník o více polích.

Vstupy: prefabrikát (předvyplnění), počet polí a rozpětí každého pole, N, b,
        Iy, třída betonu (E = Ecm), ν, podélná spára (b_s, Iy_s), Ve, vzdálenost
        vozidel, počet poloh na pole, d (statická účinná výška), typ a třída
        vozidla, příčná poloha MLC (slider), volby MKP.  Podpory jsou liniové;
        Okrajové podmínky podpor (kloubové tvrdé / kloubové měkké /
        vetknutí, tuhost pružného vetknutí k_φ) jednou pro celý most.
        V se posuzuje v řezech d od podpor, zatížení smí stát kdekoli.
Výstupy: tabulka po kontrolních řezech, grafy (1D obálky, obálky na nosnících,
         využití, příčný roznos, průběhy na nosnících, zatížení v rozhodujícím
         stavu).
"""

from __future__ import annotations
import gc
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from .vehicles import seznam_mlc, kolove_vozidlo, pasove_vozidlo
from .geometry import ECM_GPA
from .prefabrikaty import nacti_prefabrikaty
from .comparison import porovnani_zatizeni, ComparisonResult
from .plotting import (plot_obalky, plot_obalky_nosniky, plot_vyuziti_rezy,
                       plot_pricny_roznos, plot_profily_nosniky, plot_zatizeni, plot_sit)
from .stale_zatizeni import Vybaveni
from .vnitrni_sily import vnitrni_sily, VysledekSil

DEFAULTS = {
    "n_poli": 2, "L": "12", "N": "15", "b": "1", "beton": "C35/45", "beton_s": "C30/37",
    "Iy": "0.0144", "h": "0.5", "alfa": "90", "k_v": "2000", "k_rot": "",
    "b_s": "0.35", "Iy_s": "0.02",
    "nu": "0.2", "Ve": "80", "dist": "30.5", "n": "40", "d": "0.0",
    "typ": "p", "MLC": "MLC80",
}
MAX_POLI = 12

C_BEAM, C_DECK, C_VEH, C_CENTER = "#2e75b6", "#d5e8f5", "#e74c3c", "#27ae60"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bridge Load Calculator – Deskový model, spojitý nosník")
        self.resizable(True, True)
        self._cr: ComparisonResult | None = None
        self._vysledek = None
        self._vysledek_sily = None
        self._build_ui()
        # výška okna max. podle obrazovky
        self.update_idletasks()
        hs = self.winfo_screenheight()
        h = min(self.winfo_reqheight(), hs - 80)
        self.geometry(f"{self.winfo_reqwidth()}x{h}+20+10")
        self.after(100, self._reset_poloha)

    # ── Sestavení UI ─────────────────────────────────────────────────────
    def _build_ui(self):
        pad = {"padx": 6, "pady": 2}
        main = ttk.Frame(self, padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # levý panel se svislým posuvníkem (vstupů je hodně – na menších
        # obrazovkách by se nevešly)
        obal = ttk.Frame(main)
        obal.grid(row=0, column=0, sticky="ns", padx=5)
        obal.rowconfigure(0, weight=1)
        self._cv_left = cv = tk.Canvas(obal, highlightthickness=0, borderwidth=0)
        sbar = ttk.Scrollbar(obal, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sbar.set)
        cv.grid(row=0, column=0, sticky="ns")
        sbar.grid(row=0, column=1, sticky="ns")
        left = ttk.LabelFrame(cv, text="Vstupní parametry", padding=8)
        cv.create_window((0, 0), window=left, anchor="nw")

        def _velikost(_=None):
            cv.configure(scrollregion=cv.bbox("all"), width=left.winfo_reqwidth(),
                         height=min(left.winfo_reqheight(),
                                    max(300, self.winfo_screenheight() - 230)))
        left.bind("<Configure>", _velikost)

        def _kolecko(ev):
            if ev.delta:
                cv.yview_scroll(int(-ev.delta / 120) or (-1 if ev.delta > 0 else 1), "units")
            elif ev.num == 4:
                cv.yview_scroll(-1, "units")
            elif ev.num == 5:
                cv.yview_scroll(1, "units")
        for sek in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cv.bind_all(sek, lambda ev: _kolecko(ev)
                        if str(ev.widget).startswith(str(cv)) else None)
        e = {}
        self._entries = e

        self._row = 0

        self._lbl = {}

        def row_entry(label, key, unit="", width=14):
            r = self._row
            lb = ttk.Label(left, text=label)
            lb.grid(row=r, column=0, sticky="w", **pad)
            self._lbl[key] = lb
            var = tk.StringVar(value=DEFAULTS.get(key, ""))
            ent = ttk.Entry(left, textvariable=var, width=width)
            ent.grid(row=r, column=1, sticky="w", **pad)
            if unit:
                ttk.Label(left, text=unit, foreground="gray").grid(row=r, column=2, sticky="w")
            if key in ("N", "b", "b_s"):
                var.trace_add("write", lambda *_: self.after(50, self._update_slider_range))
            e[key] = var
            self._row += 1
            return ent

        # ── prefabrikát ──────────────────────────────────────────────────
        self._prefab, zdroj = nacti_prefabrikaty()
        ttk.Label(left, text="Prefabrikát").grid(row=self._row, column=0, sticky="w", **pad)
        self._prefab_var = tk.StringVar(value="(vlastní)")
        pcb = ttk.Combobox(left, textvariable=self._prefab_var, width=14, state="readonly",
                           values=["(vlastní)"] + list(self._prefab))
        pcb.grid(row=self._row, column=1, sticky="w", **pad)
        pcb.bind("<<ComboboxSelected>>", lambda _: self._vyber_prefabrikat())
        self._pcb = pcb
        ttk.Label(left, text="předvyplní L, b, Iy, spáru" if "vestav" in zdroj
                  else "předvyplní L, b, Iy, spáru (Prefabrikáty.xlsx)",
                  foreground="gray").grid(row=self._row, column=2, sticky="w")
        self._row += 1

        # ── typ konstrukce ───────────────────────────────────────────────
        ttk.Label(left, text="Typ konstrukce").grid(row=self._row, column=0, sticky="w", **pad)
        typk_var = tk.StringVar(value="nosniky")
        fk = ttk.Frame(left); fk.grid(row=self._row, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(fk, text="nosníky", variable=typk_var, value="nosniky",
                        command=self._prepni_typ).pack(side="left")
        ttk.Radiobutton(fk, text="deska (pás 1 m)", variable=typk_var, value="deska",
                        command=self._prepni_typ).pack(side="left")
        e["typ_k"] = typk_var
        self._row += 1

        # ── počet polí + rozpětí jednotlivých polí ──────────────────────
        ttk.Label(left, text="Počet polí").grid(row=self._row, column=0, sticky="w", **pad)
        self._npoli_var = tk.StringVar(value=str(DEFAULTS["n_poli"]))
        sb = ttk.Spinbox(left, from_=1, to=MAX_POLI, textvariable=self._npoli_var, width=6,
                         command=self._prestav_pole)
        sb.grid(row=self._row, column=1, sticky="w", **pad)
        sb.bind("<Return>", lambda _: self._prestav_pole())
        sb.bind("<FocusOut>", lambda _: self._prestav_pole())
        ttk.Label(left, text="[-]", foreground="gray").grid(row=self._row, column=2, sticky="w")
        self._row += 1
        ttk.Label(left, text="Rozpětí polí L").grid(row=self._row, column=0, sticky="nw", **pad)
        self._frm_pole = ttk.Frame(left)
        self._frm_pole.grid(row=self._row, column=1, columnspan=2, sticky="w", padx=6)
        self._L_vars: list[tk.StringVar] = []
        self._L_pamet: list[str] = []
        self._row += 1
        self._prestav_pole()

        self._ent_N = row_entry("Počet nosníků N",   "N",    "[-]")
        row_entry("Šířka nosníku b",         "b",    "[m]  (bez spáry = rozteč nosníků)")
        self._ent_Iy = row_entry("Mom. setrvačnosti Iy", "Iy", "[m⁴]  (nosník)")
        self._ent_h = row_entry("Tloušťka desky h", "h",  "[m]  (jen deska)")

        # ── třída betonu → E = Ecm ───────────────────────────────────────
        ttk.Label(left, text="Třída betonu").grid(row=self._row, column=0, sticky="w", **pad)
        bet_var = tk.StringVar(value=DEFAULTS["beton"])
        bcb = ttk.Combobox(left, textvariable=bet_var, values=list(ECM_GPA), width=10,
                           state="readonly")
        bcb.grid(row=self._row, column=1, sticky="w", **pad)
        self._lbl_E = ttk.Label(left, text="", foreground="gray")
        self._lbl_E.grid(row=self._row, column=2, sticky="w")
        bcb.bind("<<ComboboxSelected>>", lambda _: self._popis_E())
        e["beton"] = bet_var
        self._row += 1
        self._popis_E()
        row_entry("Poissonovo číslo ν",      "nu",   "[-]")

        # ── podélná spára ────────────────────────────────────────────────
        sp_var = tk.BooleanVar(value=False)
        self._chk_sp = ttk.Checkbutton(
            left, text="Podélná spára mezi nosníky (deskový prvek, kloubově, bez podpory)",
            variable=sp_var, command=self._prepni_sparu)
        self._chk_sp.grid(row=self._row, column=0, columnspan=3, sticky="w", padx=6)
        e["spara"] = sp_var
        self._row += 1
        self._ent_bs = row_entry("   Šířka spáry b_s",   "b_s",  "[m]")
        self._ent_Iys = row_entry("   Iy spáry",         "Iy_s", "[m⁴]  (h_s = (12·Iy_s/b_s)^⅓)")
        ttk.Label(left, text="   Beton spáry").grid(row=self._row, column=0, sticky="w", **pad)
        bs_var = tk.StringVar(value=DEFAULTS["beton_s"])
        self._cb_bet_s = ttk.Combobox(left, textvariable=bs_var, values=list(ECM_GPA),
                                      width=10, state="readonly")
        self._cb_bet_s.grid(row=self._row, column=1, sticky="w", **pad)
        self._lbl_Es = ttk.Label(left, text="", foreground="gray")
        self._lbl_Es.grid(row=self._row, column=2, sticky="w")
        self._cb_bet_s.bind("<<ComboboxSelected>>", lambda _: self._popis_E())
        e["beton_s"] = bs_var
        self._row += 1
        self._popis_E()

        row_entry("Výj. zatíž. Ve",          "Ve",   "[t]")
        row_entry("Vzdál. vozidel",          "dist", "[m]")
        row_entry("Počet poloh na pole n",   "n",    "[-]")
        row_entry("Stat. účinná výška d",    "d",    "[m]  (řez V ve vzdálenosti d od podpory)")
        row_entry("Úhel šikmosti α",         "alfa", "[°]  (90 = kolmý, max. teoret. 180; 90–165)")
        ttk.Label(left, text="Druh šikmosti").grid(row=self._row, column=0, sticky="w", **pad)
        sik_var = tk.StringVar(value="prava")
        fs_ = ttk.Frame(left); fs_.grid(row=self._row, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(fs_, text="pravá", variable=sik_var, value="prava").pack(side="left")
        ttk.Radiobutton(fs_, text="levá", variable=sik_var, value="leva").pack(side="left")
        e["sikmost"] = sik_var
        self._row += 1
        r_k = self._row
        ttk.Label(left, text="Tuhost podpory k_v").grid(row=r_k, column=0, sticky="w", **pad)
        kv_var = tk.StringVar(value=DEFAULTS["k_v"])
        ttk.Entry(left, textvariable=kv_var, width=14).grid(row=r_k, column=1, sticky="w", **pad)
        ttk.Label(left, text="[MN/m na 1 m podpory]  (prázdné/0 = tuhá; doporuč. 1000–3000)",
                  foreground="gray").grid(row=r_k, column=2, sticky="w")
        e["k_v"] = kv_var
        self._row += 1
        # okrajové podmínky podpor (jednou pro celý most)
        r_u = self._row
        ttk.Label(left, text="Uložení podpor").grid(row=r_u, column=0, sticky="w", **pad)
        uloz_var = tk.StringVar(value="tvrde")
        fu = ttk.Frame(left); fu.grid(row=r_u, column=1, columnspan=2, sticky="w")
        for txt_, val_ in (("kloub tvrdý", "tvrde"), ("kloub měkký", "mekke"),
                           ("vetknutí", "vetknuti")):
            ttk.Radiobutton(fu, text=txt_, variable=uloz_var, value=val_,
                            command=self._prepni_uloz).pack(side="left")
        e["uloz"] = uloz_var
        self._row += 1
        ttk.Label(left, text="   tvrdý: natočení podél osy podpory zabráněno (u pružné "
                             "podpory sleduje průhyb); měkký: rotace volné",
                  foreground="gray", wraplength=520).grid(row=self._row, column=0,
                                                          columnspan=3, sticky="w", padx=6)
        self._row += 1
        r_r = self._row
        ttk.Label(left, text="   Tuhost vetknutí k_φ").grid(row=r_r, column=0, sticky="w", **pad)
        kr_var = tk.StringVar(value=DEFAULTS["k_rot"])
        self._ent_krot = ttk.Entry(left, textvariable=kr_var, width=14)
        self._ent_krot.grid(row=r_r, column=1, sticky="w", **pad)
        ttk.Label(left, text="[MNm/rad na 1 m podpory]  (prázdné = dokonalé vetknutí)",
                  foreground="gray").grid(row=r_r, column=2, sticky="w")
        e["k_rot"] = kr_var
        self._row += 1
        bs_var = tk.BooleanVar(value=False)
        self._chk_bs = ttk.Checkbutton(
            left, text="β_s = 0 i u pružné podpory (zjednodušeně, SCIA s vetknutou rotací "
                       "podél podpory – jen pro srovnání)", variable=bs_var)
        self._chk_bs.grid(row=self._row, column=0, columnspan=3, sticky="w", padx=6)
        e["beta_s_pevne"] = bs_var
        self._row += 1

        r = self._row
        ttk.Label(left, text="Typ vozidla").grid(row=r, column=0, sticky="w", **pad)
        typ_var = tk.StringVar(value=DEFAULTS["typ"])
        f = ttk.Frame(left); f.grid(row=r, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(f, text="Kolové (k)", variable=typ_var, value="k",
                        command=self._update_slider_range).pack(side="left")
        ttk.Radiobutton(f, text="Pásové (p)", variable=typ_var, value="p",
                        command=self._update_slider_range).pack(side="left")
        e["typ"] = typ_var

        r += 1
        ttk.Label(left, text="Třída MLC").grid(row=r, column=0, sticky="w", **pad)
        mlc_var = tk.StringVar(value=DEFAULTS["MLC"])
        cb = ttk.Combobox(left, textvariable=mlc_var, values=seznam_mlc(), width=10,
                          state="readonly")
        cb.grid(row=r, column=1, sticky="w", **pad)
        cb.bind("<<ComboboxSelected>>", lambda _: self._update_slider_range())
        e["MLC"] = mlc_var

        def radio_row(label, key, options, default):
            nonlocal r
            r += 1
            ttk.Label(left, text=label).grid(row=r, column=0, sticky="w", **pad)
            var = tk.StringVar(value=default)
            fr = ttk.Frame(left); fr.grid(row=r, column=1, columnspan=2, sticky="w")
            for txt, val in options:
                ttk.Radiobutton(fr, text=txt, variable=var, value=val).pack(side="left")
            e[key] = var
            return fr

        self._frm_spoj = radio_row("Propojení nosníků", "spoj",
                                   [("kloubové", "kloub"), ("deskové", "deska")], "kloub")
        self._spoj_rb = e["spoj"]
        r += 1
        ttk.Label(left, text="   (se spárou vždy kloubově)", foreground="gray"
                  ).grid(row=r, column=1, columnspan=2, sticky="w")

        r += 1
        roz_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="Roznos kola do střednice desky", variable=roz_var
                        ).grid(row=r, column=0, columnspan=3, sticky="w", padx=6)
        e["roznos"] = roz_var
        r += 1
        ob_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="Obálky na jednotlivých nosnících (2D pojezd, delší výpočet)",
                        variable=ob_var).grid(row=r, column=0, columnspan=3, sticky="w", padx=6)
        e["obalky"] = ob_var

        def plain_entry(label, key, default, unit):
            nonlocal r
            r += 1
            ttk.Label(left, text=label).grid(row=r, column=0, sticky="w", **pad)
            var = tk.StringVar(value=default)
            ttk.Entry(left, textvariable=var, width=14).grid(row=r, column=1, **pad)
            ttk.Label(left, text=unit, foreground="gray").grid(row=r, column=2, sticky="w")
            e[key] = var

        plain_entry("Tloušťka vozovky t", "t_voz", "0.0", "[m]")
        plain_entry("Velikost prvku MKP", "ex", "0.125", "[m]")
        plain_entry("Krok poloh pro obálky", "krok_ob", "0.5", "[m]  (menší = hladší obálky, delší výpočet)")
        plain_entry("Převýšení grafů sil", "pomer", "2", "[-]  (půdorys: b_vykr/L_vykr = k·b/L)")

        # slider příčné polohy MLC
        r += 1
        ttk.Separator(left, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        r += 1
        ttk.Label(left, text="Příčná poloha MLC", font=("", 9, "bold")).grid(
            row=r, column=0, columnspan=3, sticky="w", padx=6)
        r += 1
        self._slider_var = tk.DoubleVar(value=3.0)
        self._slider = ttk.Scale(left, from_=0.0, to=6.0, variable=self._slider_var,
                                 orient="horizontal", length=180, command=self._on_slider)
        self._slider.grid(row=r, column=0, columnspan=2, sticky="ew", padx=6, pady=2)
        r += 1
        fs = ttk.Frame(left); fs.grid(row=r, column=0, columnspan=3, sticky="w", padx=6)
        self._lbl_poloha = ttk.Label(fs, text="y_c = 3.000 m", width=16)
        self._lbl_poloha.pack(side="left")
        ttk.Button(fs, text="Střed", width=7, command=self._reset_poloha).pack(side="left", padx=4)
        self._chk_stred_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(fs, text="auto střed", variable=self._chk_stred_var,
                        command=self._on_chk_stred).pack(side="left")
        r += 1
        self._canvas = tk.Canvas(left, width=200, height=80, bg="#f8f9fa",
                                 relief="solid", bd=1)
        self._canvas.grid(row=r, column=0, columnspan=3, padx=6, pady=(2, 6))
        r += 1
        bf = ttk.Frame(left); bf.grid(row=r, column=0, columnspan=3, pady=8)
        self._btn_run = ttk.Button(bf, text="▶  Spustit výpočet", command=self._run, width=24)
        self._btn_run.pack(pady=4)
        self._lbl_stav = ttk.Label(bf, text="", foreground="gray")
        self._lbl_stav.pack()

        # ── vnitřní síly pro posudek (g0, g − g0, q) ─────────────────────
        r += 1
        ttk.Separator(left, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        r += 1
        ttk.Label(left, text="Vnitřní síly pro posudek (g0, g − g0, q = Ve)",
                  font=("", 9, "bold")).grid(row=r, column=0, columnspan=3, sticky="w", padx=6)
        for label, key, default, unit in (
            ("Šířka chodníku vlevo", "ch_L", "1.5", "[m]"),
            ("Šířka chodníku vpravo", "ch_P", "1.5", "[m]"),
            ("Tíha skladby chodníku", "g_ch", "5.0", "[kN/m²]"),
            ("Tíha skladby vozovky", "g_voz", "2.6", "[kN/m²]"),
            ("Zábradlí (každá strana)", "g_zab", "0.5", "[kN/m]  (u vnějšího okraje)"),
            ("Svodidlo (každá strana)", "g_svo", "0.6", "[kN/m]  (na okraji vozovky)"),
            ("Plocha nosníku A", "A_nos", "", "[m²]  (g0 = A·γ; deska: h·γ)"),
            ("Objemová tíha γ", "gamma_b", "25", "[kN/m³]"),
            ("Tíha výplně spáry", "g_sp", "0", "[kN/m]  (½ na sousední nosníky)"),
            ("Plocha dobetonávky A", "A_dob", "0", "[m²]  (mezi nosníky, v g0; ½ na sousední nosníky)"),
            ("Dynamický součinitel δ", "dyn", "", "[-]  (násobí Ve; prázdné = ČSN 73 6222: 1,05)"),
            ("Osa vozidla Ve y", "y_Ve", "", "[m]  (prázdné = osa vozovky)"),
            ("Krok poloh Ve", "krok_q", "0.25", "[m]"),
        ):
            plain_entry(label, key, default, unit)
        r += 1
        bf2 = ttk.Frame(left); bf2.grid(row=r, column=0, columnspan=3, pady=8)
        self._btn_sily = ttk.Button(bf2, text="▶  Vnitřní síly pro posudek",
                                    command=self._run_sily, width=28)
        self._btn_sily.pack(pady=4)
        self._lbl_stav_sily = ttk.Label(bf2, text="", foreground="gray")
        self._lbl_stav_sily.pack()

        self._prepni_sparu()
        self._prepni_typ()
        self._prepni_uloz()

        # ── Pravý sloupec: výsledky ──────────────────────────────────────
        right = ttk.LabelFrame(main, text="Výsledky po kontrolních řezech", padding=8)
        right.grid(row=0, column=1, sticky="nsew", padx=5)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        cols = ("rez", "x", "mlc1", "ve1", "eta1", "mlc2", "ve2", "eta2", "nos")
        heads = ("Řez", "x [m]", "MLC 1D", "Ve 1D", "η 1D", "MLC 2D", "Ve 2D", "η 2D",
                 "nosník / pás")
        widths = (170, 60, 70, 70, 60, 70, 70, 60, 110)
        self._tree = ttk.Treeview(right, columns=cols, show="headings", height=14)
        for c, h, w in zip(cols, heads, widths):
            self._tree.heading(c, text=h)
            self._tree.column(c, width=w, anchor="w" if c == "rez" else "e")
        self._tree.tag_configure("fail", foreground="#c0392b")
        self._tree.tag_configure("gov", background="#fff3cd")
        self._tree.grid(row=0, column=0, sticky="nsew")
        right.columnconfigure(0, weight=1)
        self._txt = tk.Text(right, width=90, height=12, font=("Courier", 9), state="disabled")
        self._txt.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        right.rowconfigure(1, weight=1)

        # ── Grafy ────────────────────────────────────────────────────────
        pf = ttk.LabelFrame(main, text="Grafy", padding=6)
        pf.grid(row=1, column=0, columnspan=2, sticky="ew", pady=6)
        r1 = ttk.Frame(pf); r1.pack(fill="x")
        r2 = ttk.Frame(pf); r2.pack(fill="x")
        ttk.Label(r1, text="Řez:").pack(side="left", padx=(4, 2))
        self._rez_var = tk.StringVar(value="(rozhodující)")
        self._rez_cb = ttk.Combobox(r1, textvariable=self._rez_var, width=26,
                                    state="readonly", values=["(rozhodující)"])
        self._rez_cb.pack(side="left", padx=(0, 10))
        for txt, cmd in [
            ("Zatížení – Mmax, Vmax",   self._plot_zatizeni),
            ("Průběhy – MLC (řez)",     lambda: self._plot_rez(plot_profily_nosniky, stav="MLC",
                                                               pomer=self._pomer())),
            ("Průběhy – Ve (řez)",      lambda: self._plot_rez(plot_profily_nosniky, stav="Ve",
                                                               pomer=self._pomer())),
            ("Příčný roznos (řez)",     lambda: self._plot_rez(plot_pricny_roznos)),
        ]:
            ttk.Button(r1, text=txt, command=cmd, width=22).pack(side="left", padx=3, pady=3)
        ttk.Label(r2, text="Celý most:").pack(side="left", padx=(4, 8))
        for txt, cmd in [
            ("Obálky nosníky – MLC",    lambda: self._plot(plot_obalky_nosniky, stav="MLC",
                                                           pomer=self._pomer())),
            ("Obálky nosníky – Ve",     lambda: self._plot(plot_obalky_nosniky, stav="Ve",
                                                           pomer=self._pomer())),
            ("Obálky 1D (MLC vs Ve)",   lambda: self._plot(plot_obalky)),
            ("Využití po řezech",       lambda: self._plot(plot_vyuziti_rezy)),
            ("Síť MKP",                 lambda: self._plot(plot_sit)),
        ]:
            ttk.Button(r2, text=txt, command=cmd, width=22).pack(side="left", padx=3, pady=3)

    # ── Pole ─────────────────────────────────────────────────────────────
    def _prestav_pole(self):
        """Vytvoří vstupní pole L1 … Ln podle zadaného počtu polí (hodnoty zachová)."""
        try:
            n = int(float(self._npoli_var.get()))
        except ValueError:
            n = len(self._L_vars) or 1
        n = max(1, min(MAX_POLI, n))
        self._npoli_var.set(str(n))
        if n == len(self._L_vars) and self._frm_pole.winfo_children():
            return
        stare = [v.get() for v in self._L_vars]
        self._L_pamet[:len(stare)] = stare
        if len(stare) > len(self._L_pamet):
            self._L_pamet = stare
        stare = self._L_pamet
        for w in self._frm_pole.winfo_children():
            w.destroy()
        self._L_vars = []
        for i in range(n):
            val = stare[i] if i < len(stare) else (stare[-1] if stare else DEFAULTS["L"])
            var = tk.StringVar(value=val)
            rr, cc = divmod(i, 4)
            ttk.Label(self._frm_pole, text=f"L{i + 1}").grid(row=rr, column=2 * cc,
                                                             sticky="e", padx=(0, 2))
            ttk.Entry(self._frm_pole, textvariable=var, width=6).grid(
                row=rr, column=2 * cc + 1, sticky="w", padx=(0, 6), pady=1)
            self._L_vars.append(var)
        ttk.Label(self._frm_pole, text="[m]", foreground="gray").grid(
            row=0, column=8, sticky="w")

    def _get_L(self):
        self._prestav_pole()
        out = []
        for i, v in enumerate(self._L_vars):
            try:
                out.append(float(v.get().replace(",", ".")))
            except ValueError:
                raise ValueError(f"Neplatné rozpětí pole {i + 1}: '{v.get()}'.")
        return out

    # ── Beton, spára, prefabrikát ────────────────────────────────────────
    def _popis_E(self):
        fmt = lambda t: f"{ECM_GPA.get(t, 0) * 1000:,.0f}".replace(",", " ")
        self._lbl_E.configure(text=f"E = Ecm = {fmt(self._entries['beton'].get())} MPa")
        if "beton_s" in self._entries:
            self._lbl_Es.configure(
                text=f"E_s = Ecm = {fmt(self._entries['beton_s'].get())} MPa  (dobetonávka)")

    def _je_deska(self) -> bool:
        return self._entries["typ_k"].get() == "deska"

    def _prepni_uloz(self):
        u = self._entries["uloz"].get()
        self._ent_krot.configure(state="normal" if u == "vetknuti" else "disabled")
        self._chk_bs.configure(state="disabled" if u == "mekke" else "normal")

    def _prepni_typ(self):
        d = self._je_deska()
        st_n = "disabled" if d else "normal"
        self._ent_N.configure(state=st_n)
        self._ent_Iy.configure(state=st_n)
        self._ent_h.configure(state="normal" if d else "disabled")
        self._pcb.configure(state="disabled" if d else "readonly")
        self._chk_sp.configure(state=st_n)
        for w in self._frm_spoj.winfo_children():
            w.configure(state=st_n)
        self._lbl["b"].configure(text="Šířka desky b" if d else "Šířka nosníku b")
        self._prepni_sparu()
        self._reset_poloha()

    def _prepni_sparu(self):
        st = "normal" if (self._entries["spara"].get() and not self._je_deska()) else "disabled"
        self._ent_bs.configure(state=st)
        self._ent_Iys.configure(state=st)
        self._cb_bet_s.configure(state="readonly" if st == "normal" else "disabled")
        self._update_slider_range()

    def _vyber_prefabrikat(self):
        p = self._prefab.get(self._prefab_var.get())
        if p is None:
            return
        e = self._entries
        for v in self._L_vars:
            v.set(f"{p.L:g}")
        self._L_pamet = [f"{p.L:g}"] * max(len(self._L_pamet), len(self._L_vars))
        e["b"].set(f"{p.b:g}")
        e["Iy"].set(f"{p.Iy:.6g}")
        e["spara"].set(bool(p.spara))
        if p.spara:
            e["b_s"].set(f"{p.b_s:g}")
            e["Iy_s"].set(f"{p.Iy_s:.6g}")
        self._prepni_sparu()
        self._reset_poloha()

    # ── Slider a průřez ──────────────────────────────────────────────────
    def _get_NB(self):
        """(N, b, b_s) – b_s = 0 bez spáry; deska: (1, šířka, 0)."""
        if self._je_deska():
            try:
                return 1, max(float(self._entries["b"].get()), 1e-3), 0.0
            except ValueError:
                return 1, 8.0, 0.0
        try:
            N, b = int(self._entries["N"].get()), float(self._entries["b"].get())
        except ValueError:
            return 4, 1.5, 0.0
        bs = 0.0
        if self._entries["spara"].get():
            try:
                bs = max(0.0, float(self._entries["b_s"].get()))
            except ValueError:
                bs = 0.0
        return max(N, 1), max(b, 1e-3), bs

    def _get_rozvor(self):
        try:
            MLC, typ = self._entries["MLC"].get(), self._entries["typ"].get()
            v = kolove_vozidlo(MLC) if typ == "k" else pasove_vozidlo(MLC)
            return v.rozvor, getattr(v, "b_k", 0.3)
        except Exception:
            return 1.5, 0.3

    def _update_slider_range(self):
        if not hasattr(self, "_slider"):
            return
        N, b, bs = self._get_NB()
        rozvor, b_k = self._get_rozvor()
        B = N * b + (N - 1) * bs
        lo, hi = rozvor / 2 + b_k / 2, B - rozvor / 2 - b_k / 2
        if lo >= hi:
            lo, hi = 0.0, B
        self._slider.configure(from_=lo, to=hi)
        if self._chk_stred_var.get():
            self._slider_var.set(B / 2)
        self._on_slider()

    def _on_slider(self, *_):
        self._lbl_poloha.configure(text=f"y_c = {self._slider_var.get():.3f} m")
        self._kresli_prez()

    def _on_chk_stred(self):
        if self._chk_stred_var.get():
            self._reset_poloha()

    def _reset_poloha(self):
        N, b, bs = self._get_NB()
        self._chk_stred_var.set(True)
        self._slider_var.set((N * b + (N - 1) * bs) / 2)
        self._update_slider_range()

    def _kresli_prez(self):
        c = self._canvas
        c.delete("all")
        W, H = 200, 80
        N, b, bs = self._get_NB()
        rozvor, b_k = self._get_rozvor()
        B = N * b + (N - 1) * bs
        y_c = self._slider_var.get()
        m = 10
        sc = (W - 2 * m) / B
        px = lambda y: m + y * sc
        c.create_rectangle(m, 20, W - m, 40, fill=C_DECK, outline="#666")
        if self._je_deska():
            c.create_rectangle(m, 20, W - m, 46, fill="#9bb7d4", outline="#1a4a80")
            c.create_text(W / 2, 60, text="deska – výsledky na pás 1 m", font=("", 7),
                          fill="#333")
        for i in range(N if not self._je_deska() else 0):
            y0 = i * (b + bs)
            if bs > 0 and i < N - 1:
                c.create_rectangle(px(y0 + b), 20, px(y0 + b + bs), 40, fill="#bbbbbb",
                                   outline="")
            x = px(y0 + 0.5 * b)
            c.create_rectangle(x - 4, 40, x + 4, 68, fill=C_BEAM, outline="#1a4a80")
            c.create_text(x, 72, text=str(i + 1), font=("", 7), fill="#333")
        for ys in (y_c - rozvor / 2, y_c + rozvor / 2):
            xl = max(m, min(W - m, px(ys - b_k / 2)))
            xr = max(m, min(W - m, px(ys + b_k / 2)))
            c.create_rectangle(xl, 8, xr, 22, fill=C_VEH, outline=C_VEH)
        c.create_line(px(y_c), 5, px(y_c), 40, fill=C_CENTER, width=2, dash=(3, 2))
        c.create_text(W - 4, 4, text=f"B={B:.1f}m", anchor="ne", font=("", 7), fill="#555")
        c.create_text(4, 4, text=f"y_c={y_c:.2f}m", anchor="nw", font=("", 7), fill=C_VEH)

    # ── Výpočet ──────────────────────────────────────────────────────────
    def _get(self, key, typ=float):
        try:
            txt = self._entries[key].get().replace(",", ".")
            return typ(float(txt)) if typ is int else typ(txt)
        except ValueError:
            raise ValueError(f"Neplatná hodnota pro parametr '{key}'.")

    def _run(self):
        # vstupy se čtou v hlavním vlákně (Tk není vláknově bezpečné)
        try:
            e = self._entries
            y_c = None if self._chk_stred_var.get() else self._slider_var.get()
            kw = dict(
                typ=e["typ"].get(), MLC=e["MLC"].get(),
                n=self._get("n", int), dist=self._get("dist"), Ve=self._get("Ve"),
                y_center_MLC=y_c, roznos=bool(e["roznos"].get()), t_voz=self._get("t_voz"),
                obalky=bool(e["obalky"].get()), krok_obalky=self._get("krok_ob"), tisk=False,
                **self._kw_konstrukce())
        except ValueError as exc:
            messagebox.showerror("Chyba vstupu", str(exc))
            return
        self._btn_run.configure(state="disabled")
        self._lbl_stav.configure(text="Počítám…")
        self._vysledek = None
        # Garbage collector musí uklízet Tk objekty (zavřená okna grafů
        # matplotlib/TkAgg – PhotoImage, StringVar, vlastní Tcl interpret)
        # v hlavním vlákně. Kdyby se GC spustil ve výpočetním vlákně, Tkinter
        # hlásí „RuntimeError: main thread is not in main loop“ a „Tcl
        # interpreter is leaked“. Proto: úklid teď v hlavním vlákně a během
        # výpočtu cyklický GC vypnout; zapne se znovu v _cekej().
        gc.collect()
        gc.disable()
        threading.Thread(target=self._compute, args=(kw,), daemon=True).start()
        self.after(150, self._cekej, y_c)

    def _kw_konstrukce(self) -> dict:
        """Parametry konstrukce a MKP společné pro porovnání MLC/Ve i vnitřní síly."""
        e = self._entries
        deska = self._je_deska()
        spara = bool(e["spara"].get()) and not deska
        return dict(
                L=self._get_L(),
                N=1 if deska else self._get("N", int), beton=e["beton"].get(),
                Iy=0.0 if deska else self._get("Iy"),
                spara=spara,
                b_s=self._get("b_s") if spara else 0.0,
                Iy_s=self._get("Iy_s") if spara else 0.0,
                beton_s=e["beton_s"].get() if spara else None,
                typ_konstrukce="deska" if deska else "nosniky",
                h=self._get("h") if deska else 0.0,
                alfa=self._get("alfa"), sikmost=e["sikmost"].get(),
                k_pod=self._k_pod(),
                uloz=e["uloz"].get(), k_rot=self._k_rot(),
                beta_s_pevne=bool(e["beta_s_pevne"].get()),
                b=self._get("b"), nu=self._get("nu"), d=self._get("d"),
                spoj=e["spoj"].get(), ex=self._get("ex"),
        )

    # ── Vnitřní síly pro posudek ────────────────────────────────────────
    def _opt(self, key):
        """Nepovinná hodnota (prázdné → None)."""
        txt = self._entries[key].get().strip().replace(",", ".")
        if not txt:
            return None
        try:
            return float(txt)
        except ValueError:
            raise ValueError(f"Neplatná hodnota pro parametr '{key}'.")

    def _run_sily(self):
        try:
            e = self._entries
            vyb = Vybaveni(chodnik_L=self._get("ch_L"), chodnik_P=self._get("ch_P"),
                           g_chodnik=self._get("g_ch"), g_vozovka=self._get("g_voz"),
                           g_zabradli=self._get("g_zab"), g_svodidla=self._get("g_svo"))
            kw = dict(vybaveni=vyb, A_nosniku=self._opt("A_nos"),
                      gamma_beton=self._get("gamma_b"), g_spary=self._opt("g_sp") or 0.0,
                      A_dobetonavky=self._opt("A_dob") or 0.0,
                      Ve=self._get("Ve"), dyn=self._opt("dyn"), y_Ve=self._opt("y_Ve"),
                      roznos=bool(e["roznos"].get()), t_voz=self._get("t_voz"),
                      krok=self._get("krok_q"), tisk=False, **self._kw_konstrukce())
        except ValueError as exc:
            messagebox.showerror("Chyba vstupu", str(exc))
            return
        self._btn_sily.configure(state="disabled")
        self._lbl_stav_sily.configure(text="Počítám…")
        self._vysledek_sily = None
        gc.collect()
        gc.disable()

        def vypocet():
            try:
                self._vysledek_sily = ("ok", vnitrni_sily(**kw))
            except Exception as exc:
                self._vysledek_sily = ("chyba", str(exc))
        threading.Thread(target=vypocet, daemon=True).start()
        self.after(150, self._cekej_sily)

    def _cekej_sily(self):
        if self._vysledek_sily is None:
            self.after(150, self._cekej_sily)
            return
        stav, val = self._vysledek_sily
        gc.enable()
        gc.collect()
        self._btn_sily.configure(state="normal")
        self._lbl_stav_sily.configure(text="")
        if stav == "ok":
            OknoSil(self, val)
        else:
            messagebox.showerror("Chyba výpočtu", val)

    def _compute(self, kw):
        """Běží ve vedlejším vlákně – nesahá na Tk, jen uloží výsledek."""
        try:
            self._vysledek = ("ok", porovnani_zatizeni(**kw))
        except Exception as exc:
            self._vysledek = ("chyba", str(exc))

    def _cekej(self, y_c):
        """Hlavní vlákno: čeká na dokončení výpočtu."""
        if self._vysledek is None:
            self.after(150, self._cekej, y_c)
            return
        stav, val = self._vysledek
        gc.enable()
        gc.collect()          # úklid v hlavním vlákně
        self._btn_run.configure(state="normal")
        self._lbl_stav.configure(text="")
        if stav == "ok":
            self._cr = val
            self._show_results(val, y_c)
        else:
            messagebox.showerror("Chyba výpočtu", val)

    def _show_results(self, cr: ComparisonResult, y_c):
        gov = cr.rozhodujici
        self._tree.delete(*self._tree.get_children())
        for r in cr.rezy:
            x = r.x_MLC if r.rez.typ == "M+" else r.rez.x
            tags = []
            if r.vyuziti_2D >= 100:
                tags.append("fail")
            if r is gov:
                tags.append("gov")
            self._tree.insert("", "end", values=(
                r.rez.id,
                f"{x:.2f}", f"{r.MLC_1D:.1f}", f"{r.Ve_1D:.1f}", f"{r.vyuziti_1D:.1f} %",
                f"{r.MLC_2D:.1f}", f"{r.Ve_2D:.1f}", f"{r.vyuziti_2D:.1f} %",
                f"{cr.popisek(r.k_MLC)} / {cr.popisek(r.k_Ve)}"), tags=tuple(tags))
        self._rez_cb.configure(values=["(rozhodující)"] + [r.rez.id for r in cr.rezy])
        self._rez_var.set("(rozhodující)")

        K = cr.K
        stav = lambda ok: "PROJDE ✓" if ok else "NEPROJDE ✗"
        lines = [
            "=" * 70,
            f"  VÝSLEDKY – DESKOVÝ MODEL, SPOJITÝ NOSNÍK",
            f"  {cr.MLC} vs Ve = {cr.Ve:g} t",
            (f"  DESKA {K.popis()},  b = {K.b:g} m,  h = {K.h:g} m  (2D hodnoty na pás 1 m)"
             if K.je_deska else
             f"  {K.popis()},  N = {K.N},  b = {K.b:g} m,  Iy = {K.Iy:.5g} m⁴"),
            f"  Beton {self._entries['beton'].get()}: E = Ecm = {K.E:g} MPa",
            (f"  Spára: b_s = {K.b_s:g} m, Iy_s = {K.Iy_s:.5g} m⁴, h_s = {K.h_spary:.4f} m, "
             f"B = {K.B:g} m\n  Beton spáry {self._entries['beton_s'].get()}: "
             f"E_s = Ecm = {K.E_spary:g} MPa" if K.spara else
             ("" if K.je_deska else "  Bez spáry")),
            (f"  Šikmost α = {K.alfa:g}° {'pravá' if K.sikmost == 'prava' else 'levá'}"
             if K.sikmy else "  Kolmý most (α = 90°)"),
            f"  d = {K.d:g} m (řezy V v x_k ± d)",
            f"  Podpory liniové: {K.popis_ulozeni()}",
            f"  Poloha MLC: y_c = {'střed průřezu' if y_c is None else f'{y_c:.3f} m'}",
            ("" if K.je_deska else f"  Ekvivalentní tloušťka desky: h = {K.h_ekv:.4f} m"),
            f"  {cr.popis}",
            "=" * 70,
            "",
            f"  Rozhoduje: {gov.rez.id}",
            f"    využití 2D (nejvíc namáhaný {'pás 1 m' if K.je_deska else 'nosník'}): "
            f"{gov.vyuziti_2D:6.1f} %  → {stav(cr.projde)}",
            f"    využití 1D (celý most):              {cr.max_vyuziti_1D:6.1f} %  → {stav(cr.projde_1D)}",
            f"    MLC: {cr.popisek(gov.k_MLC)}, {gov.MLC_2D:.1f} {gov.jednotka}   "
            f"Ve: {cr.popisek(gov.k_Ve)}, {gov.Ve_2D:.1f} {gov.jednotka}",
            "",
            "  Kontrola rovnováhy Σ nosníků vs 1D statika (rozhodující řez):",
        ]
        if gov.stav_MLC is not None and not (gov.stav_MLC.dM != gov.stav_MLC.dM):
            lines.append(f"    MLC: M {gov.stav_MLC.dM:.3f} %   V {gov.stav_MLC.dV:.3f} %")
            lines.append(f"    Ve : M {gov.stav_Ve.dM:.3f} %   V {gov.stav_Ve.dV:.3f} %")
        elif gov.stav_MLC is not None:
            lines.append("    (u šikmé desky se nevyhodnocuje – výsledky podél čar ‖ s osou podpory)")
        vm, vv = cr.rozhodujici_typ("M"), cr.rozhodujici_typ("V")
        lines += ["", "  Rozhodující stavy (tlačítko „Zatížení – Mmax, Vmax“):"]
        for nm, rr in (("M", vm), ("V", vv)):
            if rr is not None:
                lines.append(f"    {nm}: {rr.rez.id:<22} využití 2D {rr.vyuziti_2D:6.1f} %")
        if cr.varovani:
            import textwrap
            lines.append("")
            for v_ in cr.varovani:
                lines += ["  ! " + l for l in textwrap.wrap(v_, 66)]
        lines.append("=" * 70)
        t = self._txt
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", "\n".join(lines))
        t.configure(state="disabled")

    # ── Grafy ────────────────────────────────────────────────────────────
    def _index_rezu(self):
        v = self._rez_var.get()
        if v == "(rozhodující)" or self._cr is None:
            return None
        for i, r in enumerate(self._cr.rezy):
            if r.rez.id == v:
                return i
        return None

    def _k_pod(self):
        """Tuhost pružné podpory: GUI v MN/m/m → kN/m/m; prázdné / 0 = tuhá."""
        txt = self._entries["k_v"].get().strip().replace(",", ".")
        if txt in ("", "-") or txt.lower() in ("tuha", "tuhá", "inf"):
            return None
        try:
            v = float(txt)
        except ValueError:
            raise ValueError("Neplatná hodnota tuhosti podpory k_v.")
        if v < 0:
            raise ValueError("Tuhost podpory k_v musí být ≥ 0 (0 = tuhá).")
        return v * 1000.0 if v > 0 else None

    def _k_rot(self):
        """Tuhost pružného vetknutí: GUI v MNm/rad/m → kNm/rad/m; prázdné = dokonalé."""
        if self._entries["uloz"].get() != "vetknuti":
            return None
        txt = self._entries["k_rot"].get().strip().replace(",", ".")
        if txt in ("", "-") or txt.lower() in ("inf", "tuhe", "tuhé"):
            return None
        try:
            v = float(txt)
        except ValueError:
            raise ValueError("Neplatná hodnota tuhosti vetknutí k_φ.")
        if v <= 0:
            raise ValueError("Tuhost vetknutí k_φ musí být kladná "
                             "(prázdné = dokonalé vetknutí; pro kloub zvolte kloubové uložení).")
        return v * 1000.0

    def _pomer(self) -> float:
        try:
            v = float(self._entries["pomer"].get().replace(",", "."))
            return v if v > 0 else 2.0
        except (ValueError, KeyError):
            return 2.0

    def _pripraven(self) -> bool:
        if self._cr is None:
            messagebox.showinfo("Info", "Nejprve spusťte výpočet.")
            return False
        return True

    def _plot(self, fn, **kw):
        if not self._pripraven():
            return
        try:
            fn(self._cr, show=True, **kw)
        except ValueError as exc:
            messagebox.showinfo("Info", str(exc))

    def _plot_rez(self, fn, **kw):
        if not self._pripraven():
            return
        fn(self._cr, i=self._index_rezu(), show=True, **kw)

    def _plot_zatizeni(self):
        """Vybraný řez → jeden graf; „(rozhodující)“ → rozhodující stav pro M i pro V."""
        if not self._pripraven():
            return
        i = self._index_rezu()
        if i is not None:
            plot_zatizeni(self._cr, i=i, show=True)
            return
        idx = [self._cr.rezy.index(r) for r in (self._cr.rozhodujici_typ("M"),
                                               self._cr.rozhodujici_typ("V")) if r is not None]
        for j in idx:
            plot_zatizeni(self._cr, i=j, show=False)
        import matplotlib.pyplot as plt
        plt.show()


class OknoSil(tk.Toplevel):
    """Výsledky vnitřních sil g0, g − g0, q po výstupech + export do Posudku PB."""

    def __init__(self, master, vys: VysledekSil):
        super().__init__(master)
        self.vys = vys
        jm, jv = vys.jednotky
        self.title("Vnitřní síly pro posudek – g0, g − g0, q")
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)
        txt = vys.popis + "\n" + "\n".join(f"{s.nazev}: {s.popis}" for s in vys.stavy.values())
        if vys.varovani:
            txt += "\n" + "\n".join("! " + w for w in vys.varovani)
        ttk.Label(frm, text=txt, wraplength=980, justify="left").pack(anchor="w")

        stavy = list(vys.stavy)
        cols = ["vyst", "y"] + [f"M_{s}" for s in stavy] + [f"V_{s}" for s in stavy] + \
               ["M_Ed", "V_Ed"]
        heads = ["Výstup", "y [m]"] + [f"M {s}" for s in stavy] + [f"|V| {s}" for s in stavy] + \
                ["M_Ed", "V_Ed"]
        self._tree = ttk.Treeview(frm, columns=cols, show="headings",
                                  height=min(18, max(6, vys.n_vyst)))
        for c, h in zip(cols, heads):
            self._tree.heading(c, text=h)
            self._tree.column(c, width=80 if c != "vyst" else 90, anchor="e")
        self._tree.tag_configure("gov", background="#fff3cd")
        self._tree.pack(fill="both", expand=True, pady=6)
        self._tree.bind("<<TreeviewSelect>>", self._vyber_radek)
        ttk.Label(frm, text=f"Jednotky {jm}, {jv}; M_Ed, V_Ed = MSÚ 6.10 včetně g0 "
                            "(součinitele níže). Žlutě nejzatíženější výstup.",
                  foreground="gray").pack(anchor="w")

        r1 = ttk.Frame(frm); r1.pack(fill="x", pady=4)
        ttk.Label(r1, text="Posuzovaný výstup:").pack(side="left")
        self._vyst_var = tk.StringVar()
        self._cb = ttk.Combobox(r1, textvariable=self._vyst_var, values=vys.popisky,
                                width=12, state="readonly")
        self._cb.pack(side="left", padx=4)
        ttk.Label(r1, text="kritérium").pack(side="left", padx=(10, 2))
        self._krit = tk.StringVar(value="M")
        kcb = ttk.Combobox(r1, textvariable=self._krit, values=["M", "M-", "V"], width=4,
                           state="readonly")
        kcb.pack(side="left")
        kcb.bind("<<ComboboxSelected>>", lambda _: self._obnov())
        ttk.Button(r1, text="Průběhy sil", command=self._graf_sil).pack(side="left", padx=6)
        ttk.Button(r1, text="Příčné rozdělení", command=self._graf_pricne).pack(side="left")

        # součinitele a export
        lf = ttk.LabelFrame(frm, text="Export do Posudku PB", padding=6)
        lf.pack(fill="x", pady=6)
        s = vys.soucinitele
        self._souc = {}
        r2 = ttk.Frame(lf); r2.pack(fill="x")
        for key, lab in (("gamma_G", "γ_G"), ("gamma_G_inf", "γ_G,inf"), ("xi", "ξ"),
                         ("gamma_Q", "γ_Q"), ("psi0", "ψ0"), ("psi1", "ψ1"), ("psi2", "ψ2")):
            ttk.Label(r2, text=lab).pack(side="left", padx=(6, 2))
            v = tk.StringVar(value=f"{getattr(s, key):g}")
            ent = ttk.Entry(r2, textvariable=v, width=6)
            ent.pack(side="left")
            ent.bind("<FocusOut>", lambda _: self._obnov())
            ent.bind("<Return>", lambda _: self._obnov())
            self._souc[key] = v
        ttk.Label(r2, text="(pro Ve ověřit)", foreground="gray").pack(side="left", padx=6)
        r3 = ttk.Frame(lf); r3.pack(fill="x", pady=4)
        ttk.Label(r3, text="Režim").pack(side="left", padx=(6, 2))
        self._rezim = tk.StringVar(value="kombinace")
        ttk.Combobox(r3, textvariable=self._rezim, values=["kombinace", "zatezovaci_stavy"],
                     width=16, state="readonly").pack(side="left")
        ttk.Label(r3, text="MSÚ").pack(side="left", padx=(10, 2))
        self._msu = tk.StringVar(value="6.10ab")
        ttk.Combobox(r3, textvariable=self._msu, values=["6.10ab", "6.10"], width=7,
                     state="readonly").pack(side="left")
        ttk.Label(r3, text="Délka nosníku L").pack(side="left", padx=(10, 2))
        self._Lnos = tk.StringVar(value=f"{vys.K.Ltot:g}")
        ttk.Entry(r3, textvariable=self._Lnos, width=8).pack(side="left")
        ttk.Label(r3, text="[m] (L0 = rozpětí; se vstupem PB se bere z něj)",
                  foreground="gray").pack(side="left", padx=4)
        r4 = ttk.Frame(lf); r4.pack(fill="x")
        self._pb = tk.StringVar(value="")
        ttk.Label(r4, text="Vstup posudku PB (.toml)").pack(side="left", padx=(6, 2))
        ttk.Entry(r4, textvariable=self._pb, width=60).pack(side="left")
        ttk.Button(r4, text="…", width=3, command=self._vyber_pb).pack(side="left", padx=2)
        ttk.Button(r4, text="Uložit výsledky a export…", command=self._export
                   ).pack(side="left", padx=10)
        self._obnov()

    def _soucinitele(self):
        from .vnitrni_sily import Soucinitele
        try:
            return Soucinitele(**{k: float(v.get().replace(",", "."))
                                  for k, v in self._souc.items()})
        except ValueError:
            raise ValueError("Neplatný součinitel kombinace.")

    def _obnov(self):
        try:
            self.vys.soucinitele = self._soucinitele()
        except ValueError as exc:
            messagebox.showerror("Chyba vstupu", str(exc), parent=self)
            return
        gov = self.vys.rozhodujici(self._krit.get())
        self._tree.delete(*self._tree.get_children())
        stavy = list(self.vys.stavy)
        for o, d in enumerate(self.vys.souhrn()):
            vals = [d["vystup"], f"{d['y']:.2f}"] + [f"{d['M_' + s]:.1f}" for s in stavy] + \
                   [f"{d['V_' + s]:.1f}" for s in stavy] + [f"{d['M_Ed']:.1f}", f"{d['V_Ed']:.1f}"]
            self._tree.insert("", "end", iid=str(o), values=vals,
                              tags=("gov",) if o == gov else ())
        self._vyst_var.set(self.vys.popisky[gov])

    def _vyber_radek(self, _=None):
        sel = self._tree.selection()
        if sel:
            self._vyst_var.set(self.vys.popisky[int(sel[0])])

    def _o(self) -> int:
        return self.vys.index(self._vyst_var.get())

    def _graf_sil(self):
        from .plotting_sily import plot_sily
        plot_sily(self.vys, self._o(), show=True)

    def _graf_pricne(self):
        from .plotting_sily import plot_pricne
        plot_pricne(self.vys, show=True)

    def _vyber_pb(self):
        from tkinter import filedialog
        p = filedialog.askopenfilename(parent=self, title="Vstup Posudku PB",
                                       filetypes=[("TOML", "*.toml"), ("vše", "*.*")])
        if p:
            self._pb.set(p)

    def _export(self):
        from tkinter import filedialog
        from .export_pb import uloz_vysledky
        from .vstup_sily import uloz_grafy
        try:
            self.vys.soucinitele = self._soucinitele()
            Ln = float(self._Lnos.get().replace(",", ".")) if self._Lnos.get().strip() else None
        except ValueError as exc:
            messagebox.showerror("Chyba vstupu", str(exc), parent=self)
            return
        slozka = filedialog.askdirectory(parent=self, title="Složka pro výsledky")
        if not slozka:
            return
        try:
            soubory = uloz_vysledky(self.vys, slozka, vystup=self._vyst_var.get(),
                                    L_nosniku=Ln, rezim=self._rezim.get(), msu=self._msu.get(),
                                    pb_vstup=self._pb.get().strip() or None)
            soubory += uloz_grafy(self.vys, slozka, self._vyst_var.get())
        except Exception as exc:
            messagebox.showerror("Chyba exportu", str(exc), parent=self)
            return
        messagebox.showinfo("Uloženo", "\n".join(soubory), parent=self)


def spustit_gui():
    App().mainloop()
