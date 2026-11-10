"""
gui.py
======
Spojený program BLC × Posudek PB – grafické rozhraní Posudku PB s novou první
kartou „Most a zatížení (BLC)“:

  0  Most a zatížení (BLC)   konstrukce mostu, vybavení (g − g0), vybrané vozidlo (q),
                              výpočet vnitřních sil, výběr posuzovaného nosníku
  1 – 4, 6, 7                 karty Posudku PB beze změny (materiály, průřez, nosník
                              a předpětí, výztuž, nastavení, výsledky)
  5  Zatížení a čas           prostředí a časová osa; vnější zatížení se NEZADÁVÁ –
                              přebírá se z obálek vnitřních sil posuzovaného nosníku

Rozpětí L0, délka L a třída betonu jsou společné (pole na kartě 0 jsou propojená
s kartami 1 a 3), A a Iy nosníku se berou z průřezu posudku, γ_G, ξ a kombinace MSÚ
z nastavení posouzení.  F5 spočítá most (je-li třeba) i posudek.
"""

from __future__ import annotations
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import matplotlib.pyplot as plt
import numpy as np

from blc.vehicles import seznam_mlc
from blc.vnitrni_sily import vnitrni_sily, VysledekSil
from pb_posudek import gui as pbgui
from pb_posudek.gui import Aplikace, Formular, Graf, Tabulka, TRIDY_BETONU

from .vypocet import (VYCHOZI_BLC, parametry_blc, spocti, vyber_nosnik, vlastnosti_prurezu,
                      zatizeni_z_blc)

