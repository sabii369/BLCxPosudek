"""
gui.py
======
Spojený program BLC × Posudek PB – grafické rozhraní Posudku PB s novou první
kartou „Most a zatížení (BLC)“:

  0  Most a zatížení (BLC)   konstrukce mostu, vybavení (g − g0), chodci, vybrané vozidlo (q:
                              Vn, Vr, Ve podle ČSN 73 6222 nebo MLC), výpočet vnitřních sil,
                              výběr posuzovaného nosníku, volba výpočtu zatížitelnosti
  1 – 4, 6, 7                 karty Posudku PB beze změny (materiály, průřez, nosník
                              a předpětí, výztuž, nastavení, výsledky)
  5  Zatížení a čas           prostředí a časová osa; vnější zatížení se NEZADÁVÁ –
                              přebírá se z obálek vnitřních sil posuzovaného nosníku

Rozpětí L0, délka L a třída betonu jsou společné (pole na kartě 0 jsou propojená
s kartami 1 a 3), A a Iy nosníku se berou z průřezu posudku, γ_G, ξ a kombinace MSÚ
z nastavení posouzení.  F5 spočítá most (je-li třeba) i posudek.
"""

from __future__ import annotations
from blc.cisla import cz
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import matplotlib.pyplot as plt
import numpy as np

from blc.vehicles import seznam_mlc
from blc.vnitrni_sily import nahled_mostu, vnitrni_sily, VysledekSil
from pb_posudek import gui as pbgui
from pb_posudek.gui import Aplikace, Formular, Graf, Tabulka, TRIDY_BETONU

from .vypocet import (VYCHOZI_BLC, klic_mkp, parametry_blc, spocti, vyber_nosnik,
                      vlastnosti_prurezu, vys_se_soucinitely, zatizeni_z_blc)

KOREN = Path(__file__).resolve().parents[1]
PRIKLAD_MOST = KOREN / "priklady" / "most_KA67_12.toml"
NAZEV = "BLC × Posudek PB"
VOZIDLA_GUI = {"Vn": "Vn – normální", "Vr": "Vr – výhradní", "Ve": "Ve – výjimečná",
               "MLC_k": "MLC kolové", "MLC_p": "MLC pásové"}
VOZIDLA_KLIC = {v: k for k, v in VOZIDLA_GUI.items()}
VOZIDLA_KLIC["Ve"] = "Ve"
DRUHY_ZAT_GUI = {"vse": "Vn, Vr i Ve", "vozidlo": "jen zvolené vozidlo"}
DRUHY_ZAT_KLIC = {v: k for k, v in DRUHY_ZAT_GUI.items()}
PROTOKOL_GUI = {"souhrn": "souhrn – posudky pro zvolené vozidlo", "Vn": "jen Vn – posudky při Vn",
                "Vr": "jen Vr – posudky při Vr", "Ve": "jen Ve – posudky při Ve"}
PROTOKOL_KLIC = {v: k for k, v in PROTOKOL_GUI.items()}
SEDA = "#52514e"
REZIMY = ("Posouzení", "Zatížitelnost")
GRAF_REZ = "Příčný řez – poloha zatížení"
ZNACKA_POS = " ●"                 # posuzovaný nosník v tabulce karty 0 (◄ Segoe UI kreslí jako šipku)
GRAFY_BLC = ["Průběhy sil – vybraný nosník", "Vnitřní síly na nosnících (půdorys)",
             "Příčné rozdělení a vybavení", GRAF_REZ]


def _popisky_formulare(fm) -> dict:
    """{klíč: popisek} polí Formular (popisek leží v mřížce vlevo od pole)."""
    out = {}
    for k, w in fm.widgety.items():
        gi = w.grid_info()
        out[k] = fm.grid_slaves(row=int(gi["row"]), column=int(gi["column"]) - 1)[0]
    return out


def rozloz_formular(fm, viditelne, sloupcu: int = 2) -> None:
    """Zobrazí jen pole `viditelne` (v původním pořadí, bez mezer v mřížce); skrytá pole
    si hodnotu ponechají."""
    if not hasattr(fm, "_popisky"):
        fm._popisky = _popisky_formulare(fm)
    i = 0
    for k, *_ in fm.pole:
        w, lab = fm.widgety[k], fm._popisky[k]
        if k in viditelne:
            r, c = divmod(i, sloupcu)
            i += 1
            lab.grid(row=r, column=2 * c, sticky="w", padx=(4, 6), pady=2)
            w.grid(row=r, column=2 * c + 1, sticky="we", padx=(0, 14), pady=2)
        else:
            lab.grid_remove()
            w.grid_remove()