KOREN = Path(__file__).resolve().parents[1]
PRIKLAD_MOST = KOREN / "priklady" / "most_KA67_12.toml"
NAZEV = "BLC × Posudek PB"
VOZIDLA_GUI = {"Ve": "Ve", "MLC_k": "MLC kolové", "MLC_p": "MLC pásové"}
VOZIDLA_KLIC = {v: k for k, v in VOZIDLA_GUI.items()}
SEDA = "#52514e"


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
        cv = tk.Canvas(lev, highlightthickness=0, width=560)
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
        zm = self._naplanuj_nahled

        lf = ttk.LabelFrame(f, text="Nosná konstrukce", padding=6)
        lf.pack(fill="x", pady=4)
        self._ram_propojene = ttk.Frame(lf)
        self._ram_propojene.pack(fill="x")
        self.f_kon = Formular(lf, [
            ("typ_konstrukce", "Typ konstrukce", "choice", ["nosniky", "deska"]),
            ("N", "Počet nosníků N", "int", None),
            ("b", "Šířka nosníku b [m]", "float", None),
            ("d", "Účinná výška d [m]", "float", None),
            ("prurez_z_posudku", "A, Iy z průřezu (karta 2)", "bool", True),
            ("nu", "Poissonovo číslo ν", "float", None),
            ("A_nosniku", "A nosníku [m²] (bez převzetí)", "optfloat", None),
            ("Iy", "Iy nosníku [m⁴] (bez převzetí)", "optfloat", None),
            ("h", "Tloušťka desky h [m] (deska)", "optfloat", None)], sloupcu=2, pri_zmene=zm)
        self.f_kon.pack(fill="x")
        self.lbl_prurez_blc = ttk.Label(lf, text="", foreground=SEDA)
        self.lbl_prurez_blc.pack(anchor="w", pady=(2, 0))

        lf = ttk.LabelFrame(f, text="Podélná spára mezi nosníky", padding=6)
        lf.pack(fill="x", pady=4)
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
            ("alfa", "Úhel šikmosti α [°] (90 = kolmý)", "float", None),
            ("sikmost", "Šikmost", "choice", ["prava", "leva"]),
            ("k_v", "Tuhost podpory k_v [MN/m/m]", "optfloat", None),
            ("uloz", "Uložení", "choice", ["tvrde", "mekke", "vetknuti"]),
            ("k_rot", "Vetknutí k_φ [MNm/rad/m]", "optfloat", None),
            ("spoj", "Spojení nosníků bez spáry", "choice", ["kloub", "deska"])],
            sloupcu=2, pri_zmene=zm)
        self.f_uloz.pack(fill="x")
        ttk.Label(lf, foreground=SEDA, text="k_v prázdné / 0 = tuhá podpora; k_φ prázdné = dokonalé "
                                            "vetknutí (jen uložení „vetknuti“)").pack(anchor="w")

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
        ttk.Label(lf, foreground=SEDA, text=(
            "Na obou chodnících, v nepříznivých částech plochy vlivu (obálka); prázdné / 0 = bez "
            "zatížení chodců.")).pack(anchor="w")

        lf = ttk.LabelFrame(f, text="Vozidlo, které přejíždí most (q)", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_voz = Formular(lf, [
            ("vozidlo", "Vozidlo", "choice", list(VOZIDLA_GUI.values())),
            ("Ve", "Ve – tíha vozidla [t]", "optfloat", None),
            ("MLC", "Třída MLC", "choice", seznam_mlc()),
            ("dist", "Kolona – vzdálenost vozidel [m]", "optfloat", None),
            ("dyn", "Dynamický součinitel δ (prázdné = ČSN 73 6222)", "optfloat", None),
            ("y_vozidla", "Osa vozidla y [m]", "optfloat", None),
            ("roznos", "Roznos kola do střednice desky", "bool", True),
            ("t_voz", "Tloušťka vozovky (roznos) [m]", "float", None),
            ("krok", "Krok poloh vozidla [m]", "float", None),
            ("ex", "Velikost prvku MKP [m]", "float", None)], sloupcu=2, pri_zmene=zm)
        self.f_voz.pack(fill="x")
        ttk.Label(lf, foreground=SEDA, text=(
            "Jedno vozidlo projíždí po mostě v obou směrech; kolona jen pro MLC (prázdné = jedno "
            "vozidlo). Osa vozidla prázdná = osa vozovky mezi chodníky. Dynamický součinitel "
            "prázdný = podle ČSN 73 6222, kap. 8: Ve δ = 1,05 (čl. 8.4); pro MLC norma δ neuvádí "
            "(uvažuje se 1,0).")).pack(anchor="w")

        lf = ttk.LabelFrame(f, text="Předání do posudku", padding=6)
        lf.pack(fill="x", pady=4)
        self.f_pred = Formular(lf, [
            ("vystup", "Posuzovaný nosník", "choice", ["auto"]),
            ("kriterium", "Nejzatíženější podle", "choice", ["M", "M-", "V"]),
            ("rezim", "Předání zatížení", "choice", ["kombinace", "zatezovaci_stavy"]),
            ("gamma_Q", "γ_Q – doprava", "float", None),
            ("psi0", "ψ0 – doprava", "float", None), ("psi1", "ψ1 – doprava", "float", None),
            ("psi2", "ψ2 – doprava", "float", None),
            ("gamma_Qch", "γ_Q – chodci", "float", None),
            ("psi0_ch", "ψ0 – chodci", "float", None), ("psi1_ch", "ψ1 – chodci", "float", None),
            ("psi2_ch", "ψ2 – chodci", "float", None)], sloupcu=2, pri_zmene=zm)
        self.f_pred.pack(fill="x")
        ttk.Label(lf, foreground=SEDA, justify="left", text=(
            "auto = nejzatíženější nosník podle MSÚ (6.10, včetně g0). γ_G, γ_G,inf, ξ a kombinace MSÚ "
            "se berou z karty 6;\nψ pro zvolené vozidlo ověřte (výchozí = TS, ČSN EN 1990 tab. A2.1)."
        )).pack(anchor="w")

        # pravý sloupec – výpočet a výsledky
        prav = ttk.Frame(pan, padding=(8, 8, 4, 4))
        pan.add(prav, weight=3)
        bt = ttk.Frame(prav)
        bt.pack(fill="x")
        self.btn_blc = ttk.Button(bt, text="▶  Vnitřní síly mostu", command=self.spocitej_blc)
        self.btn_blc.pack(side="left")
        ttk.Button(bt, text="▶▶  Most + posudek (F5)", style="Akce.TButton",
                   command=self.spocitej).pack(side="left", padx=6)
        self.var_zat = tk.BooleanVar(value=False)
        ttk.Checkbutton(bt, text="Výpočet zatížitelnosti – hledat Ve pro η = 100 % (místo posouzení)",
                        variable=self.var_zat, command=self._naplanuj_nahled).pack(side="left", padx=8)
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
            self.t_blc.column(c, width=66 if c != "vyst" else 70, anchor="e")
        self.t_blc.tag_configure("pos", background="#fff3cd")
        self.t_blc.pack(fill="x")
        self.t_blc.bind("<<TreeviewSelect>>", lambda e: self._graf_blc())
        self.t_blc.bind("<Double-1>", self._nastav_posuzovany)
        ttk.Label(prav, foreground=SEDA, text=(
            "Jednotky kNm, kN (deska: na pás 1 m). Žlutě posuzovaný nosník; dvojklik = posuzovat "
            "tento nosník. M_Ed, V_Ed = MSÚ 6.10 vč. g0.")).pack(anchor="w")
        r = ttk.Frame(prav)
        r.pack(fill="x", pady=(6, 2))
        ttk.Label(r, text="Graf:").pack(side="left")
        self.var_graf_blc = tk.StringVar(value="Průběhy sil – vybraný nosník")
        cb = ttk.Combobox(r, textvariable=self.var_graf_blc, state="readonly", width=34,
                          values=["Průběhy sil – vybraný nosník", "Vnitřní síly na nosnících (půdorys)",
                                  "Příčné rozdělení a vybavení"])
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self._graf_blc())
        self.g_blc = Graf(prav, figsize=(8, 5))
        self.g_blc.pack(fill="both", expand=True)

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
        for w in z.winfo_children()[1:]:          # volba způsobu zadání a zadávací panely
            w.pack_forget()
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
                   self.f_pred, self.f_cas_blc):
            out.update(fm.ziskej())
        out["vozidlo"] = VOZIDLA_KLIC.get(out.get("vozidlo", "Ve"), out.get("vozidlo", "Ve"))
        out["zatizitelnost"] = bool(self.var_zat.get())
        lin = [{k: v for k, v in r.items() if v is not None} for r in self.t_liniova.ziskej()]
        if lin:
            out["liniova"] = lin
        return out

    def _nastav_blc_formulare(self, b: dict):
        m = {**VYCHOZI_BLC, **b}
        m["vozidlo"] = VOZIDLA_GUI.get(m.get("vozidlo", "Ve"), m.get("vozidlo"))
        for fm in (self.f_kon, self.f_spara, self.f_uloz, self.f_vyb, self.f_chodci, self.f_voz,
                   self.f_pred, self.f_cas_blc):
            fm.nastav(m)
        self.t_liniova.nastav(b.get("liniova", []))
        self.var_zat.set(bool(m.get("zatizitelnost", False)))

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
        return repr(sorted(kw.items()))

    def _aktualni_blc(self, d: dict) -> VysledekSil | None:
        """Spočtený most, odpovídá-li aktuálním vstupům, jinak None."""
        if self._blc_vys is None:
            return None
        try:
            return self._blc_vys if self._klic(parametry_blc(d)) == self._blc_klic else None
        except Exception:  # noqa: BLE001
            return None

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
        vys0 = self._blc_vys if klic == self._blc_klic else None
        zat = bool(d["blc"].get("zatizitelnost"))
        if zat and d["blc"].get("vozidlo", "Ve") != "Ve":
            messagebox.showerror("Zatížitelnost", "Výpočet zatížitelnosti je pro vozidlo Ve – "
                                                  "zvolte na kartě 0 vozidlo Ve.")
            return

        def prace():
            vys = vys0 or vnitrni_sily(**kw)
            if zat:
                from .zatizitelnost import zatizitelnost
                res = zatizitelnost(d, vys)
                return vys, res.o, res.model
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
        self._na_pozadi(prace, hotovo, "Výpočet zatížitelnosti – hledání Ve pro každý mezní stav "
                                       "(desítky výpočtů posudku)…" if zat else
                        "Výpočet mostu (BLC) a posudku nosníku…")

    def _zobraz_vysledky(self, model):
        """Výsledky posudku; při výpočtu zatížitelnosti místo využití Ve [t]."""
        super()._zobraz_vysledky(model)
        res = getattr(model, "zatizitelnost", None)
        nadpisy = {"MSÚ": "MSÚ – nejvyšší využití", "MSP": "MSP – nejvyšší využití",
                   "Celkem": "Výsledek"}
        if res is None:
            self.t_vys.heading("eta", text="η")
            self.t_vys.column("eta", width=56)
            for ms, (v, _) in self.karty.items():
                v.master.configure(text=nadpisy[ms])
            return
        from .zatizitelnost import klic_posudku
        zat = {p.klic: p for p in res.posudky}
        self.t_vys.heading("eta", text="Ve [t]")
        self.t_vys.column("eta", width=205)
        m_all = res.minimum()
        for iid, v in self._radky:
            p = zat.get(klic_posudku(v))
            if p is None:
                continue
            self.t_vys.set(iid, "eta", p.text)
            if p.stav in ("nezavisi_nok", "bez_vozidla"):
                tag = "bad"
            elif p.stav == "Ve" and m_all is not None and abs(p.Ve - m_all.Ve) < 1e-6:
                tag = "warn"
            else:
                tag = "ok"
            self.t_vys.item(iid, tags=(tag,))
        for ms in ("MSÚ", "MSP"):
            v, det = self.karty[ms]
            v.master.configure(text=f"{ms} – zatížitelnost")
            mm = res.minimum(ms)
            if mm is None:
                v.configure(text="neomezuje", foreground="#0a7d0a")
                det.configure(text=f"do Ve = {res.Ve_max:.0f} t")
            else:
                v.configure(text=f"Ve = {mm.Ve:.1f} t", foreground="#1a1a1a")
                det.configure(text=f"{mm.klic[1]} – {mm.klic[2]}")
        v, det = self.karty["Celkem"]
        v.master.configure(text="Zatížitelnost")
        nok = len(res.nevyhovuji_nezavisle)
        if m_all is None:
            v.configure(text=f"Ve > {res.Ve_max:.0f} t", foreground="#0a7d0a")
        else:
            v.configure(text=f"Ve = {m_all.Ve:.1f} t", foreground="#0a7d0a" if not nok else "#8a5a00")
        upoz = model.protokol.upozorneni
        det.configure(text=(f"{res.n_vypoctu} výpočtů posudku" +
                            (f"; {nok} posudků nevyhovuje nezávisle na Ve" if nok else "") +
                            (f"; upozornění {len(upoz)}" if upoz else "")))
        self.lbl_souhrn.configure(
            text=("Zatížitelnost " + (f"Ve = {m_all.Ve:.1f} t" if m_all else f"Ve > {res.Ve_max:.0f} t")),
            foreground="#0a7d0a" if not nok else "#8a5a00")
        self.stav.set(f"Zatížitelnost: " + (f"Ve = {m_all.Ve:.1f} t ({m_all.klic[0]} {m_all.klic[1]} – "
                                             f"{m_all.klic[2]})" if m_all else "neomezena")
                      + f"; protokol a grafy pro toto Ve"
                      + (f"; upozornění {len(upoz)} (karta Výsledky)." if upoz else "."))

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
                    text=f"Z průřezu posudku: A = {A:.4f} m², Iy = {Iy:.5f} m⁴, "
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
            return
        o = vyber_nosnik(vys, d)
        pop = vys.popisky[o]
        txt = (f"✔ {vys.popis}\nVozidlo: {vys.vozidlo}, osa y = {vys.y_Ve:.2f} m; "
               f"posuzovaný {'pás' if vys.deska else 'nosník'}: {pop}")
        if vys.varovani:
            txt += "\n! " + "\n! ".join(vys.varovani)
        self.lbl_blc.configure(text=txt, foreground="#0a7d0a")
        self.f_pred.widgety["vystup"].configure(values=["auto"] + vys.popisky)
        zat = d["zatizeni"]
        self.lbl_zat.configure(
            text=(f"Posuzovaný {'pás' if vys.deska else 'nosník'} {pop} (y = {float(vys.vyst.y[o]):.2f} m), "
                  f"vozidlo {vys.vozidlo}, δ = {vys.dyn:g} ({vys.dyn_zdroj}); "
                  f"předání: {zat.get('zpusob')}. "
                  f"Vlastní tíhu nosníku g0 počítá posudek z průřezu (model mostu: g0 = {vys.g0:.2f} "
                  f"{'kN/m²' if vys.deska else 'kN/m'})."), foreground="#0a7d0a")
        if jen_stav and self.t_blc.get_children():
            self._oznac_posuzovany(o)
        else:
            self.t_blc.delete(*self.t_blc.get_children())
            for i, s in enumerate(vys.souhrn()):
                g = lambda k: f"{s.get(k, 0.0):.1f}"  # noqa: E731
                self.t_blc.insert("", "end", iid=str(i), values=(
                    s["vystup"], f"{s['y']:.2f}", g("M_g0"), g("M_g-g0"), g("M_qch"), g("M_q"),
                    g("V_g0"), g("V_g-g0"), g("V_qch"), g("V_q"), g("M_Ed"), g("V_Ed")))
            self._oznac_posuzovany(o)
            self.t_blc.selection_set(str(o))
            self._graf_blc()
        self._kresli_zatizeni(vys, zat)

    def _oznac_posuzovany(self, o: int):
        for iid in self.t_blc.get_children():
            self.t_blc.item(iid, tags=("pos",) if int(iid) == o else ())

    def _nastav_posuzovany(self, _=None):
        sel = self.t_blc.selection()
        if sel and self._blc_vys is not None:
            self.f_pred.prom["vystup"].set(self._blc_vys.popisky[int(sel[0])])

    def _graf_blc(self):
        vys = self._blc_vys
        if vys is None:
            return
        from blc.plotting_sily import plot_sily, plot_pricne
        sel = self.t_blc.selection()
        o = int(sel[0]) if sel else vys.rozhodujici()
        volba = self.var_graf_blc.get()
        if volba.startswith("Průběhy"):
            fig = plot_sily(vys, o, show=False)
        elif volba.startswith("Vnitřní síly"):
            from blc.plotting_sily import plot_stavy_pudorys
            fig = plot_stavy_pudorys(vys, o, show=False)
        else:
            fig = plot_pricne(vys, show=False)
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
        axm.set(title="M převzaté do posudku [kNm] (bez g0)", xlabel="x [m]")
        axv.set(title="V převzaté do posudku [kN] (bez g0)", xlabel="x [m]")
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