class AplikaceMost(Aplikace):
    """Okno Posudku PB rozšířené o model mostu (BLC)."""

    def __init__(self, soubor: str | None = None):
        self._blc_vys: VysledekSil | None = None
        self._blc_klic: str | None = None
        self._protokol_po_vypoctu = False
        priklad = soubor is None and PRIKLAD_MOST.exists()
        super().__init__(str(PRIKLAD_MOST) if priklad else soubor)
        if priklad:
            self.soubor = None
            self.vystup = Path.cwd() / "vystup"
            self.title(f"{NAZEV} – příklad {PRIKLAD_MOST.name}")
        self.nb.select(0)

    def title(self, s=None):  # noqa: D401 – názvy oken posudku přejmenovat
        if s is None:
            return super().title()
        return super().title(str(s).replace("PB posudek", NAZEV, 1))

    # =====================================================================
    # Lišta – režim výpočtu (posouzení / zatížitelnost)
    # =====================================================================
    def _lista(self):
        super()._lista()
        tb = self.btn_vypocet.master
        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(tb, text="Režim:").pack(side="left")
        self.var_zat = tk.BooleanVar(value=False)
        self.var_rezim = tk.StringVar(value=REZIMY[0])
        for r in REZIMY:
            ttk.Radiobutton(tb, text=r, value=r, variable=self.var_rezim,
                            command=self._zmena_rezimu).pack(side="left", padx=(4, 0))
        self.fr_zat = ttk.Frame(tb)
        ttk.Label(self.fr_zat, text="druhy").pack(side="left", padx=(8, 2))
        self.var_zat_druhy = tk.StringVar(value=DRUHY_ZAT_GUI["vse"])
        ttk.Combobox(self.fr_zat, textvariable=self.var_zat_druhy, state="readonly", width=17,
                     values=list(DRUHY_ZAT_GUI.values())).pack(side="left")
        ttk.Label(self.fr_zat, text="protokol").pack(side="left", padx=(8, 2))
        self.var_zat_prot = tk.StringVar(value=PROTOKOL_GUI["souhrn"])
        cb = ttk.Combobox(self.fr_zat, textvariable=self.var_zat_prot, state="readonly", width=32,
                          values=list(PROTOKOL_GUI.values()))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._prepni_protokol())

    def _zmena_rezimu(self, *_):
        """Přepínač Posouzení / Zatížitelnost: var_zat, tlačítko výpočtu, volby zatížitelnosti."""
        zat = self.var_rezim.get() == REZIMY[1]
        if self.var_zat.get() != zat:
            self.var_zat.set(zat)
        if zat:
            self.fr_zat.pack(side="left")
        else:
            self.fr_zat.pack_forget()
        self.btn_vypocet.configure(text="▶  Zatížitelnost (F5)" if zat else "▶  Posouzení (F5)")
        if hasattr(self, "f_voz"):
            self._viditelnost()
            self._naplanuj_nahled()

    # =====================================================================
    # Karta 0 – most a zatížení
    # =====================================================================
    def _zalozka_materialy(self):
        self._zalozka_most()
        super()._zalozka_materialy()

    def _zalozka_most(self):
        vnejsi = ttk.Frame(self.nb)
        self.nb.add(vnejsi, text="0  Most a zatížení (BLC)")
        pan = ttk.Panedwindow(vnejsi, orient="horizontal")
        pan.pack(fill="both", expand=True)
        # levý sloupec se svislým posuvníkem
        lev = ttk.Frame(pan)
        cv = tk.Canvas(lev, highlightthickness=0, width=640)
        sb = ttk.Scrollbar(lev, orient="vertical", command=cv.yview)
        f = ttk.Frame(cv, padding=8)
        okno = cv.create_window((0, 0), window=f, anchor="nw")
        f.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(okno, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        cv.bind("<Enter>", lambda e: cv.bind_all("<MouseWheel>", lambda ev: cv.yview_scroll(
            int(-ev.delta / 120), "units")))
        cv.bind("<Leave>", lambda e: cv.unbind_all("<MouseWheel>"))
        pan.add(lev, weight=2)
        self.after(300, lambda: pan.sashpos(0, max(560, int(pan.winfo_width() * 0.44))))
        zm = self._naplanuj_nahled

        lf = ttk.LabelFrame(f, text="Nosná konstrukce", padding=6)
        lf.pack(fill="x", pady=4)
        self.lf_kon = lf
        self._ram_propojene = ttk.Frame(lf)
        self._ram_propojene.pack(fill="x")
        self.f_kon = Formular(lf, [
            ("typ_konstrukce", "Typ konstrukce", "choice", ["nosniky", "deska"]),
            ("N", "Počet nosníků N", "int", None),
            ("b", "Šířka nosníku b [m]", "float", None),
            ("d", "Účinná výška d [m]", "float", None),
            ("prurez_z_posudku", "A, Iy z průřezu (karta 2)", "bool", True),
            ("nu", "Poissonovo číslo ν", "float", None),
            ("A_nosniku", "A nosníku [m²]", "optfloat", None),
            ("A_dobetonavky", "A dobetonávky [m²]", "optfloat", None),
            ("Iy", "Iy nosníku [m⁴]", "optfloat", None),
            ("h", "Tloušťka desky h [m]", "optfloat", None)], sloupcu=2, pri_zmene=zm)
        self.f_kon.pack(fill="x")
        self.lbl_prurez_blc = ttk.Label(lf, text="", foreground=SEDA)
        self.lbl_prurez_blc.pack(anchor="w", pady=(2, 0))

        lf = ttk.LabelFrame(f, text="Podélná spára mezi nosníky", padding=6)
        lf.pack(fill="x", pady=4)
        self.lf_spara = lf
        self.f_spara = Formular(lf, [
            ("spara", "Spára (deskový prvek, kloubově)", "bool", False),
            ("b_s", "Šířka spáry b_s [m]", "optfloat", None),
            ("Iy_s", "Iy spáry [m⁴]", "optfloat", None),
            ("beton_s", "Beton spáry", "choice", TRIDY_BETONU),
            ("g_spary", "Tíha výplně spáry [kN/m]", "optfloat", None)], sloupcu=2, pri_zmene=zm)
        self.f_spara.pack(fill="x")

        lf = ttk.LabelFrame(f, text="Uložení a šikmost", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_uloz = Formular(lf, [
            ("alfa", "Šikmost α [°]", "float", None),
            ("sikmost", "Šikmost", "choice", ["prava", "leva"]),
            ("k_v", "k_v [MN/m/m]", "optfloat", None),
            ("uloz", "Uložení", "choice", ["tvrde", "mekke", "vetknuti"]),
            ("k_rot", "Vetknutí k_φ [MNm/rad/m]", "optfloat", None),
            ("spoj", "Spojení nosníků", "choice", ["kloub", "deska"]),
            ("beta_s_pevne", "β_s = 0 (srovnání)", "bool", False)],
            sloupcu=2, pri_zmene=zm)
        self.f_uloz.pack(fill="x")
        ttk.Label(lf, foreground=SEDA, wraplength=530, justify="left", text=(
            "α = 90° kolmý most; k_v = tuhost podpory, prázdné / 0 = tuhá; k_φ prázdné = dokonalé "
            "vetknutí (jen uložení „vetknuti“); spojení nosníků bez spáry; β_s = 0 i u pružné "
            "podpory = zjednodušená vazba (SCIA s vetknutou rotací podél podpory) – jen pro srovnání"
            )).pack(anchor="w")

        lf = ttk.LabelFrame(f, text="Ostatní stálé zatížení g − g0 (vybavení mostu)", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_vyb = Formular(lf, [
            ("chodnik_L", "Šířka chodníku vlevo [m]", "float", None),
            ("chodnik_P", "Šířka chodníku vpravo [m]", "float", None),
            ("g_chodnik", "Tíha skladby chodníku [kN/m²]", "float", None),
            ("g_vozovka", "Tíha skladby vozovky [kN/m²]", "float", None),
            ("g_zabradli", "Zábradlí – každá strana [kN/m]", "float", None),
            ("g_svodidla", "Svodidlo – každá strana [kN/m]", "float", None)],
            sloupcu=2, pri_zmene=zm)
        self.f_vyb.pack(fill="x")
        ttk.Label(lf, text="Další liniová zatížení (římsa …), y = osa od levého okraje:",
                  foreground=SEDA).pack(anchor="w", pady=(4, 0))
        self.t_liniova = Tabulka(lf, [("nazev", "Název", 140, "str", None),
                                      ("g", "g [kN/m]", 70, "float", None),
                                      ("y", "y osy [m]", 70, "float", None),
                                      ("sirka", "šířka [m]", 70, "optfloat", None)],
                                 pri_zmene=zm, vyska=3, vychozi={"sirka": 0.2})
        self.t_liniova.pack(fill="x")

        lf = ttk.LabelFrame(f, text="Zatížení chodců (q_ch)", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_chodci = Formular(lf, [
            ("q_chodnik", "Zatížení chodníků [kN/m²]", "optfloat", None)], sloupcu=2, pri_zmene=zm)
        self.f_chodci.pack(fill="x")
        ttk.Label(lf, foreground=SEDA, justify="left", wraplength=540, text=(
            "Na obou chodnících, v nepříznivých částech plochy vlivu (obálka). Prázdné = podle "
            "ČSN 73 6222: s Vn a Vr 2,5 kN/m² (tab. 7.1, 7.2), s Ve 0 (chodci vyloučeni, čl. 3.1.4); "
            "0 = bez zatížení chodců.")).pack(anchor="w")

        lf = ttk.LabelFrame(f, text="Vozidlo, které přejíždí most (q)", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_voz = Formular(lf, [
            ("vozidlo", "Vozidlo / schéma", "choice", list(VOZIDLA_GUI.values())),
            ("Vn", "Tíha Vn [t]", "optfloat", None),
            ("Vr", "Tíha Vr [t]", "optfloat", None),
            ("Ve", "Tíha Ve [t]", "optfloat", None),
            ("MLC", "Třída MLC", "choice", seznam_mlc()),
            ("dist", "Kolona – vzdálenost vozidel [m]", "optfloat", None),
            ("dyn", "δ (prázdné = ČSN 73 6222)", "optfloat", None),
            ("y_vozidla", "Osa vozidla Ve / MLC y [m]", "optfloat", None),
            ("roznos", "Roznos kola do střednice desky", "bool", True),
            ("t_voz", "Tloušťka vozovky (roznos) [m]", "float", None),
            ("krok", "Krok poloh vozidla [m]", "float", None),
            ("ex", "Velikost prvku MKP [m]", "float", None)], sloupcu=2, pri_zmene=zm)
        self.f_voz.pack(fill="x")
        ttk.Label(lf, foreground=SEDA, justify="left", wraplength=540, text=(
            "ČSN 73 6222: Vn – schéma obr. 7.1 (vn = Vn/13,33; dvounáprava ≥ 16 t, jinak náhradní "
            "náprava), pruh č. 1 u kraje vozovky u užšího chodníku; Vr – jediné vozidlo (> 50 t "
            "šestinápravové, > 16 t třínápravové, jinak dvounápravové) vnějším okrajem u téhož "
            "kraje; Ve – devítinápravová souprava v ose vozovky (nebo v zadané ose y). MLC: jedno "
            "vozidlo, kolona (prázdné = jedno vozidlo). Vozidla projíždějí v obou směrech. δ prázdné "
            "= kap. 8: Vn δ1/δ2/δ3 podle počtu pruhů, Vr δ1 (z vlastní frekvence), Ve 1,05; "
            "MLC 1,0.")).pack(anchor="w")

        lf = ttk.LabelFrame(f, text="Předání do posudku", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_pred = Formular(lf, [
            ("vystup", "Posuzovaný nosník", "choice", ["auto"]),
            ("kriterium", "Nejzatíženější podle", "choice", ["M", "M-", "V"]),
            ("rezim", "Předání zatížení", "choice", ["kombinace", "zatezovaci_stavy"])],
            sloupcu=2, pri_zmene=zm)
        self.f_pred.pack(fill="x")
        ttk.Label(lf, foreground=SEDA, justify="left", wraplength=530, text=(
            "auto = nejzatíženější nosník podle MSÚ (6.10, včetně g0); u zatížitelnosti nejzatíženější "
            "samotným zatížením Vn / Vr / Ve. Dílčí součinitele všech zatížení "
            "(stálá, doprava, chodci, teplota) jsou na kartě 5, kombinace MSÚ na kartě 6."
        )).pack(anchor="w")

        # pravý sloupec – výpočet a výsledky
        prav = ttk.Frame(pan, padding=(8, 8, 4, 4))
        pan.add(prav, weight=3)
        bt = ttk.Frame(prav)
        bt.pack(fill="x")
        self.btn_blc = ttk.Button(bt, text="▶  Jen vnitřní síly mostu", command=self.spocitej_blc)
        self.btn_blc.pack(side="left")
        ttk.Label(bt, foreground=SEDA, text="posouzení / zatížitelnost: tlačítko v liště nahoře (F5)"
                  ).pack(side="left", padx=8)
        self.lbl_blc = ttk.Label(prav, text="Vnitřní síly mostu nejsou spočteny.",
                                 foreground="#b42323", wraplength=700, justify="left")
        self.lbl_blc.pack(anchor="w", pady=4)
        cols = ("vyst", "y", "M_g0", "M_g", "M_qch", "M_q", "V_g0", "V_g", "V_qch", "V_q",
                "M_Ed", "V_Ed")
        heads = ("Nosník", "y [m]", "M g0", "M g−g0", "M chodci", "M doprava", "|V| g0",
                 "|V| g−g0", "|V| chodci", "|V| doprava", "M_Ed", "V_Ed")
        self.t_blc = ttk.Treeview(prav, columns=cols, show="headings", height=10,
                                  selectmode="browse")
        for c, h in zip(cols, heads):
            self.t_blc.heading(c, text=h)
            self.t_blc.column(c, width=62 if c != "vyst" else 74, anchor="e")
        self.t_blc.tag_configure("pos", background="#fff3cd", font=("Segoe UI", 9, "bold"))
        self.t_blc.pack(fill="x")
        self.t_blc.bind("<<TreeviewSelect>>", lambda e: self._graf_blc())
        self.t_blc.bind("<Double-1>", self._nastav_posuzovany)
        ttk.Label(prav, foreground=SEDA, text=(
            "Jednotky kNm, kN (deska: na pás 1 m). ● tučně = posuzovaný nosník; dvojklik = "
            "posuzovat tento nosník. M_Ed, V_Ed = MSÚ 6.10 vč. g0.")).pack(anchor="w")
        r = ttk.Frame(prav)
        r.pack(fill="x", pady=(6, 2))
        ttk.Label(r, text="Graf:").pack(side="left")
        self.var_graf_blc = tk.StringVar(value="Průběhy sil – vybraný nosník")
        cb = ttk.Combobox(r, textvariable=self.var_graf_blc, state="readonly", width=34,
                          values=GRAFY_BLC)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self._graf_blc())
        self.g_blc = Graf(prav, figsize=(8, 5))
        self.g_blc.pack(fill="both", expand=True)
        self._nahled_klic = None
        self._nahled_zobrazen = False
        # pole karty 0 podle typu konstrukce, spáry, uložení, vozidla a režimu
        for fm, klice in ((self.f_kon, ("typ_konstrukce", "prurez_z_posudku")), (self.f_spara, ("spara",)),
                          (self.f_uloz, ("uloz",)), (self.f_voz, ("vozidlo",))):
            for k in klice:
                fm.prom[k].trace_add("write", lambda *_: self._viditelnost())
        for fm in (self.f_kon, self.f_spara, self.f_uloz, self.f_vyb, self.f_chodci, self.f_voz, self.f_pred):
            fm.columnconfigure(1, minsize=110)
            fm.columnconfigure(3, minsize=110)
        self.after_idle(self._viditelnost)

    def _viditelnost(self):
        """Na kartě 0 jen pole platná pro typ konstrukce, spáru, uložení, vozidlo a režim."""
        kon = self.f_kon.prom
        deska = kon["typ_konstrukce"].get() == "deska"
        prevzit = bool(kon["prurez_z_posudku"].get())
        vid = {"typ_konstrukce", "d", "nu"}
        vid |= {"h"} if deska else {"N", "b", "prurez_z_posudku", "A_dobetonavky"}
        if not deska and not prevzit:
            vid |= {"A_nosniku", "Iy"}
        rozloz_formular(self.f_kon, vid)
        if deska:
            self.lf_spara.pack_forget()
        elif not self.lf_spara.winfo_manager():
            self.lf_spara.pack(fill="x", pady=4, after=self.lf_kon)
        spara = bool(self.f_spara.prom["spara"].get())
        rozloz_formular(self.f_spara, {"spara"} | ({"b_s", "Iy_s", "beton_s", "g_spary"} if spara else set()))
        vid = {"alfa", "sikmost", "k_v", "uloz", "beta_s_pevne"}
        if self.f_uloz.prom["uloz"].get() == "vetknuti":
            vid.add("k_rot")
        if not deska and not spara:
            vid.add("spoj")
        rozloz_formular(self.f_uloz, vid)
        voz = VOZIDLA_KLIC.get(self.f_voz.prom["vozidlo"].get(), self.f_voz.prom["vozidlo"].get())
        zat = bool(self.var_zat.get())
        vid = {"vozidlo", "dyn", "roznos", "t_voz", "krok", "ex"}
        if zat:
            vid |= {"Vn", "Vr", "Ve", "y_vozidla"}         # referenční tíhy všech druhů
        elif voz in ("Vn", "Vr", "Ve"):
            vid |= {voz} | ({"y_vozidla"} if voz == "Ve" else set())
        else:
            vid |= {"MLC", "dist", "y_vozidla"}
        rozloz_formular(self.f_voz, vid)

    def _propoj_s_posudkem(self):
        """Pole L, L0 a beton na kartě 0 sdílejí proměnné s kartami 1 a 3."""
        fr = self._ram_propojene
        for i, (popis, var) in enumerate((
                ("Rozpětí L0 [m] (= karta 3)", self.f_nosnik.prom["L0"]),
                ("Délka nosníku L [m] (= karta 3)", self.f_nosnik.prom["L"]),
                ("Beton nosníků (= karta 1)", self.f_beton.prom["trida"]))):
            ttk.Label(fr, text=popis).grid(row=i // 2, column=2 * (i % 2), sticky="w", padx=(4, 6), pady=2)
            if var is self.f_beton.prom["trida"]:
                w = ttk.Combobox(fr, textvariable=var, values=TRIDY_BETONU, width=16)
            else:
                w = ttk.Entry(fr, textvariable=var, width=18)
            w.grid(row=i // 2, column=2 * (i % 2) + 1, sticky="we", padx=(0, 14), pady=2)
        fr.columnconfigure(1, weight=1)
        fr.columnconfigure(3, weight=1)

    def _zalozka_nosnik(self):
        super()._zalozka_nosnik()
        self._propoj_s_posudkem()

    # =====================================================================
    # Karta 5 – zatížení převzaté z obálek
    # =====================================================================
    def _zalozka_zatizeni(self):
        super()._zalozka_zatizeni()
        z = self.ram_zat.master
        for w in (self.ram_zpusob, self.ram_zat):  # volba způsobu zadání a zadávací panely
            w.pack_forget()
        # součinitele proměnných zatížení mostu v sekci dílčích součinitelů (vedle stálých a teploty)
        zm = self._naplanuj_nahled
        for atr, nazev, prip in (("f_souc_doprava", "Doprava q", ""), ("f_souc_chodci", "Chodci q_ch", "_ch")):
            sf = ttk.LabelFrame(self.ram_soucinitele, text=nazev, padding=4)
            sf.pack(side="left", fill="x", expand=True, anchor="n", padx=(8, 0), before=self.lf_souc_teplota)
            fm = Formular(sf, [(f"gamma_Q{'ch' if prip else ''}", "γ_Q", "float", None),
                               (f"psi0{prip}", "ψ0 (6.10a)", "float", None),
                               (f"psi1{prip}", "ψ1 (častá)", "float", None),
                               (f"psi2{prip}", "ψ2 (kvazistálá)", "float", None)], pri_zmene=zm)
            fm.pack(fill="x")
            setattr(self, atr, fm)
        ttk.Label(self.ram_soucinitele.master, foreground=SEDA, justify="left", text=(
            "Doprava a chodci: charakteristická γ = ψ = 1; ψ0 = ψ1 = 0,75 = ČSN 73 6222, čl. 10.1.1 a "
            "10.2.1 (Vn, Vr, Ve), pro MLC ověřte; ψ2 norma neuvádí. Stálá: 6.10a a 6.10 γ_G,sup, "
            "6.10b ξ·γ_G,sup, příznivě γ_G,inf.")).pack(anchor="w", pady=(4, 0))
        lf = ttk.LabelFrame(z, text="Vnější zatížení – převzato z obálek vnitřních sil mostu "
                                    "(karta 0)", padding=6)
        lf.pack(fill="both", expand=True, pady=(8, 0))
        self.lbl_zat = ttk.Label(lf, text="", justify="left", wraplength=1100)
        self.lbl_zat.pack(anchor="w")
        self.f_cas_blc = Formular(lf, [
            ("t_vneseni", "Kvazistálá kombinace / g − g0 působí od stáří [dny] "
                          "(prázdné = uvedení do provozu)", "optfloat", None),
            ("t_stale", "Vnesení g − g0 [dny] – jen režim zatěžovacích stavů "
                        "(prázdné = jako výše)", "optfloat", None)],
            pri_zmene=self._naplanuj_nahled)
        self.f_cas_blc.pack(fill="x", pady=4)
        self.g_zat = Graf(lf, figsize=(9, 3))
        self.g_zat.pack(fill="both", expand=True)

    # =====================================================================
    # Data
    # =====================================================================
    def _blc_data(self) -> dict:
        out = {}
        for fm in (self.f_kon, self.f_spara, self.f_uloz, self.f_vyb, self.f_chodci, self.f_voz,
                   self.f_pred, self.f_cas_blc, self.f_souc_doprava, self.f_souc_chodci):
            out.update(fm.ziskej())
        out["vozidlo"] = VOZIDLA_KLIC.get(out.get("vozidlo", "Ve"), out.get("vozidlo", "Ve"))
        out["zatizitelnost"] = bool(self.var_zat.get())
        out["zatizitelnost_druhy"] = DRUHY_ZAT_KLIC.get(self.var_zat_druhy.get(), "vse")
        out["protokol_zatizitelnosti"] = PROTOKOL_KLIC.get(self.var_zat_prot.get(), "souhrn")
        lin = [{k: v for k, v in r.items() if v is not None} for r in self.t_liniova.ziskej()]
        if lin:
            out["liniova"] = lin
        return out

    def _nastav_blc_formulare(self, b: dict):
        m = {**VYCHOZI_BLC, **b}
        m["vozidlo"] = VOZIDLA_GUI.get(m.get("vozidlo", "Ve"), m.get("vozidlo"))
        for fm in (self.f_kon, self.f_spara, self.f_uloz, self.f_vyb, self.f_chodci, self.f_voz,
                   self.f_pred, self.f_cas_blc, self.f_souc_doprava, self.f_souc_chodci):
            fm.nastav(m)
        self.t_liniova.nastav(b.get("liniova", []))
        self.var_zat.set(bool(m.get("zatizitelnost", False)))
        self.var_rezim.set(REZIMY[1] if self.var_zat.get() else REZIMY[0])
        self._zmena_rezimu()
        dz = m.get("zatizitelnost_druhy", "vse")
        self.var_zat_druhy.set(DRUHY_ZAT_GUI.get(dz if isinstance(dz, str) else "vse",
                                                 DRUHY_ZAT_GUI["vse"]))
        self.var_zat_prot.set(PROTOKOL_GUI.get(m.get("protokol_zatizitelnosti") or "souhrn",
                                               PROTOKOL_GUI["souhrn"]))

    def _nastav_data(self, d: dict):
        super()._nastav_data(d)
        self._nastav_blc_formulare(d.get("blc", {}))
        self._blc_vys, self._blc_klic = None, None
        self._zobraz_blc()

    def _zatizeni_nahradni(self) -> dict:
        """Zatížení bez spočteného mostu – jen aby šel sestavit model pro náhledy."""
        return {"zpusob": "kombinace", "obsahuje_vlastni_tihu": False,
                "kombinace": [{"druh": "char", "q": 0.0,
                               "nazev": "bez zatížení – vnitřní síly mostu nejsou spočteny"}]}

    def ziskej_data(self) -> dict:
        d = super().ziskej_data()
        d["blc"] = self._blc_data()
        vys = self._aktualni_blc(d)
        d["zatizeni"] = zatizeni_z_blc(vys, d) if vys else self._zatizeni_nahradni()
        return d

    @staticmethod
    def _klic(kw: dict) -> str:
        return klic_mkp(kw)          # bez součinitelů – ty MKP nemění

    def _vys_pro(self, kw: dict, klic: str) -> VysledekSil | None:
        """Spočtený most pro vstupy kw; jiné γ, ψ, ξ se jen dosadí (MKP se nepřepočítává)."""
        if self._blc_vys is None or klic != self._blc_klic:
            return None
        self._blc_vys = vys_se_soucinitely(self._blc_vys, kw["soucinitele"])
        return self._blc_vys

    def _aktualni_blc(self, d: dict) -> VysledekSil | None:
        """Spočtený most, odpovídá-li aktuálním vstupům (až na součinitele), jinak None."""
        try:
            kw = parametry_blc(d)
        except Exception:  # noqa: BLE001
            return None
        return self._vys_pro(kw, self._klic(kw))

    # =====================================================================
    # Výpočet
    # =====================================================================
    def _priprav(self):
        d = self.ziskej_data()
        kw = parametry_blc(d)
        return d, kw, self._klic(kw)

    def spocitej_blc(self):
        try:
            d, kw, klic = self._priprav()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Neplatná vstupní data", str(e))
            return

        def hotovo(vys):
            self._blc_vys, self._blc_klic = vys, klic
            self._zobraz_blc()
            self.stav.set(f"Vnitřní síly mostu spočteny – {vys.n_vyst} "
                          f"{'pásů' if vys.deska else 'nosníků'}.")
        self._na_pozadi(lambda: vnitrni_sily(**kw), hotovo, "Výpočet vnitřních sil mostu (BLC)…")

    def spocitej(self):
        try:
            d, kw, klic = self._priprav()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Neplatná vstupní data", str(e))
            return
        vys0 = self._vys_pro(kw, klic)
        zat = bool(d["blc"].get("zatizitelnost"))
        if zat and d["blc"].get("vozidlo", "Ve") not in ("Vn", "Vr", "Ve"):
            messagebox.showerror("Zatížitelnost", "Výpočet zatížitelnosti je pro vozidla ČSN 73 6222 – "
                                                  "zvolte na kartě 0 vozidlo Vn, Vr nebo Ve.")
            return
        self._prubeh_text = ""

        def prubeh(t):
            self._prubeh_text = t

        def prace():
            vys = vys0 or vnitrni_sily(**kw)
            if zat:
                from .zatizitelnost import zatizitelnost, protokol_druhu
                prot = d["blc"].get("protokol_zatizitelnosti") or "souhrn"
                res = zatizitelnost(d, vys, prubeh=prubeh, protokol=prot)
                model = protokol_druhu(res, prot, prubeh)
                return vys, model.blc["o"], model
            _, o, model = spocti(d, vys)
            return vys, o, model

        def hotovo(r):
            vys, o, model = r
            self._blc_vys, self._blc_klic = vys, klic
            self._zobraz_blc()
            self._zobraz_vysledky(model)
            if self._protokol_po_vypoctu:
                self._protokol_po_vypoctu = False
                self.after(10, self.protokol)
        self._na_pozadi(prace, hotovo, "Výpočet zatížitelnosti – hledání tíhy vozidla pro každý mezní "
                                       "stav (desítky výpočtů posudku na druh)…" if zat else
                        "Výpočet mostu (BLC) a posudku nosníku…")
        if zat:
            self.after(300, self._obnov_prubeh)

    def _prepni_protokol(self):
        """Po výpočtu zatížitelnosti přepne výsledky a protokol na souhrn / jeden druh
        (posudek při zatížitelnosti druhu se spočte jen poprvé, hledání se neopakuje)."""
        res = getattr(self.model, "zatizitelnost", None) if self.model is not None else None
        if res is None:
            return
        celek = res.celek or res
        volba = PROTOKOL_KLIC.get(self.var_zat_prot.get(), "souhrn")
        if volba != "souhrn" and volba not in celek.druhy:
            messagebox.showinfo("Zatížitelnost", f"Zatížitelnost {volba} nebyla spočtena – spusťte "
                                                 "výpočet znovu (F5).")
            return
        from .zatizitelnost import protokol_druhu
        self._na_pozadi(lambda: protokol_druhu(celek, volba), self._zobraz_vysledky,
                        f"Posudek při zatížitelnosti {volba}…" if volba != "souhrn" else
                        "Souhrnný protokol zatížitelnosti…")

    def _obnov_prubeh(self):
        """Průběh výpočtu zatížitelnosti do stavového řádku (text nastavuje vlákno výpočtu)."""
        if not self._zaneprazdnen:
            return
        if self._prubeh_text:
            self.stav.set(self._prubeh_text + " …")
        self.after(300, self._obnov_prubeh)

    def _zobraz_vysledky(self, model):
        """Výsledky posudku; při výpočtu zatížitelnosti místo využití tíhy Vn / Vr / Ve [t]."""
        super()._zobraz_vysledky(model)
        res = getattr(model, "zatizitelnost", None)
        nadpisy = {"MSÚ": "MSÚ – nejvyšší využití", "MSP": "MSP – nejvyšší využití",
                   "Celkem": "Výsledek"}
        if res is None:
            self.t_vys.heading("eta", text="η")
            self.t_vys.column("eta", width=56)
            for ms, (v, _) in self.karty.items():
                v.master.configure(text=nadpisy[ms])
                v.configure(font=("Segoe UI", 20, "bold"))
            return
        from .zatizitelnost import klic_posudku
        druhy = list(res.druhy)
        zat = {d: {p.klic: p for p in z.posudky} for d, z in res.druhy.items()}
        mins = {d: z.minimum() for d, z in res.druhy.items()}
        self.t_vys.heading("eta", text=" / ".join(druhy) + " [t]")
        self.t_vys.column("eta", width=230 if len(druhy) == 1 else 190)
        for iid, v in self._radky:
            pp = [zat[d].get(klic_posudku(v)) for d in druhy]
            if any(p is None for p in pp):
                continue
            stavy = {p.stav for p in pp}
            if len(druhy) == 1 or (len(stavy) == 1 and "V" not in stavy):
                txt = pp[0].text
            else:
                txt = " / ".join(p.kratky for p in pp)
            self.t_vys.set(iid, "eta", txt)
            if stavy & {"nezavisi_nok", "bez_vozidla"}:
                tag = "bad"
            elif any(p.stav == "V" and mins[d] is not None and abs(p.V - mins[d].V) < 1e-6
                     for d, p in zip(druhy, pp)):
                tag = "warn"
            else:
                tag = "ok"
            self.t_vys.item(iid, tags=(tag,))
        for ms in ("MSÚ", "MSP"):
            v, det = self.karty[ms]
            v.master.configure(text=f"{ms} – zatížitelnost")
            casti = []
            for d, z in res.druhy.items():
                mm = z.minimum(ms)
                casti.append(f"{d} > {z.V_max:.0f}" if mm is None else f"{d} {cz(mm.V, 1)}")
            v.configure(text=" · ".join(casti) + " t", foreground="#1a1a1a",
                        font=("Segoe UI", 20 if len(druhy) == 1 else 13, "bold"))
            mm = res.minimum(ms)
            det.configure(text=f"{res.druh}: " + (f"{mm.klic[1]} – {mm.klic[2]}" if mm else
                                                   "neomezuje"))
        v, det = self.karty["Celkem"]
        v.master.configure(text="Zatížitelnost (ČSN 73 6222)")
        nok = len(res.nevyhovuji_nezavisle)
        txt = " · ".join(f"{d} {cz(z.V, 1)}" if z.V is not None else f"{d} > {z.V_max:.0f}"
                         for d, z in res.druhy.items()) + " t"
        v.configure(text=txt, foreground="#0a7d0a" if not nok else "#8a5a00",
                    font=("Segoe UI", 20 if len(druhy) == 1 else 13, "bold"))
        upoz = model.protokol.upozorneni
        Vaj = res.Vaj
        det.configure(text=(f"{res.n_vypoctu} výpočtů posudku" +
                            (f"; V_aj = {cz(Vaj, 1)} t" if Vaj is not None else "") +
                            (f"; {nok} posudků nevyhovuje nezávisle na zatížení" if nok else "") +
                            (f"; upozornění {len(upoz)}" if upoz else "")))
        if hasattr(self, "_filtruj"):
            self._filtruj()
        self.lbl_souhrn.configure(text="Zatížitelnost " + txt,
                                  foreground="#0a7d0a" if not nok else "#8a5a00")
        self.stav.set(f"Zatížitelnost: {txt}; protokol a grafy pro {res.druh} = "
                      f"{cz(res.vys.V, 1)} t" + (f"; upozornění {len(upoz)} (karta Výsledky)." if upoz
                                              else "."))

    def protokol(self):
        """HTML protokol posudku včetně kapitoly a grafů zatížení mostu."""
        if self.model is None:
            self._protokol_po_vypoctu = True
            self.spocitej()
            return
        import webbrowser
        from .vypocet import uloz_protokol_most
        model, cil = self.model, self.vystup

        def hotovo(p):
            self.stav.set(f"Protokol uložen: {p}")
            webbrowser.open(Path(p).resolve().as_uri())
        self._na_pozadi(lambda: uloz_protokol_most(model, cil), hotovo, "Vytvářím HTML protokol…")

    def _sestav_seznam_grafu(self, m) -> dict:
        """Grafy výsledků posudku + zatížení na mostě a napětí v řezech (pod napětím fáze)."""
        from .grafy_most import seznam_grafu
        s = super()._sestav_seznam_grafu(m)
        navic = seznam_grafu(m)
        rezy = {k: v for k, v in navic.items() if not k.startswith("Zatížení")}
        out = {}
        for k, v in s.items():
            out[k] = v
            if k == "Vnitřní síly":
                out.update({kk: vv for kk, vv in navic.items() if kk.startswith("Zatížení")})
            if k.startswith("Napětí v betonu – "):
                nazev = "Napětí v řezech – " + k[len("Napětí v betonu – "):]
                if nazev in rezy:
                    out[nazev] = rezy.pop(nazev)
        out.update(rezy)
        return out

    # =====================================================================
    # Zobrazení
    # =====================================================================
    def _nahled(self):
        super()._nahled()
        self._zobraz_blc(jen_stav=True)

    def _zobraz_blc(self, jen_stav: bool = False):
        """Stav výpočtu mostu, tabulka nosníků, grafy na kartě 0 a 5."""
        try:
            d = self.ziskej_data()
            vys = self._aktualni_blc(d)
        except Exception as e:  # noqa: BLE001
            d, vys = None, None
            chyba = str(e)
        else:
            chyba = ""
        try:
            if d is not None and d.get("blc", {}).get("prurez_z_posudku", True) \
                    and d["blc"].get("typ_konstrukce", "nosniky") == "nosniky":
                A, Iy = vlastnosti_prurezu(d)
                self.lbl_prurez_blc.configure(
                    text=f"Z průřezu posudku: A = {cz(A, 4)} m², Iy = {cz(Iy, 5)} m⁴, "
                         f"g0 = {A * float(d.get('beton', {}).get('objemova_tiha', 25.0)):.2f} kN/m")
            else:
                self.lbl_prurez_blc.configure(text="")
        except Exception:  # noqa: BLE001
            self.lbl_prurez_blc.configure(text="")
        if vys is None:
            if self._blc_vys is not None:
                txt = "⚠ Vstupy se změnily – vnitřní síly mostu je nutné přepočítat (F5 přepočítá vše)."
            else:
                txt = "Vnitřní síly mostu nejsou spočteny (F5 spočítá most i posudek)."
            if chyba:
                txt += f"\n⚠ {chyba}"
            self.lbl_blc.configure(text=txt, foreground="#b42323")
            self.lbl_zat.configure(text=txt + "\nZatížení posudku se převezme po výpočtu mostu.",
                                   foreground="#b42323")
            if not jen_stav or self._blc_vys is None:
                self.t_blc.delete(*self.t_blc.get_children())
            self._kresli_zatizeni(None, None)
            self._kresli_nahled(d)
            return
        o = vyber_nosnik(vys, d)
        pop = vys.popisky[o]
        txt = (f"✔ {vys.popis}\nVozidlo: {vys.vozidlo}, {vys.poloha_q}; chodci "
               f"{cz(vys.q_ch)} kN/m²; posuzovaný {'pás' if vys.deska else 'nosník'}: {pop}")
        if vys.varovani:
            txt += "\n! " + "\n! ".join(vys.varovani)
        self.lbl_blc.configure(text=txt, foreground="#0a7d0a")
        self.f_pred.widgety["vystup"].configure(values=["auto"] + vys.popisky)
        zat = d["zatizeni"]
        self.lbl_zat.configure(
            text=(f"Posuzovaný {'pás' if vys.deska else 'nosník'} {pop} (y = {cz(float(vys.vyst.y[o]), 2)} m), "
                  f"vozidlo {vys.vozidlo}, δ = {cz(vys.dyn, 3, g=True)} ({vys.dyn_zdroj}); chodci "
                  f"{cz(vys.q_ch)} kN/m²" + (f" ({vys.q_ch_zdroj})" if vys.q_ch_zdroj else "") + "; "
                  f"předání: {zat.get('zpusob')}. "
                  f"Vlastní tíhu nosníku g0 počítá posudek z průřezu (model mostu: g0 = {cz(vys.g0, 2)} "
                  f"{'kN/m²' if vys.deska else 'kN/m'})" +
                  (f"; dobetonávka {cz(vys.g_dobetonavky, 2)} kN/m (½ na sousední nosníky) se předává "
                   "se stálým g − g0" if vys.g_dobetonavky else "") + "."), foreground="#0a7d0a")
        if jen_stav and self.t_blc.get_children():
            self._oznac_posuzovany(o)
            if self._nahled_zobrazen:            # graf ukazoval náhled – vrátit spočtený
                self._graf_blc()
        else:
            self.t_blc.delete(*self.t_blc.get_children())
            for i, s in enumerate(vys.souhrn()):
                g = lambda k: f"{cz(s.get(k, 0.0), 1)}"  # noqa: E731
                self.t_blc.insert("", "end", iid=str(i), values=(
                    s["vystup"] + (ZNACKA_POS if i == o else ""), f"{cz(s['y'], 2)}", g("M_g0"), g("M_g-g0"), g("M_qch"), g("M_q"),
                    g("V_g0"), g("V_g-g0"), g("V_qch"), g("V_q"), g("M_Ed"), g("V_Ed")))
            self._oznac_posuzovany(o)
            self.t_blc.selection_set(str(o))
            self._graf_blc()
        self._kresli_zatizeni(vys, zat)

    def _oznac_posuzovany(self, o: int):
        vys = self._blc_vys
        for iid in self.t_blc.get_children():
            i = int(iid)
            self.t_blc.item(iid, tags=("pos",) if i == o else ())
            if vys is not None and i < vys.n_vyst:
                self.t_blc.set(iid, "vyst", vys.popisky[i] + (ZNACKA_POS if i == o else ""))

    def _nastav_posuzovany(self, _=None):
        sel = self.t_blc.selection()
        if sel and self._blc_vys is not None:
            self.f_pred.prom["vystup"].set(self._blc_vys.popisky[int(sel[0])])

    def _graf_blc(self):
        vys = self._blc_vys
        if vys is None:
            return
        self._nahled_zobrazen = False
        from blc.plotting_sily import plot_sily, plot_pricne
        sel = self.t_blc.selection()
        o = int(sel[0]) if sel else vys.rozhodujici()
        volba = self.var_graf_blc.get()
        if volba == GRAF_REZ:
            from blc.plotting_sily import plot_pricny_rez
            fig = plot_pricny_rez(vys, o, show=False)
        elif volba.startswith("Průběhy"):
            fig = plot_sily(vys, o, show=False)
        elif volba.startswith("Vnitřní síly"):
            from blc.plotting_sily import plot_stavy_pudorys
            fig = plot_stavy_pudorys(vys, o, show=False)
        else:
            fig = plot_pricne(vys, show=False)
        plt.close(fig)
        self.g_blc.zobraz(fig)

    def _kresli_nahled(self, d):
        """Bez spočteného mostu: náhled příčného řezu se zatížením dopravou ze zadání (bez MKP,
        překreslí se jen při změně vstupů)."""
        from blc.plotting_sily import plot_pricny_rez
        try:
            kw = parametry_blc(d) if d is not None else None
            klic = None if kw is None else klic_mkp(kw)
        except Exception:  # noqa: BLE001
            kw = klic = None
        if klic is not None and klic == self._nahled_klic and self._nahled_zobrazen:
            return
        self._nahled_klic = klic
        self._nahled_zobrazen = True
        if kw is None:
            self.g_blc.fig.clear()
            self.g_blc.canvas.draw_idle()
            return
        try:
            n = nahled_mostu(**kw)
            o = n.popisky.index(str(d["blc"].get("vystup"))) if d["blc"].get("vystup") in n.popisky else None
            fig = plot_pricny_rez(n, o, show=False)
            from textwrap import fill
            from blc.plotting_sily import nadpis_pricneho_rezu
            fig.axes[0].set_title(fill("Náhled ze zadání (most není spočten) – " + nadpis_pricneho_rezu(n),
                                       100), fontsize=9)
            fig.tight_layout()
        except Exception:  # noqa: BLE001 – neúplné zadání: náhled se nekreslí
            return
        plt.close(fig)
        self.g_blc.zobraz(fig)

    def _kresli_zatizeni(self, vys, zat):
        fig = self.g_zat.fig
        fig.clear()
        if not zat:
            self.g_zat.canvas.draw_idle()
            return
        axm, axv = fig.add_subplot(121), fig.add_subplot(122)
        rady = []
        if zat.get("zpusob") == "kombinace":
            for k in zat.get("kombinace", []):
                rady.append((pbgui.DRUHY_KOMBINACI.get(k["druh"], k["druh"]), k["x"], k["M_max"],
                             k.get("M_min"), k.get("V_max"), k.get("V_min")))
        else:
            for k in zat.get("stale", []) + zat.get("promenne", []):
                t = k["tabulka"]
                rady.append((k.get("nazev", ""), t["x"], t["M"], None, t.get("V"), None))
        for j, (naz, x, Mx, Mn, Vx, Vn) in enumerate(rady):
            c = pbgui.grafy.C[j % 8]
            axm.plot(x, Mx, color=c, lw=1.5, label=naz)
            if Mn is not None and not np.allclose(Mn, Mx):
                axm.plot(x, Mn, color=c, lw=0.9, ls="--")
            if Vx is not None:
                axv.plot(x, Vx, color=c, lw=1.5)
            if Vn is not None and not np.allclose(Vn, Vx):
                axv.plot(x, Vn, color=c, lw=0.9, ls="--")
        axm.invert_yaxis()
        axm.set(title="M převzaté do posudku [kNm] (bez vlastní tíhy nosníku)", xlabel="x [m]")
        axv.set(title="V převzaté do posudku [kN] (bez vlastní tíhy nosníku)", xlabel="x [m]")
        for a in (axm, axv):
            a.grid(alpha=0.3)
        axm.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        self.g_zat.canvas.draw_idle()


def main(argv=None) -> int:
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    app = AplikaceMost(argv[0] if argv else None)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
