"""Výpočetní model nosníku z předpjatého betonu a jeho posouzení.

Statické schéma: prostý nosník (volitelně s převislými konci za ložisky).
Předpětí: dodatečné (soudržné kabely) nebo předem předpjaté (lana).
Spřažená deska se v této verzi neuvažuje.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from . import reologie
from .kabel import Kabel
from .materialy import Beton, BetonarskaVyztuz, PredpinaciVyztuz
from .msu import (VrstvaPredpeti, VrstvaVyztuze, ohybova_unosnost, smykova_unosnost)
from .protokol import Kapitola, Protokol, VysledekPosudku, fmt
from .prurez import Prurez
from .trhliny import Vrstva, sirka_trhliny, xi_predpinaci
from .zatizeni import (DRUHY_KOMBINACI, NAZVY_KOMBINACI, KombinaceVstup, Obalka, ZatezovaciStav,
                       kombinace)
from .ztraty import ztrata_dlouhodoba_546, ztrata_pokluzem_obecne


# ČSN 73 6222, tab. 12.3: kategorie mostu podle informativní zbytkové životnosti a druhu konstrukce
# (sloupce: předem předpjaté, dodatečně předpjaté soudržné, dodatečně nesoudržné, železobetonové)
ZBYTKOVA_ZIVOTNOST = {"50": ("S4", "BCDE"), "15-30": ("S3", "CDEF"), "10": ("S1", "DEFG")}
# ČSN 73 6222, tab. 12.4: kategorie → (kombinace pro dekompresi, kombinace pro šířku trhlin, w_max [mm])
KRITERIA_KATEGORIE = {
    "B": ("casta", "char", 0.2),
    "C": ("kvazistala", "casta", 0.2),
    "D": ("zadna", "casta", 0.2),
    "E": ("zadna", "kvazistala", 0.3),
    "F": ("zadna", "kvazistala", 0.4),
    "G": ("zadna", "kvazistala", 0.5),
}


def kategorie_mostu(zbytkova_zivotnost: str, typ_predpeti: str) -> str:
    """Kategorie mostu B–G podle ČSN 73 6222, tab. 12.3 ("" = zbytková životnost nezadána)."""
    zz = str(zbytkova_zivotnost or "").strip().replace(" až ", "-").replace("–", "-").replace(" ", "")
    if not zz:
        return ""
    if zz not in ZBYTKOVA_ZIVOTNOST:
        raise ValueError(f"Informativní zbytková životnost „{zbytkova_zivotnost}“ – možnosti: 50, 15-30, 10 let.")
    sloupec = {"predem": 0, "dodatecne": 1, "nesoudrzne": 2, "zb": 3}
    typ = next((v for k, v in sloupec.items() if str(typ_predpeti).startswith(k)), 1)
    return ZBYTKOVA_ZIVOTNOST[zz][1][typ]


@dataclass
class Nastaveni:
    """Parametry posouzení (výchozí hodnoty podle doporučení ČSN EN 1992-1-1)."""

    # napínání (5.10.2.1, 5.10.3)
    k1_nap: float = 0.8
    k2_nap: float = 0.9
    k7: float = 0.75
    k8: float = 0.85
    # napětí v betonu (5.10.2.2, 7.2)
    k_predpeti: float = 0.6        # tlak při vnesení předpětí · f_ck(t)
    k1: float = 0.6                # tlak – charakteristická kombinace
    k2: float = 0.45               # tlak – kvazistálá kombinace
    k5: float = 0.75               # napětí v předpínací výztuži – charakteristická
    tah_predpeti: str = "fctm"     # mez tahu při předpětí a výstavbě: fctm | fctk005 | 0
    tah_provoz: str = "fctm"       # mez tahu – charakteristická kombinace
    dekomprese: str = "casta"      # casta | kvazistala | zadna
    dekomprese_rezim: str = "krajni"  # krajni | kabel
    a_dek: float = 25.0            # mm – hloubka dekomprese kolem kabelu (EN 1992-2 7.3.1(105))
    # ČSN 73 6222, tab. 12.3 a 12.4: informativní zbytková životnost → kategorie mostu → kombinace
    # pro dekompresi a šířku trhlin a w_max ("" = bez kategorie, platí dekomprese/trhliny/w_max níže)
    zbytkova_zivotnost: str = ""   # "" | "50" | "15-30" | "10"
    trhliny: str = "zadna"         # kombinace pro šířku trhlin: char | casta | kvazistala | zadna
    w_max: float = 0.2             # mm – omezení šířky trhlin na povrchu
    xi_p: float | None = None      # poměr soudržnosti předp. výztuže ξ (tab. 6.2; None = podle typu)
    r_sup: float | None = None     # 5.10.9 (None = podle typu předpětí)
    r_inf: float | None = None
    # MSÚ
    gamma_P: float = 1.0
    gamma_G: float = 1.35
    gamma_G_inf: float = 1.0
    xi: float = 0.85
    kombinace_msu: str = "6.10ab"  # 6.10ab | 6.10
    cot_theta_min: float = 1.0
    cot_theta_max: float = 2.5
    kanalky: str = "ocel"          # ocel | plast (6.2.3(6))
    # použitelnost
    pruhyb_limit: float = 250.0    # L/...
    relaxace_t_max_h: float = 500000.0
    hlavni_napeti: bool = True


@dataclass
class SmykovaVyztuz:
    Asw: float = 0.0       # mm2 (všechny střižnosti)
    s: float = 200.0       # mm
    alpha: float = 90.0    # sklon ve stupních
    od: float | None = None
    do: float | None = None

    @property
    def Asw_s(self) -> float:
        return self.Asw / self.s if self.s > 0 else 0.0


@dataclass
class Faze:
    nazev: str
    t: float
    provoz: bool
    stale: list[ZatezovaciStav]
    sigma: list[np.ndarray] = field(default_factory=list)   # σ_pm,t,i(x)
    popis: str = ""
    ztraty: dict = field(default_factory=dict)
    # oslabení výztuže korozí – součinitele zbývající plochy (1 = bez oslabení)
    k_Ap: float = 1.0          # předpínací výztuž (síla P i A_p v MSÚ)
    k_As: float = 1.0          # podélná betonářská výztuž
    k_Asw: float = 1.0         # smyková výztuž
    # mezní přetvoření předpínací výztuže při tažnosti oslabené korozí (None = neoslabená, ε_ud)
    eps_ud_p: float | None = None

    @property
    def oslabena(self) -> bool:
        return min(self.k_Ap, self.k_As, self.k_Asw) < 1.0 or self.eps_ud_p is not None

    @property
    def nazev_t(self) -> str:
        return f"{self.nazev} (t = {fmt(self.t, 0)} dní)"


class NosnikPB:
    """Nosník z předpjatého betonu – vstupy, výpočet a posouzení."""

    def __init__(self, *, beton: Beton, predpinaci: PredpinaciVyztuz, betonarska: BetonarskaVyztuz,
                 prurez: Prurez, L: float, L0: float | None, kabely: list[Kabel],
                 typ_predpeti: str = "dodatecne", vyztuz: list[VrstvaVyztuze] | None = None,
                 smykova: list[SmykovaVyztuz] | None = None, RH: float = 70.0, t_s: float = 3.0,
                 t0: float = 7.0, t_provoz: float = 120.0, t_konec: float = 36500.0,
                 stale: list[ZatezovaciStav] | None = None,
                 promenne: list[ZatezovaciStav] | None = None,
                 nastaveni: Nastaveni | None = None, projekt: dict | None = None,
                 n_rezu: int = 41, charakteristiky: str = "brutto",
                 pocet_napinani: int | None = None, relaxace_pred_uvolnenim_h: float | None = None,
                 predem_eta_p1: float = 3.2, predem_alpha1: float = 1.25,
                 predem_alpha2: float = 0.19, predem_eta_p2: float = 1.2, kombinace_vstup: list[KombinaceVstup] | None = None,
                 kombinace_vcetne_g0: bool = False, t_vneseni: float | None = None,
                 t_akt: float | None = None, oslabeni_Ap: float = 0.0, oslabeni_As: float = 0.0,
                 oslabeni_Asw: float = 0.0):
        self.beton = beton
        self.predp = predpinaci
        self.betonarska = betonarska
        self.prurez = prurez
        self.L = float(L)
        self.L0 = float(L0) if L0 else float(L)
        self.kabely = kabely
        self.typ = typ_predpeti
        self.vyztuz = vyztuz or []
        self.smykova = smykova or []
        self.RH = RH
        self.t_s = t_s
        self.t0 = t0
        self.t_provoz = t_provoz
        self.t_konec = t_konec
        self.stale_vstup = stale or []
        self.promenne = promenne or []
        self.kombinace_vstup = kombinace_vstup or []
        self.rezim_kombinace = bool(self.kombinace_vstup)
        self.kombinace_vcetne_g0 = kombinace_vcetne_g0
        self.t_vneseni = t_vneseni if t_vneseni is not None else t_provoz
        # aktuální stáří konstrukce (posudek existující konstrukce) a oslabení výztuže korozí [%]
        self.t_akt = float(t_akt) if t_akt not in (None, "") else None
        if self.t_akt is not None and not (t_provoz < self.t_akt < t_konec):
            raise ValueError(f"Aktuální stáří {self.t_akt:g} dní musí ležet mezi uvedením do provozu "
                             f"({t_provoz:g}) a koncem životnosti ({t_konec:g}).")
        self.oslabeni = {"Ap": float(oslabeni_Ap or 0.0), "As": float(oslabeni_As or 0.0),
                         "Asw": float(oslabeni_Asw or 0.0)}
        for k_, v_ in self.oslabeni.items():
            if not 0.0 <= v_ < 100.0:
                raise ValueError(f"Oslabení výztuže {k_} korozí musí být 0 až < 100 %.")
        self.n = nastaveni or Nastaveni()
        self.projekt = projekt or {}
        self.n_rezu = n_rezu
        self.charakteristiky = charakteristiky
        self.pocet_napinani = pocet_napinani
        self.relax_pred_h = relaxace_pred_uvolnenim_h
        self.eta_p1, self.a1_pt, self.a2_pt = predem_eta_p1, predem_alpha1, predem_alpha2
        self.eta_p2 = predem_eta_p2  # 8.10.2.3(2): 1,4 dráty s vtisky, 1,2 sedmidrátová lana
        if self.n.r_sup is None:
            self.n.r_sup = 1.05 if self.predem else 1.10
        if self.n.r_inf is None:
            self.n.r_inf = 0.95 if self.predem else 0.90
        self.kategorie = kategorie_mostu(self.n.zbytkova_zivotnost, self.typ)
        if self.kategorie:
            self.n.dekomprese, self.n.trhliny, self.n.w_max = KRITERIA_KATEGORIE[self.kategorie]
        self.protokol = Protokol(self.projekt.get("nazev", "Posudek nosníku z předpjatého betonu"))
        self.v: dict = {}  # uložené výsledky pro grafy

    # ------------------------------------------------------------------
    @property
    def predem(self) -> bool:
        return self.typ.startswith("predem")

    @property
    def Ap(self) -> float:
        return sum(k.Ap for k in self.kabely)

    # ==================================================================
    def spocitej(self) -> Protokol:
        with np.errstate(divide="ignore", invalid="ignore"):
            return self._spocitej()

    def _spocitej(self) -> Protokol:
        self._site()
        self._vstupy()
        self._prurezy()
        self._kabely()
        self._zatizeni()
        self._ztraty_okamzite()
        self._faze_a_dlouhodobe_ztraty()
        self._prehled_ztrat()
        self._vnitrni_sily()
        self._msp()
        if self.n.hlavni_napeti:
            self._hlavni_napeti()
        self._pruhyb()
        self._msu_ohyb()
        self._msu_smyk()
        if self.predem:
            self._kotveni_lan()
        self._krehky_lom()
        return self.protokol

    # ------------------------------------------------------------------
    def _site(self):
        self.xa = (self.L - self.L0) / 2
        self.xb = self.xa + self.L0
        x = np.linspace(0, self.L, self.n_rezu)
        x = np.union1d(x, [self.xa, self.xb, self.xa + self.L0 / 2])
        # Řezy těsně vně podpor: posouvající síla má v podpoře skok o reakci. Řez přesně v podpoře
        # nese hodnotu na straně pole, řez o δ vedle hodnotu na převislém konci (≈ 0), takže průběh
        # V obsahuje svislý skok místo lineárního náběhu od konce nosníku k podpoře.
        d = 1e-4
        if self.xa > 2 * d:
            x = np.union1d(x, [self.xa - d, self.xb + d])
        self.x = x
        self.ia = int(np.argmin(abs(x - self.xa)))
        self.ib = int(np.argmin(abs(x - self.xb)))
        self.im = int(np.argmin(abs(x - (self.xa + self.L0 / 2))))
        self.v_poli = (x >= self.xa - 1e-9) & (x <= self.xb + 1e-9)
        body = [0.0, self.xa, self.xa + self.L0 / 4, self.xa + self.L0 / 2,
                self.xa + 3 * self.L0 / 4, self.xb, self.L]
        idx = sorted({int(np.argmin(abs(x - b))) for b in body})
        self.i_tab = idx

    def _x_tab_hlavicka(self) -> list[str]:
        return [f"x = {fmt(self.x[i], 3)} m" for i in self.i_tab]

    # ------------------------------------------------------------------
    def _vstupy(self):
        b, p, s = self.beton, self.predp, self.betonarska
        K = self.protokol.kapitola("Vstupní údaje")
        K.text(self.projekt.get("popis", ""))
        K.text(f"Statické schéma: prostý nosník délky L = {fmt(self.L)} m, rozpětí (vzdálenost "
               f"ložisek) L0 = {fmt(self.L0)} m. Předpětí: "
               f"{'předem předpjatá lana' if self.predem else 'dodatečně předpjaté soudržné kabely'}. "
               "Spřažená deska mostovky se v této verzi neuvažuje.")
        K2 = self.protokol.kapitola("Materiály", 2)
        K2.text(f"Beton {b.trida}, cement třídy {b.cement}; charakteristiky podle tab. 3.1 ČSN EN 1992-1-1.")
        K2.krok("Charakteristická válcová pevnost", "f_{ck}", "", b.fck, "MPa", "tab. 3.1")
        K2.krok("Průměrná pevnost v tlaku", "f_{cm} = f_{ck} + 8", f"{fmt(b.fck)} + 8", b.fcm, "MPa", "tab. 3.1")
        K2.krok("Průměrná pevnost v tahu",
                "f_{ctm} = 0,30·f_{ck}^{2/3}" if b.fck <= 50 else "f_{ctm} = 2,12·ln(1 + f_{cm}/10)",
                "", b.fctm, "MPa", "tab. 3.1")
        K2.krok("Charakteristická pevnost v tahu (5% kvantil)", "f_{ctk,0,05} = 0,7·f_{ctm}", "",
                b.fctk005, "MPa", "tab. 3.1")
        K2.krok("Sečnový modul pružnosti", "E_{cm} = 22·(f_{cm}/10)^{0,3}" if not b.Ecm_zadany else "E_{cm} (zadáno)",
                f"22·({fmt(b.fcm)}/10)^{{0,3}}·10^{{3}}" if not b.Ecm_zadany else "", b.Ecm, "MPa", "tab. 3.1")
        K2.krok("Návrhová pevnost v tlaku", "f_{cd} = α_{cc}·f_{ck}/γ_{c}",
                f"{fmt(b.alpha_cc)}·{fmt(b.fck)}/{fmt(b.gamma_c)}", b.fcd, "MPa", "3.1.6")
        K2.krok("Návrhová pevnost v tahu", "f_{ctd} = α_{ct}·f_{ctk,0,05}/γ_{c}",
                f"{fmt(b.alpha_ct)}·{fmt(b.fctk005)}/{fmt(b.gamma_c)}", b.fctd, "MPa", "3.1.6")
        K2.krok("Mezní přetvoření (parabola-obdélník)", "ε_{c2}; ε_{cu2}; n",
                "", f"{fmt(b.eps_c2 * 1e3)} ‰; {fmt(b.eps_cu2 * 1e3)} ‰; {fmt(b.n)}", "", "tab. 3.1")
        K2.text(f"Předpínací výztuž {p.typ} ({'dráty' if p.druh == 'drat' else 'lana'}): "
                f"A_p,1 = {fmt(p.Ap_lano)} mm², f_pk = {fmt(p.fpk)} MPa, "
                f"f_p0,1k = {fmt(p.fp01k)} MPa, E_p = {fmt(p.Ep)} MPa, třída relaxace {p.trida_relaxace} "
                f"(ρ1000 = {fmt(p.rho1000)} %), γ_s = {fmt(p.gamma_s)}, tažnost ε_uk = {fmt(p.taznost)} ‰"
                + (f", tažnost oslabená korozí ε_uk,red = {fmt(p.taznost_oslabena, 1)} ‰." if p.oslabena_taznost
                   else "."))
        K2.text("Modul pružnosti E_p: dráty 205 GPa, lana 195 GPa (3.3.6(2), (3)). "
                + ("Pracovní diagram se zpevněním – stoupající větev do k·f_pd při ε_uk, k = f_pk/f_p0,1k."
                   if p.zpevneni else
                   "Pracovní diagram bez zpevnění – vodorovná větev na úrovni f_pd.")
                + " Mezní přetvoření ε_ud se kontroluje v obou případech (obr. 3.10).")
        K2.krok("Návrhová pevnost předpínací výztuže", "f_{pd} = f_{p0,1k}/γ_{s}",
                f"{fmt(p.fp01k)}/{fmt(p.gamma_s)}", p.fpd, "MPa", "3.3.6")
        K2.krok("Mezní přetvoření předpínací výztuže", "ε_{ud} = 0,9·ε_{uk}",
                f"0,9·{fmt(p.eps_uk * 1e3)} ‰", p.eps_ud * 1e3, "‰", "3.3.6(7)")
        if p.oslabena_taznost:
            od = "aktuálního stáří" if self.t_akt is not None else "konce životnosti"
            K2.text("Tažnost oslabená korozí zkracuje pracovní diagram předpínací výztuže při nezměněném sklonu "
                    "zpevnění (daném neoslabenou tažností ε_uk), výztuž proto nedosáhne pevnosti k·f_pd. Uvažuje se "
                    f"v MSÚ (ohyb) ve fázích od {od}, stejně jako oslabení plochy výztuže.")
            K2.krok("Mezní přetvoření výztuže oslabené korozí", "ε_{ud,red} = 0,9·ε_{uk,red}",
                    f"0,9·{fmt(p.eps_uk_red * 1e3, 1)} ‰", p.eps_ud_red * 1e3, "‰")
            K2.krok("Napětí na mezi přetvoření oslabené / neoslabené výztuže", "σ_{p}(ε_{ud,red}); σ_{p}(ε_{ud})",
                    "", f"{fmt(float(p.sigma_msu(p.eps_ud_red)))}; {fmt(float(p.sigma_msu(p.eps_ud)))}", "MPa")
        K2.text(f"Betonářská výztuž {s.typ}: f_yk = {fmt(s.fyk)} MPa, f_yd = {fmt(s.fyd)} MPa, "
                f"E_s = {fmt(s.Es)} MPa, ε_ud = {fmt(s.eps_ud * 1e3)} ‰.")
        K2.obrazek("diagramy_materialu", "Návrhové pracovní diagramy materiálů pro MSÚ")

    # ------------------------------------------------------------------
    def _prurezy(self):
        P = self.prurez
        K = self.protokol.kapitola("Průřezové charakteristiky", 2)
        K.text("Průřez je zadán numericky obrysovým polygonem (souřadnice y, z od spodního okraje). "
               "Charakteristiky jsou spočteny Greenovými vzorci pro polygon.")
        K.krok("Výška průřezu", "h", "", P.h, "mm")
        K.krok("Plocha betonu", "A_{c} = ½·Σ(y_{i}·z_{i+1} − y_{i+1}·z_{i})", "", P.A, "mm²")
        K.krok("Poloha těžiště od spodního okraje", "z_{t} = S_{y}/A_{c}", "", P.zt, "mm")
        K.krok("Moment setrvačnosti k těžišti", "I_{c} = I_{0} − A_{c}·z_{t}^{2}", "", P.I, "mm⁴")
        K.krok("Průřezový modul – horní vlákna", "W_{h} = I_{c}/(h − z_{t})",
               f"{fmt(P.I)}/({fmt(P.h)} − {fmt(P.zt)})", P.W_h, "mm³")
        K.krok("Průřezový modul – dolní vlákna", "W_{d} = I_{c}/z_{t}", f"{fmt(P.I)}/{fmt(P.zt)}", P.W_d, "mm³")
        K.krok("Obvod vystavený vysychání", "u", "", P.u, "mm")
        K.krok("Náhradní rozměr", "h_{0} = 2·A_{c}/u", f"2·{fmt(P.A)}/{fmt(P.u)}", P.h0, "mm", "3.1.4(5)")
        g0 = P.A * 1e-6 * self.beton.objemova_tiha
        K.krok("Vlastní tíha nosníku", "g_{0} = A_{c}·γ", f"{fmt(P.A * 1e-6)}·{fmt(self.beton.objemova_tiha)}",
               g0, "kN/m")
        K.obrazek("prurez", "Příčný řez nosníku s polohou předpínací a betonářské výztuže")
        self.g0 = g0

    # ------------------------------------------------------------------
    def _kabely(self):
        x = self.x
        self.zk = [k.geometrie.z_v(x) for k in self.kabely]
        self.ak = [k.geometrie.alfa_v(x) for k in self.kabely]
        K = self.protokol.kapitola("Předpínací výztuž a vedení kabelů", 2)
        rows = []
        for k in self.kabely:
            rows.append([k.nazev, k.pocet_lan, fmt(k.Ap), k.popis_geometrie, fmt(k.sigma_max),
                         fmt(k.P_max), k.napinani if not self.predem else "–",
                         fmt(k.mu) if not self.predem else "–", fmt(k.k) if not self.predem else "–",
                         fmt(k.pokluz) if not self.predem else "–", fmt(k.d_kanalku)])
        K.tabulka(["Kabel", "Počet lan", "A_p [mm²]", "Geometrie", "σ_p,max [MPa]", "P_max [kN]",
                   "Napínání", "μ", "k [rad/m]", "Pokluz [mm]", "∅ kanálku [mm]"], rows,
                  "Přehled předpínacích kabelů")
        rows = []
        for i in self.i_tab:
            rows.append([fmt(x[i], 3)] + [fmt(z[i], 1) for z in self.zk] +
                        [fmt(math.degrees(a[i]), 2) for a in self.ak])
        K.tabulka(["x [m]"] + [f"z {k.nazev} [mm]" for k in self.kabely] +
                  [f"α {k.nazev} [°]" for k in self.kabely], rows, "Poloha a sklon kabelů v charakteristických řezech")
        K.obrazek("kabely", "Vedení kabelů po délce nosníku")
        # kontrola výškového překrytí kanálků (kabely jsou zadány v jedné svislé rovině)
        if not self.predem:
            for a in range(len(self.kabely)):
                for c in range(a + 1, len(self.kabely)):
                    ka, kc = self.kabely[a], self.kabely[c]
                    mez = 0.5 * (ka.d_kanalku + kc.d_kanalku)
                    prekryv = np.abs(self.zk[a] - self.zk[c]) < mez
                    if mez > 0 and prekryv.any():
                        xs = x[prekryv]
                        K.text(f"⚠ Kanálky {ka.nazev} a {kc.nazev} se výškově překrývají v úseku x = "
                               f"{fmt(xs.min(), 3)}–{fmt(xs.max(), 3)} m (svislá vzdálenost os < "
                               f"{fmt(mez)} mm). V tomto úseku se při stanovení b_w,nom uvažují vedle sebe "
                               "v téže úrovni; zkontrolujte vedení kabelů (křížení ve stojině).")

        # průřezové charakteristiky po délce (brutto / ideální)
        n = len(x)
        Pz = self.prurez
        self.secP = np.tile([Pz.A, Pz.zt, Pz.I], (n, 1))
        self.secL = self.secP.copy()
        if self.charakteristiky.startswith("ideal"):
            ap = self.predp.Ep / self.beton.Ecm
            ap0 = self.predp.Ep / self.beton.Ecm_t(self.t0)
            as_ = self.betonarska.Es / self.beton.Ecm
            self.secG = self.secP.copy()
            for j in range(n):
                otvory, plus, plus0, lana = [], [], [], []
                for k, z in zip(self.kabely, self.zk):
                    if not self.predem and k.d_kanalku > 0:
                        otvory.append((z[j], -math.pi * k.d_kanalku ** 2 / 4))
                    plus.append((z[j], ((ap - 1) if self.predem else ap) * k.Ap))
                    plus0.append((z[j], (ap0 - 1) * k.Ap))
                    lana.append((z[j], -k.Ap))
                vyz = [(v.z, (as_ - 1) * v.As) for v in self.vyztuz]
                if self.predem:
                    # síla P_m,t v lanech (vč. změny napětí od vlastní tíhy při uvolnění) je v rovnováze s betonem
                    # → působí spolu s vlastní tíhou na betonový průřez bez lan; je to totéž jako síla před
                    # uvolněním a vlastní tíha na ideálním průřezu (Navrátil 4.26–4.29)
                    self.secP[j] = Pz.charakteristiky_s_body(lana + vyz)
                else:
                    self.secP[j] = Pz.charakteristiky_s_body(otvory + vyz)
                self.secG[j] = self.secP[j]
                self.secI0 = getattr(self, "secI0", np.zeros_like(self.secP))
                self.secI0[j] = Pz.charakteristiky_s_body(plus0 + vyz)
                self.secL[j] = Pz.charakteristiky_s_body(otvory + plus + vyz)
            j = self.im
            if self.predem:
                K.text("Předpínací síla P_m,t (napětí v lanech po ztrátách, včetně změny od vlastní tíhy při uvolnění) "
                       "a vlastní tíha při vnesení předpětí působí na betonový průřez bez lan (+ α_s·A_s). To je "
                       "ekvivalentní působení síly před uvolněním lan a vlastní tíhy na ideálním průřezu s α_p = "
                       "E_p/E_cm(t0) (Navrátil 4.26–4.29). Zatížení vnášená později působí na ideální průřez.")
            else:
                K.text("Účinky předpětí a vlastní tíhy při vnesení předpětí jsou počítány na oslabeném průřezu "
                       "(beton bez kabelových kanálků + α_s·A_s), účinky zatížení po zainjektování na ideálním průřezu.")
            rows = [["brutto", fmt(Pz.A), fmt(Pz.zt), fmt(Pz.I)],
                    ["pro předpětí" + (" a vlastní tíhu při vnesení" if self.predem else ""),
                     fmt(self.secP[j, 0]), fmt(self.secP[j, 1]), fmt(self.secP[j, 2])]]
            if self.predem:
                rows.append(["ideální při vnesení (pro kontrolu, α_p = E_p/E_cm(t0))", fmt(self.secI0[j, 0]),
                             fmt(self.secI0[j, 1]), fmt(self.secI0[j, 2])])
            rows.append(["pro zatížení", fmt(self.secL[j, 0]), fmt(self.secL[j, 1]), fmt(self.secL[j, 2])])
            K.tabulka(["Průřez (střed rozpětí)", "A [mm²]", "z_t [mm]", "I [mm⁴]"], rows)
        else:
            self.secG = self.secP.copy()
            K.text("Napětí jsou počítána na plném betonovém (brutto) průřezu – vliv kanálků a výztuže "
                   "na průřezové charakteristiky se zanedbává.")

    # ------------------------------------------------------------------
    def _zatizeni(self):
        x, L = self.x, self.L
        g0 = ZatezovaciStav("Vlastní tíha nosníku g0", "stale", t=self.t0,
                            rovnomerne=[(self.g0, 0.0, L)], gamma=self.n.gamma_G,
                            gamma_inf=self.n.gamma_G_inf)
        self.zs_g0 = g0
        if self.rezim_kombinace:
            g0.spocitej(x, L, self.xa, self.xb)
            self._zatizeni_kombinace()
            return
        for z in [g0] + self.stale_vstup + self.promenne:
            if z.druh == "stale" and z.t is None:
                z.t = self.t0
            z.spocitej(x, L, self.xa, self.xb)
        K = self.protokol.kapitola("Zatížení a časová osa", 2)
        rows = [[g0.nazev, "stálé", fmt(g0.t, 0), fmt(self.g0), "–", "–", "–", fmt(g0.gamma)]]
        for z in self.stale_vstup:
            rows.append([z.nazev, "stálé", fmt(z.t, 0), self._popis_zs(z), "–", "–", "–", fmt(z.gamma)])
        for z in self.promenne:
            rows.append([z.nazev + (f" [{z.skupina}]" if z.skupina else ""), "proměnné", fmt(self.t_provoz, 0),
                         self._popis_zs(z), fmt(z.psi0), fmt(z.psi1), fmt(z.psi2), fmt(z.gamma)])
        K.tabulka(["Zatěžovací stav", "Druh", "t [dny]", "Hodnota", "ψ0", "ψ1", "ψ2", "γ"], rows,
                  "Charakteristické hodnoty zatížení a součinitele kombinací (ČSN EN 1990)")
        K.text("Proměnná zatížení se stejnou skupinou působí současně (např. LM1 = TS + UDL); "
               "spojitá proměnná zatížení jsou umístěna do nepříznivých částí příčinkových čar, "
               "pohyblivé soustavy břemen jsou posouvány po celé délce nosníku.")

    def _zatizeni_kombinace(self):
        """Vnější zatížení zadané přímo kombinacemi (bez vlastní tíhy nosníku g0)."""
        nn = self.n
        kv = {k.druh: k for k in self.kombinace_vstup}
        nezname = [d for d in kv if d not in DRUHY_KOMBINACI]
        if nezname:
            raise ValueError(f"Neznámý druh kombinace: {', '.join(nezname)} "
                             f"(povolené: {', '.join(DRUHY_KOMBINACI)})")
        chybi = [DRUHY_KOMBINACI[d] for d in ("char", "casta", "kvazistala") if d not in kv]
        if not any(d in kv for d in ("6.10a", "6.10b", "6.10")):
            chybi.append("MSÚ (6.10a / 6.10b nebo 6.10)")
        if chybi:
            raise ValueError("Chybí kombinace: " + ", ".join(chybi))
        if self.t_vneseni < self.t0:
            raise ValueError("Čas vnesení stálých zatížení nesmí být menší než t0.")
        fak_g0 = {"char": 1.0, "casta": 1.0, "kvazistala": 1.0, "6.10a": nn.gamma_G,
                  "6.10": nn.gamma_G, "6.10b": nn.xi * nn.gamma_G}
        g = self.zs_g0
        self.kv: dict[str, Obalka] = {}
        for druh, k in kv.items():
            o = k.obalka(self.x, self.L, self.xa, self.xb)
            if self.kombinace_vcetne_g0:
                f = fak_g0[druh]
                o = Obalka(o.M_max - f * g.M_max, o.M_min - f * g.M_max, o.V_max - f * g.V_max,
                           o.V_min - f * g.V_max)
            self.kv[druh] = o
        K = self.protokol.kapitola("Zatížení a časová osa", 2)
        K.text("Vnější zatížení je zadáno přímo kombinacemi podle ČSN EN 1990 (vnitřní síly prostého nosníku). "
               "Vlastní tíhu nosníku g0 = " + fmt(self.g0) + " kN/m počítá program samostatně, protože působí "
               "již při vnesení předpětí; v MSÚ se přičítá s γ_G = " + fmt(nn.gamma_G) + " (6.10a, 6.10) a "
               "ξ·γ_G = " + fmt(nn.xi * nn.gamma_G) + " (6.10b). "
               + ("Zadané kombinace vlastní tíhu nosníku obsahují – její podíl se od nich odečítá."
                  if self.kombinace_vcetne_g0 else "Zadané kombinace vlastní tíhu nosníku neobsahují."))
        K.text(f"Kvazistálá kombinace (bez g0) je uvažována jako dlouhodobě působící od stáří betonu "
               f"t = {fmt(self.t_vneseni, 0)} dní (dotvarování, ztráty předpětí, průhyb). Charakteristická, častá "
               "a MSÚ kombinace se posuzují od uvedení do provozu.")
        im = self.im
        rows = []
        for druh in DRUHY_KOMBINACI:
            if druh not in kv:
                continue
            o = self.kv[druh]
            rows.append([DRUHY_KOMBINACI[druh],
                         kv[druh].popis + (" – znaménko V otočeno" if kv[druh].otoceno_V else ""),
                         fmt(o.M_max[im]), fmt(float(o.M_max.max())), fmt(float(o.M_min.min())),
                         fmt(float(o.V_max.max())), fmt(float(o.V_min.min()))])
        K.tabulka(["Kombinace", "Zadání", "M uprostřed", "M_max", "M_min", "V_max", "V_min"], rows,
                  "Vnitřní síly od zadaných kombinací bez vlastní tíhy nosníku [kNm, kN]")
        if any(k.otoceno_V for k in kv.values()):
            K.text("U kombinací označených „znaménko V otočeno“ neodpovídalo znaménko posouvající síly konvenci "
                   "V = dM/dx (např. výstup ze SCIA) – posouvající síly byly převráceny.")

    @staticmethod
    def _popis_zs(z: ZatezovaciStav) -> str:
        parts = []
        for q, a, b in z.rovnomerne:
            parts.append(f"q = {fmt(q)} kN/m ({fmt(a)}–{fmt(b)} m)")
        for F, p in z.bremena:
            parts.append(f"F = {fmt(F)} kN v x = {fmt(p)} m")
        if z.pohyblive:
            parts.append("pohyblivá břemena " + "+".join(fmt(f) for f in z.pohyblive[0]) + " kN")
        if z.tabulka:
            parts.append("vnitřní síly zadané tabulkou")
        return "; ".join(parts)

    # ------------------------------------------------------------------
    def _napeti(self, z, NP, MP, Mg0, ML, r=1.0, idx=None):
        """Napětí v betonu [MPa] ve výšce z (mm) – vektorově po délce nosníku."""
        sP = self.secP if idx is None else self.secP[idx]
        sG = self.secG if idx is None else self.secG[idx]
        sL = self.secL if idx is None else self.secL[idx]
        AP, ztP, IP = sP[..., 0], sP[..., 1], sP[..., 2]
        ztG, IG = sG[..., 1], sG[..., 2]
        AL, ztL, IL = sL[..., 0], sL[..., 1], sL[..., 2]
        return (r * (NP * 1e3 / AP + MP * 1e6 * (ztP - z) / IP) + Mg0 * 1e6 * (ztG - z) / IG
                + ML * 1e6 * (ztL - z) / IL)

    def _sily_predpeti(self, sigma: list[np.ndarray], k_Ap: float = 1.0):
        """N_P [kN], M_P [kNm], V_P [kN] po délce nosníku od napětí σ_i(x);
        k_Ap = zbývající plocha předpínací výztuže (oslabení korozí, fáze.k_Ap)."""
        N = np.zeros_like(self.x)
        M = np.zeros_like(self.x)
        V = np.zeros_like(self.x)
        ztP = self.secP[:, 1]
        for k, s, z, a in zip(self.kabely, sigma, self.zk, self.ak):
            P = s * k.Ap * k_Ap * 1e-3
            N -= P * np.cos(a)
            M += P * np.cos(a) * (z - ztP) * 1e-3
            V += P * np.sin(a)
        return N, M, V

    def _faktor_prenosu(self, msu: bool = False) -> np.ndarray:
        """Náběh předpětí v kotevní oblasti předem předpjatých lan (8.10.2.2)."""
        if not self.predem:
            return np.ones_like(self.x)
        # návrhová délka přenosu (8.10.2.2(3)): l_pt1 = 0,8·l_pt pro místní napětí (MSP), l_pt2 = 1,2·l_pt pro MSÚ
        l = self.lpt * (1.2 if msu else 0.8)
        d = np.minimum(self.x, self.L - self.x) * 1000
        return np.clip(d / l, 0.0, 1.0)

    # ------------------------------------------------------------------
    def _ztraty_okamzite(self):
        x = self.x
        p = self.predp
        n = self.n
        K = self.protokol.kapitola("Ztráty předpětí")
        K.text("Ztráty předpětí jsou stanoveny podle čl. 5.10.4–5.10.6 ČSN EN 1992-1-1 zvlášť pro "
               "každý kabel v každém řezu nosníku.")
        K1 = self.protokol.kapitola("Napětí při napínání", 2)
        lim_nap = min(n.k1_nap * p.fpk, n.k2_nap * p.fp01k)
        lim_0 = min(n.k7 * p.fpk, n.k8 * p.fp01k)
        K1.krok("Maximální napínací napětí", "σ_{p,max} = min(k_{1}·f_{pk}; k_{2}·f_{p0,1k})",
                f"min({fmt(n.k1_nap)}·{fmt(p.fpk)}; {fmt(n.k2_nap)}·{fmt(p.fp01k)})", lim_nap, "MPa",
                "5.10.2.1(1)")
        if self.predem and any(k.postup for k in self.kabely):
            raise ValueError("Postup napínání (napětí a doby podržení) lze zadat jen u dodatečně předpjatých kabelů.")
        if any(k.postup for k in self.kabely):
            K1.text("Kabely se napínají podle zadaného postupu: napětí na lisu se postupně nastavuje na uvedené "
                    "hodnoty a podrží po uvedenou dobu, nakonec se kabel napne na σ_p,max a zakotví. Napínací napětí "
                    "se posuzuje na největší napětí během postupu.")
            K1.tabulka(["Kabel", "Postup napínání (napětí na lisu / doba podržení)", "σ_lis,max [MPa]"],
                       [[k.nazev, self._popis_postupu(k), fmt(k.sigma_lis_max)] for k in self.kabely],
                       "Postup napínání kabelů")
        for k in self.kabely:
            self.protokol.pridej_posudek(K1, VysledekPosudku(
                f"Napínací napětí – {k.nazev}", "MSP", k.sigma_lis_max, lim_nap, "MPa",
                k.sigma_lis_max / lim_nap, faze="napínání", odkaz="5.10.2.1", skupina="Napětí v předpínací výztuži",
                poznamka="maximum během postupu napínání" if k.postup else ""))
        self.lim_pm0 = lim_0

        self.sig_tr, self.sig_pokl, self.sig_el = [], [], []
        self.pokluz_info = []
        self.rho_drzeni = [np.zeros_like(x) for _ in self.kabely]   # relaxace proběhlá při podržení na lisu
        if not self.predem:
            K2 = self.protokol.kapitola("Ztráta třením", 2)
            K2.text("Napětí v kabelu po ztrátě třením (5.45):")
            K2.krok("", "σ_{p}(x) = σ_{p,max}·e^{−μ·(θ + k·x)}", "", None, "", "5.10.5.2")
            K2.text("θ – součet absolutních úhlových změn kabelu od kotvy, x – délka kabelu od kotvy, "
                    "μ – součinitel tření, k – neúmyslná úhlová změna.")
            K3 = self.protokol.kapitola("Ztráta pokluzem v kotvě", 2)
            K3.text("Při pokluzu se kabel u kotvy zkracuje a tření působí v opačném směru než při napínání. "
                    "Průběh napětí po zakotvení je σ_p,po(x) = σ_A·e^{+μ·(θ + k·x)} až po dosah pokluzu x_w, "
                    "napětí v kotvě σ_A a x_w plynou z podmínky, že plocha mezi průběhy napětí před a po "
                    "zakotvení je rovna w·E_p:")
            K3.krok("", "∫_{0}^{x_{w}} [σ_{p}(x) − σ_{p,po}(x)] dx = w·E_{p},   σ_{p,po}(x) = min[σ_{p}(x); σ_{A}·e^{μ·(θ + k·x)}]",
                    "", None, "", "5.10.5.3")
            if any(k.postup for k in self.kabely):
                K2.text("Při povolení lisu působí tření opačně: σ_p(x) = min[σ_p,stáv(x); σ_lis·e^{+μ·(θ + k·x)}], "
                        "při dalším napnutí σ_p(x) = max[σ_p,stáv(x); σ_lis·e^{−μ·(θ + k·x)}].")
            for ik, k in enumerate(self.kabely):
                g = k.geometrie
                s0, s1, info, rho = self._napni_kabel(k)
                self.sig_tr.append(np.interp(x, g.x, s0))
                self.sig_pokl.append(np.interp(x, g.x, s1))
                self.pokluz_info.append(info)
                self.rho_drzeni[ik] = np.interp(x, g.x, rho)
                K2.krok(f"Kabel {k.nazev}: celková úhlová změna / délka kabelu", "θ_{celk}; L_{k}", "",
                        f"{fmt(g.theta[-1], 4)} rad; {fmt(g.s[-1])} m")
                K2.krok(f"Kabel {k.nazev}: napětí na pasivním konci / v místě minima",
                        "σ_{p,min} = σ_{p,max}·e^{−μ·(θ + k·x)}", "", float(s0.min()), "MPa")
                for strana, r in info.items():
                    K3.krok(f"Kabel {k.nazev} – kotva {strana}: požadovaná plocha napětí", "A_{w} = w·E_{p}",
                            f"{fmt(k.pokluz)}·10^{{-3}}·{fmt(p.Ep)}", r.plocha, "MPa·m")
                    K3.krok(f"Kabel {k.nazev} – kotva {strana}: dosah pokluzu", "x_{w}", "iterací", r.x_w, "m")
                    K3.krok(f"Kabel {k.nazev} – kotva {strana}: ztráta v kotvě", "Δσ_{p,w}(0) = σ_{p}(0) − σ_{A}",
                            "", r.dsigma_kotva, "MPa")
                    if r.cely_kabel:
                        K3.text("Pokluz ovlivní celou délku kabelu.")
            rows = []
            for i in self.i_tab:
                rows.append([fmt(x[i], 3)] + [f"{fmt(a[i], 1)} / {fmt(b[i], 1)}"
                                              for a, b in zip(self.sig_tr, self.sig_pokl)])
            K3.tabulka(["x [m]"] + [f"{k.nazev}: σ po tření / po pokluzu [MPa]" for k in self.kabely], rows,
                       "Napětí v kabelech po ztrátě třením a pokluzem")
        else:
            K2 = self.protokol.kapitola("Ztráty před uvolněním lan (předem předpjatý prvek)", 2)
            t_h = self.relax_pred_h if self.relax_pred_h is not None else self.t0 * 24.0
            self.t_rel_h = t_h
            for k in self.kabely:
                d_pr = float(p.relaxace(k.sigma_max, t_h))
                s = np.full_like(x, k.sigma_max - d_pr)
                self.sig_tr.append(np.full_like(x, k.sigma_max))
                self.sig_pokl.append(s)
                K2.krok(f"{k.nazev}: relaxace do uvolnění lan", f"Δσ_{{pr}} = σ_{{pi}}·{p.popis_relaxace}",
                        f"t = {fmt(t_h)} h, μ = {fmt(k.sigma_max / p.fpk)}", d_pr, "MPa", "3.3.2(7)")
            K2.text("Ztráta pokluzem v kotvách napínací dráhy a třením na deviátorech je zahrnuta "
                    "v zadaném napětí σ_p,max (napětí lan před betonáží).")
            # délka přenosu – první odhad z napětí před uvolněním, zpřesní se po výpočtu σ_pm0
            b = self.beton
            fctd_t = b.alpha_ct * 0.7 * b.fctm_t(self.t0) / b.gamma_c
            fbpt = self.eta_p1 * 1.0 * fctd_t
            d_l = p.d_lana or 15.7
            self.lpt = self.a1_pt * self.a2_pt * d_l * max(float(s[self.im]) for s in self.sig_pokl) / fbpt

        # --- pružné přetvoření betonu ------------------------------------
        K4 = self.protokol.kapitola("Ztráta pružným přetvořením betonu", 2)
        b = self.beton
        Ec0 = b.Ecm_t(self.t0)
        nk = self.pocet_napinani or len(self.kabely)
        j = 1.0 if self.predem else (nk - 1) / (2 * nk)
        K4.krok("Modul pružnosti betonu při vnesení předpětí", "E_{cm}(t_{0}) = (f_{cm}(t_{0})/f_{cm})^{0,3}·E_{cm}",
                f"({fmt(b.fcm_t(self.t0))}/{fmt(b.fcm)})^{{0,3}}·{fmt(b.Ecm)}", Ec0, "MPa", "3.1.3(3)")
        if self.predem:
            K4.text("U předem předpjatých prvků se při uvolnění lan beton zkrátí současně s lany (j = 1):")
        else:
            K4.text(f"Kabely jsou napínány postupně v n = {nk} krocích; ztráta postupným napínáním "
                    "(5.44) se uvažuje průměrnou hodnotou pro všechny kabely:")
        K4.krok("", "Δσ_{el} = j·(E_{p}/E_{cm}(t_{0}))·|σ_{c}(z_{p})|", f"j = {fmt(j)}", None, "", "5.10.5.1")
        Mg0 = self.zs_g0.M_max
        # u předem předpjatých prvků závisí délka přenosu na σ_pm0 (po uvolnění) → dva průchody
        for pruchod in range(2 if self.predem else 1):
            if pruchod == 1:
                self.lpt = self.a1_pt * self.a2_pt * d_l * sig_pm0_lpt / fbpt
            fr = self._faktor_prenosu()
            sig = [s * fr for s in self.sig_pokl]
            for _ in range(4):
                NP, MP, _ = self._sily_predpeti(sig)
                new = []
                for k, s0, z in zip(self.kabely, self.sig_pokl, self.zk):
                    sc = self._napeti(z, NP, MP, Mg0, 0.0)
                    d_el = j * p.Ep / Ec0 * np.maximum(-sc, 0.0)
                    new.append((s0 - d_el) * fr)
                sig = new
            sig_pm0_lpt = max(float(s[self.im]) for s in sig)
        self.d_el = [(s0 * fr - s) for s0, s in zip(self.sig_pokl, sig)]
        self.sig_pm0 = sig
        if self.predem:
            K2.krok("Pevnost v soudržnosti při přenosu", "f_{bpt} = η_{p1}·η_{1}·f_{ctd}(t)",
                    f"{fmt(self.eta_p1)}·1,0·{fmt(fctd_t)}", fbpt, "MPa", "8.10.2.2(1)")
            K2.krok("Základní délka přenosu (σ_pm0 – napětí těsně po uvolnění lan)",
                    "l_{pt} = α_{1}·α_{2}·φ·σ_{pm0}/f_{bpt}",
                    f"{fmt(self.a1_pt)}·{fmt(self.a2_pt)}·{fmt(d_l)}·{fmt(sig_pm0_lpt)}/{fmt(fbpt)}",
                    self.lpt, "mm", "8.10.2.2(2)")
            K2.krok("Návrhové délky přenosu", "l_{pt1} = 0,8·l_{pt};  l_{pt2} = 1,2·l_{pt}", "",
                    f"{fmt(0.8 * self.lpt)} mm; {fmt(1.2 * self.lpt)} mm", "", "8.10.2.2(3)")
            K2.text("V oblasti přenosu je předpětí uvažováno s lineárním náběhem: pro posudky MSP (místní napětí "
                    "při vnesení a v provozu) s méně příznivou kratší délkou l_pt1, pro MSÚ s l_pt2.")
        # relaxace proběhlá při podržení na lisu → ekvivalentní čas při napětí po zakotvení
        self.t_ekv = [np.where(r > 0, p.cas_relaxace(np.maximum(sp, 1.0), r), 0.0)
                      for r, sp in zip(self.rho_drzeni, self.sig_pm0)]
        im = self.im
        for k, d in zip(self.kabely, self.d_el):
            K4.krok(f"Kabel {k.nazev} – ztráta ve středu rozpětí", "Δσ_{el}", "", float(d[im]), "MPa")

        # --- napětí po okamžitých ztrátách ---------------------------------
        K5 = self.protokol.kapitola("Napětí po okamžitých ztrátách", 2)
        K5.krok("Mezní napětí po zakotvení", "σ_{pm0,max} = min(k_{7}·f_{pk}; k_{8}·f_{p0,1k})",
                f"min({fmt(n.k7)}·{fmt(p.fpk)}; {fmt(n.k8)}·{fmt(p.fp01k)})", lim_0, "MPa", "5.10.3(2)")
        for k, s in zip(self.kabely, self.sig_pm0):
            i = int(np.argmax(s))
            self.protokol.pridej_posudek(K5, VysledekPosudku(
                f"Napětí po zakotvení σ_pm0 – {k.nazev}", "MSP", float(s[i]), lim_0, "MPa",
                float(s[i]) / lim_0, faze="po vnesení předpětí", x=float(x[i]), odkaz="5.10.3(2)",
                skupina="Napětí v předpínací výztuži"))
        NP, MP, VP = self._sily_predpeti(self.sig_pm0)
        rows = []
        for i in self.i_tab:
            rows.append([fmt(x[i], 3)] + [fmt(s[i], 1) for s in self.sig_pm0] + [fmt(-NP[i]), fmt(MP[i])])
        K5.tabulka(["x [m]"] + [f"σ_pm0 {k.nazev} [MPa]" for k in self.kabely] + ["P_m0 [kN]", "M_P [kNm]"],
                   rows, "Napětí a síly po okamžitých ztrátách")
        K5.obrazek("napeti_kabelu", "Průběh napětí v kabelech po délce – okamžité a dlouhodobé ztráty")

    @staticmethod
    def _popis_postupu(k: Kabel) -> str:
        def c(v: float) -> str:
            return f"{v:g}".replace(".", ",")
        casti = [f"{c(sg)} MPa" + (f" / {c(tm)} min" if tm else "") for sg, tm in k.postup]
        return " → ".join(casti + [f"{c(k.sigma_max)} MPa (zakotvení)"])

    def _napni_kabel(self, k: Kabel):
        """Napínání kabelu podle postupu (napětí na lisu, podržení) a zakotvení.

        Vrací průběh napětí před zakotvením, po pokluzu, info o pokluzu a poměrnou relaxaci proběhlou
        při podrženích – vše na síti geometrie kabelu.
        """
        g = k.geometrie
        p = self.predp
        strany = []
        if k.napinani in ("levy", "oba"):
            strany.append((0, np.exp(-k.mu * (g.theta + k.k * g.s))))
        if k.napinani in ("pravy", "oba"):
            strany.append((-1, np.exp(-k.mu * (g.theta[-1] - g.theta + k.k * (g.s[-1] - g.s)))))
        s0 = np.zeros_like(g.x)
        rho = np.zeros_like(g.x)
        for s_lis, t_min in k.kroky_lisu:
            for i_k, f in strany:
                # napnutí: tření proti pohybu od lisu; povolení: tření v opačném směru
                s0 = np.maximum(s0, s_lis * f) if s_lis >= s0[i_k] else np.minimum(s0, s_lis / f)
            if t_min > 0:
                sp = np.maximum(s0, 1.0)
                t_e = np.where(rho > 0, p.cas_relaxace(sp, rho), 0.0)
                rho = p.relaxace(sp, t_e + t_min / 60.0) / sp
        s1 = s0.copy()
        info = {}
        # při oboustranném napínání sahá vliv každé kotvy po místo minima průběhu od tření
        xk = g.x[int(np.argmin(np.maximum(strany[0][1], strany[1][1])))] if k.napinani == "oba" else None

        def pokluz(xs, sig, f_zpet, x_konec):
            # při pokluzu působí tření proti zpětnému pohybu kabelu: σ_po(x) = min[σ0(x); σ_A·e^{+μ(θ+kx)}]
            # (Navrátil 4.14–4.18) – platí pro klesající průběh i po povolení lisu
            return ztrata_pokluzem_obecne(xs, sig, f_zpet, k.pokluz, p.Ep, x_konec=x_konec)

        if k.napinani in ("levy", "oba"):
            r = pokluz(g.x, s1, np.exp(k.mu * (g.theta + k.k * g.s)), xk)
            s1 = r.sigma
            info["levy"] = r
        if k.napinani in ("pravy", "oba"):
            f_p = np.exp(k.mu * (g.theta[-1] - g.theta + k.k * (g.s[-1] - g.s)))
            r = pokluz(g.x[::-1][0] - g.x[::-1], s1[::-1], f_p[::-1], (g.x[-1] - xk) if xk is not None else None)
            s1 = r.sigma[::-1]
            info["pravy"] = r
        return s0, s1, info, rho

    # ------------------------------------------------------------------
    def _popis_oslabeni(self, f: Faze, co: tuple[str, ...] = ("Ap", "As", "Asw", "taznost")) -> str:
        """Oslabení výztuže korozí ve fázi f jako text (jen uplatněné složky z co); prázdný bez oslabení."""
        k = {"Ap": f.k_Ap, "As": f.k_As, "Asw": f.k_Asw}
        znacky = {"Ap": "A_p", "As": "A_s", "Asw": "A_sw"}
        casti = [f"{znacky[c]} −{fmt(self.oslabeni[c], 1)} %" for c in co if c in k and k[c] < 1.0]
        if "taznost" in co and f.eps_ud_p is not None:
            casti.append(f"ε_uk,red = {fmt(self.predp.taznost_oslabena, 1)} ‰")
        return ", ".join(casti)

    def _faze_a_dlouhodobe_ztraty(self):
        x = self.x
        b, p, P = self.beton, self.predp, self.prurez
        h0 = P.h0
        K = self.protokol.kapitola("Časová osa a dlouhodobé ztráty", 2)
        # fáze
        faze = [Faze("Vnesení předpětí", self.t0, False, [self.zs_g0])]
        casy = sorted({z.t for z in self.stale_vstup if z.t > self.t0} | {self.t_provoz, self.t_konec})
        if self.rezim_kombinace:
            casy = sorted({self.t_provoz, self.t_konec} | ({self.t_vneseni} if self.t_vneseni > self.t0 else set()))
        if self.t_akt is not None:
            casy = sorted(set(casy) | {self.t_akt})
        for t in casy:
            aktivni = [self.zs_g0] + [z for z in self.stale_vstup if z.t <= t]
            if t == self.t_konec:
                nazev = "Konec životnosti"
            elif t == self.t_akt:
                nazev = "Aktuální stáří"
            elif t == self.t_provoz:
                nazev = "Uvedení do provozu"
            elif self.rezim_kombinace:
                nazev = "Vnesení ostatních stálých zatížení"
            else:
                nazev = "Vnesení: " + ", ".join(z.nazev for z in self.stale_vstup if z.t == t)
            faze.append(Faze(nazev, t, t >= self.t_provoz, aktivni))
            if self.rezim_kombinace:
                faze[-1].popis = "g0" + (" + kvazistálá kombinace" if t >= self.t_vneseni else "")
        # zatížení v čase t0 pro předpětí mají vliv i stálá zatížení s t <= t0
        faze[0].stale = [self.zs_g0] + [z for z in self.stale_vstup if z.t <= self.t0]
        if self.rezim_kombinace:
            faze[0].popis = "g0" + (" + kvazistálá kombinace" if self.t_vneseni <= self.t0 else "")
        # oslabení výztuže korozí – od aktuálního stáří (bez něj jen konec životnosti)
        t_osl = self.t_akt if self.t_akt is not None else self.t_konec
        osl = self.oslabeni
        for f in faze:
            if f.provoz and f.t >= t_osl:
                f.k_Ap = 1.0 - osl["Ap"] / 100.0
                f.k_As = 1.0 - osl["As"] / 100.0
                f.k_Asw = 1.0 - osl["Asw"] / 100.0
                if p.oslabena_taznost:
                    f.eps_ud_p = p.eps_ud_red
        self.faze = faze

        K.tabulka(["Fáze", "Stáří betonu t [dny]", "Působící stálá zatížení", "Proměnná zatížení",
                   "Oslabení výztuže korozí"],
                  [[f.nazev, fmt(f.t, 0), f.popis or ", ".join(z.nazev for z in f.stale),
                    "ano" if f.provoz else "ne", self._popis_oslabeni(f) or "–"] for f in faze],
                  "Časová osa výstavby a provozu")
        if self.t_akt is not None:
            K.text(f"Konstrukce se posuzuje i pro aktuální stáří t = {fmt(self.t_akt, 0)} dní "
                   "(ztráty předpětí, mezní stavy použitelnosti a únosnosti jako v ostatních provozních fázích).")
        if any(v > 0 for v in osl.values()):
            K.text(f"Oslabení výztuže korozí (zmenšení plochy) se uvažuje ve fázích od "
                   f"{'aktuálního stáří' if self.t_akt is not None else 'konce životnosti'}: "
                   f"předpínací výztuž {fmt(osl['Ap'], 1)} % – předpínací síla P = σ_p·A_p·(1 − ρ_p) "
                   f"(napětí ve zbývající výztuži se nemění) a plocha A_p v MSÚ; podélná betonářská výztuž "
                   f"{fmt(osl['As'], 1)} %; smyková výztuž {fmt(osl['Asw'], 1)} %. Ztráty předpětí se počítají "
                   "pro neoslabenou výztuž, průřezové charakteristiky se nemění.")
        if p.oslabena_taznost:
            K.text(f"Tažnost předpínací výztuže oslabená korozí ε_uk,red = {fmt(p.taznost_oslabena, 1)} ‰ "
                   f"(neoslabená ε_uk = {fmt(p.taznost)} ‰) se uvažuje ve fázích od "
                   f"{'aktuálního stáří' if self.t_akt is not None else 'konce životnosti'}: mezní přetvoření "
                   f"v MSÚ ε_ud,red = {fmt(p.eps_ud_red * 1e3)} ‰, pracovní diagram se nemění (kap. Materiály).")

        # zatěžovací kroky pro dotvarování
        Mg0 = self.zs_g0.M_max
        NP0, MP0, _ = self._sily_predpeti(self.sig_pm0)
        # zatěžovací kroky: (t_k, název, [σ_c,i(x)] v úrovni kabelů, vnější moment M_k(x) mimo g0)
        kroky = []
        if self.rezim_kombinace:
            M0 = self.kv["kvazistala"].M_max if self.t_vneseni <= self.t0 else np.zeros_like(x)
            kroky.append((self.t0, "předpětí + vlastní tíha nosníku",
                          [self._napeti(z, NP0, MP0, Mg0, M0) for z in self.zk], M0))
            if self.t_vneseni > self.t0:
                Mq = self.kv["kvazistala"].M_max
                kroky.append((self.t_vneseni, "kvazistálá kombinace",
                              [self._napeti(z, 0, 0, 0, Mq) for z in self.zk], Mq))
        else:
            M0 = sum((zz.M_max for zz in self.stale_vstup if zz.t <= self.t0), np.zeros_like(x))
            kroky.append((self.t0, "předpětí + stálá zatížení při t0",
                          [self._napeti(z, NP0, MP0, Mg0, M0) for z in self.zk], M0))
            for zz in self.stale_vstup:
                if zz.t > self.t0:
                    kroky.append((zz.t, zz.nazev, [self._napeti(z, 0, 0, 0, zz.M_max) for z in self.zk],
                                  zz.M_max))
            Mqp = sum((z.psi2 * z.M_max for z in self.promenne), np.zeros_like(x))
            if np.any(Mqp != 0):
                kroky.append((self.t_provoz, "kvazistálá část proměnných zatížení",
                              [self._napeti(z, 0, 0, 0, Mqp) for z in self.zk], Mqp))
        self.kroky_dotv = kroky

        # nelineární dotvarování od předpětí
        fck0 = b.fck_t(self.t0)
        smin = min(float(self._napeti(z, NP0, MP0, Mg0, 0.0).min()) for z in (0.0, P.h))
        _, k_sig = reologie.nelinearni_dotvarovani(1.0, smin, fck0)
        self.k_sigma0 = k_sig

        # --- smršťování ---------------------------------------------------
        Ks = self.protokol.kapitola("Smršťování betonu", 2)
        sh = reologie.smrstovani(b, self.RH, h0, self.t_konec, self.t_s)
        sh0 = reologie.smrstovani(b, self.RH, h0, self.t0, self.t_s)
        Ks.text(f"Relativní vlhkost RH = {fmt(self.RH)} %, konec ošetřování t_s = {fmt(self.t_s)} dne, "
                f"h0 = {fmt(h0)} mm, cement třídy {b.cement}. Hodnoty pro konec životnosti t = {fmt(self.t_konec, 0)} dní:")
        Ks.krok("Součinitel vlhkosti", "β_{RH} = 1,55·[1 − (RH/RH_{0})^{3}]", f"1,55·[1 − ({fmt(self.RH)}/100)^{{3}}]",
                sh["beta_RH"], "", "(B.12)")
        Ks.krok("Základní smršťování vysycháním",
                "ε_{cd,0} = 0,85·[(220 + 110·α_{ds1})·exp(−α_{ds2}·f_{cm}/f_{cm0})]·10^{−6}·β_{RH}",
                f"0,85·[(220 + 110·{fmt(sh['alpha_ds1'])})·exp(−{fmt(sh['alpha_ds2'])}·{fmt(b.fcm)}/10)]·10^{{−6}}·{fmt(sh['beta_RH'])}",
                sh["eps_cd0"], "", "(B.11)")
        Ks.krok("Součinitel náhradního rozměru", "k_{h}", f"h0 = {fmt(h0)} mm", sh["k_h"], "", "tab. 3.3")
        Ks.krok("Časový průběh vysychání", "β_{ds}(t,t_{s}) = (t − t_{s})/[(t − t_{s}) + 0,04·√(h_{0}^{3})]",
                f"({fmt(self.t_konec, 0)} − {fmt(self.t_s)})/[({fmt(self.t_konec, 0)} − {fmt(self.t_s)}) + 0,04·√({fmt(h0)}^{{3}})]",
                sh["beta_ds"], "", "(3.10)")
        Ks.krok("Smršťování vysycháním", "ε_{cd}(t) = β_{ds}(t,t_{s})·k_{h}·ε_{cd,0}",
                f"{fmt(sh['beta_ds'])}·{fmt(sh['k_h'])}·{fmt(sh['eps_cd0'])}", sh["eps_cd"], "", "(3.9)")
        Ks.krok("Autogenní smršťování (konečné)", "ε_{ca}(∞) = 2,5·(f_{ck} − 10)·10^{−6}",
                f"2,5·({fmt(b.fck)} − 10)·10^{{−6}}", sh["eps_ca_inf"], "", "(3.12)")
        Ks.krok("Autogenní smršťování", "ε_{ca}(t) = [1 − exp(−0,2·t^{0,5})]·ε_{ca}(∞)",
                f"{fmt(sh['beta_as'])}·{fmt(sh['eps_ca_inf'])}", sh["eps_ca"], "", "(3.11), (3.13)")
        Ks.krok("Celkové smršťování", "ε_{cs}(t) = ε_{cd}(t) + ε_{ca}(t)", "", sh["eps_cs"], "", "(3.8)")
        Ks.krok("Smršťování do vnesení předpětí", "ε_{cs}(t_{0})", f"t0 = {fmt(self.t0)} dní", sh0["eps_cs"], "")
        Ks.text("Ztrátu předpětí způsobuje jen smršťování po vnesení předpětí: ε_cs(t) − ε_cs(t0).")

        # --- dotvarování ---------------------------------------------------
        Kd = self.protokol.kapitola("Dotvarování betonu", 2)
        cr = reologie.dotvarovani(b, self.RH, h0, self.t_konec, self.t0)
        Kd.text(f"Součinitel dotvarování podle přílohy B.1 pro zatížení v čase t0 = {fmt(self.t0)} dní "
                f"a konec životnosti t = {fmt(self.t_konec, 0)} dní:")
        Kd.krok("Součinitele vlivu pevnosti", "α_{1} = (35/f_{cm})^{0,7}; α_{2} = (35/f_{cm})^{0,2}; α_{3} = (35/f_{cm})^{0,5}",
                "", f"{fmt(cr['alpha1'])}; {fmt(cr['alpha2'])}; {fmt(cr['alpha3'])}", "", "(B.8c)")
        Kd.krok("Vliv vlhkosti", "φ_{RH} = [1 + (1 − RH/100)/(0,1·h_{0}^{1/3})·α_{1}]·α_{2}" if b.fcm > 35 else
                "φ_{RH} = 1 + (1 − RH/100)/(0,1·h_{0}^{1/3})", "", cr["phi_RH"], "", "(B.3)")
        Kd.krok("Vliv pevnosti betonu", "β(f_{cm}) = 16,8/√f_{cm}", f"16,8/√{fmt(b.fcm)}", cr["beta_fcm"], "", "(B.4)")
        Kd.krok("Upravené stáří při zatížení (druh cementu)", "t_{0} = t_{0,T}·[9/(2 + t_{0,T}^{1,2}) + 1]^{α} ≥ 0,5",
                "", cr["t0_upr"], "dní", "(B.9)")
        Kd.krok("Vliv stáří při zatížení", "β(t_{0}) = 1/(0,1 + t_{0}^{0,20})", "", cr["beta_t0"], "", "(B.5)")
        Kd.krok("Základní součinitel dotvarování", "φ_{0} = φ_{RH}·β(f_{cm})·β(t_{0})",
                f"{fmt(cr['phi_RH'])}·{fmt(cr['beta_fcm'])}·{fmt(cr['beta_t0'])}", cr["phi0"], "", "(B.2)")
        Kd.krok("Součinitel β_H", "β_{H} = 1,5·[1 + (0,012·RH)^{18}]·h_{0} + 250·α_{3} ≤ 1500·α_{3}", "",
                cr["beta_H"], "", "(B.8)")
        Kd.krok("Časový průběh dotvarování", "β_{c}(t,t_{0}) = [(t − t_{0})/(β_{H} + t − t_{0})]^{0,3}", "",
                cr["beta_c"], "", "(B.7)")
        Kd.krok("Součinitel dotvarování", "φ(t,t_{0}) = φ_{0}·β_{c}(t,t_{0})",
                f"{fmt(cr['phi0'])}·{fmt(cr['beta_c'])}", cr["phi"], "", "(B.1)")
        Kd.krok("Poměr napětí při vnesení předpětí", "k_{σ} = |σ_{c}|/f_{ck}(t_{0})",
                f"{fmt(abs(smin))}/{fmt(fck0)}", k_sig, "", "3.1.4(4)")
        if k_sig > 0.45:
            Kd.text(f"k_σ > 0,45 → uvažuje se nelineární dotvarování od předpětí: φ_nl = φ·exp[1,5·(k_σ − 0,45)] "
                    f"= φ·{fmt(math.exp(1.5 * (k_sig - 0.45)))}.")
        rows = []
        for t_k, naz, _, _ in kroky:
            rows.append([naz, fmt(t_k, 0)] + [fmt(self._phi(f.t, t_k, first=(t_k == self.t0)))
                                               for f in faze])
        Kd.tabulka(["Zatěžovací krok", "t_k [dny]"] + [f"φ({fmt(f.t, 0)}, t_k)" for f in faze], rows,
                   "Součinitele dotvarování pro jednotlivé zatěžovací kroky (superpozice)")

        # --- relaxace a výsledná ztráta (5.46) ----------------------------
        Kr = self.protokol.kapitola("Relaxace a celkové dlouhodobé ztráty (5.46)", 2)
        Kr.text("Ztráta relaxací podle 3.3.2(7): Δσ_pr = σ_pi·" + p.popis_relaxace +
                f", čas od napnutí v hodinách (nejvýše {fmt(self.n.relaxace_t_max_h, 0)} h podle 3.3.2(8)). "
                "Podle 5.10.6(1) je σ_pi napětí σ_p(G + P_m0 + ψ2·Q): napětí po okamžitých ztrátách σ_pm0 "
                "(obsahuje vlastní tíhu při vnesení) zvětšené o α_e·σ_c od ostatních stálých a kvazistálých "
                "proměnných zatížení vnesených do daného času v úrovni kabelu.")
        if self.predem:
            Kr.text("U předem předpjatých lan proběhne relaxace Δσ_pr,0 již před uvolněním (při napětí σ_p,max). Po "
                    "uvolnění klesne napětí na σ_pm0, a proto se kapacita relaxace přepočte podle přílohy D: pro fiktivní "
                    "napětí σ_f = σ_pm0 + Δσ_pr,0 se určí ekvivalentní čas t_e, za který by relaxace dosáhla Δσ_pr,0, a "
                    "relaxace po uvolnění je Δσ_pr = Δσ_pr(σ_f; t_e + t) − Δσ_pr,0.")
            im_ = self.im
            cor_rows = []
            for k, s in zip(self.kabely, self.sig_pm0):
                cor = float(p.relaxace(k.sigma_max, self.t_rel_h))
                sf = float(s[im_]) + cor
                cor_rows.append([k.nazev, fmt(k.sigma_max), fmt(cor), fmt(float(s[im_])), fmt(sf),
                                 fmt(float(p.cas_relaxace(sf, cor / sf)))])
            Kr.tabulka(["Lano", "σ_p,max [MPa]", "Δσ_pr,0 [MPa]", "σ_pm0 [MPa]", "σ_f [MPa]", "t_e [h]"], cor_rows,
                       "Relaxace před uvolněním a ekvivalentní čas (střed rozpětí)")
        if any(k.postup for k in self.kabely):
            im_ = self.im
            Kr.text("Relaxace, která proběhne při podržení napětí na lisu, se do dalšího průběhu započítá metodou "
                    "ekvivalentního času (obdobně jako 10.3.2.2(2)): pro každé podržení se určí doba t_e, za kterou by "
                    "při daném napětí proběhla dosavadní poměrná relaxace ρ, a ρ se zvětší o relaxaci za dobu podržení; "
                    "po zakotvení se z výsledné ρ určí ekvivalentní čas t_e při napětí σ_p(G + P_m0 + ψ2·Q). Relaxace po "
                    "zakotvení je pak Δσ_pr = Δσ_pr(σ_p; t_e + t) − Δσ_pr(σ_p; t_e). Uvažuje se, že lis během podržení "
                    "udržuje napětí.")
            for ik, k in enumerate(self.kabely):
                if not k.postup:
                    continue
                Kr.krok(f"{k.nazev}: poměrná relaxace při podržení na lisu (střed rozpětí)", "ρ = Δσ_{pr}/σ", "",
                        100 * float(self.rho_drzeni[ik][im_]), "%", "3.3.2(7)")
                Kr.krok(f"{k.nazev}: ekvivalentní čas při σ_pm0 = {fmt(float(self.sig_pm0[ik][im_]))} MPa",
                        "t_{e}: Δσ_{pr}(σ_{pm0}; t_{e})/σ_{pm0} = ρ", "", float(self.t_ekv[ik][im_]), "h")
        Kr.text("Dlouhodobé ztráty od smršťování, dotvarování a relaxace podle (5.46); pro zatížení vnášená "
                "postupně se dotvarovací člen počítá superpozicí Σ φ(t,t_k)·Δσ_c,k:")
        Kr.krok("", "Δσ_{p,c+s+r} = [ε_{cs}·E_{p} + 0,8·Δσ_{pr} + (E_{p}/E_{cm})·Σφ(t,t_{k})·σ_{c,k}] / "
                "[1 + (E_{p}/E_{cm})·(A_{p}/A_{c})·(1 + A_{c}·z_{cp}^{2}/I_{c})·(1 + 0,8·φ(t,t_{0}))]",
                "", None, "", "5.10.6(2)")
        Ac, Ic = P.A, P.I
        Ap_tot = self.Ap
        faze[0].sigma = [s.copy() for s in self.sig_pm0]
        faze[0].ztraty = {"eps_cs": 0.0}
        im = self.im
        for f in faze[1:]:
            sigs, det, eps, phi0, zcp, zres = self._dlouhodobe(f.t)
            f.sigma = sigs
            f.ztraty = {"eps_cs": eps, "phi0": phi0, "kabely": det}
            # podrobný postup ve středu rozpětí
            if f.t == self.t_konec or f.provoz:
                Kr.text(f"<b>{f.nazev_t}</b> – střed rozpětí:")
                Kr.krok("Smršťování po vnesení předpětí", "ε_{cs}(t) − ε_{cs}(t_{0})", "", eps, "")
                Kr.krok("Součinitel dotvarování", "φ(t,t_{0})", "", phi0, "")
                Kr.krok("Excentricita výslednice předpětí", "z_{cp} = z_{t} − z_{p}", f"{fmt(P.zt)} − {fmt(zres[im])}",
                        float(zcp[im]), "mm")
                for k, d in zip(self.kabely, det):
                    m = d["mezi"]
                    Kr.krok(f"{k.nazev}: napětí pro relaxaci", "σ_{p}(G + P_{m0} + ψ_{2}Q) = σ_{pm0} + α_{e}·σ_{c,G+ψ2Q}",
                            f"{fmt(float(self.sig_pm0[self.kabely.index(k)][im]))} + {fmt(float(d['ds_G'][im]))}",
                            float(d["s_rel"][im]), "MPa", "5.10.6(1)")
                    Kr.krok(f"{k.nazev}: relaxace", "Δσ_{pr}", "", float(np.atleast_1d(d["d_pr"])[im]
                                                                          if np.ndim(d["d_pr"]) else d["d_pr"]), "MPa")
                    Kr.krok(f"{k.nazev}: dotvarovací člen", "Σφ(t,t_{k})·σ_{c,k}(z_{p})", "", float(d["creep"][im]), "MPa")
                    Kr.krok(f"{k.nazev}: ztráta Δσ_p,c+s+r", "[ε_{cs}E_{p} + 0,8Δσ_{pr} − α_{p}Σφσ_{c}]/jmenovatel",
                            f"[{fmt(m['clen_smrst'])} + {fmt(float(np.atleast_1d(m['clen_relax'])[im] if np.ndim(m['clen_relax']) else m['clen_relax']))} + "
                            f"{fmt(float(m['clen_dotv'][im]))}] / {fmt(float(m['jmenovatel'][im]) if np.ndim(m['jmenovatel']) else m['jmenovatel'])}",
                            float(d["loss"][im]), "MPa")
        # tabulka sil v čase
        rows = []
        for f in faze:
            NP, MP, _ = self._sily_predpeti(f.sigma, f.k_Ap)
            rows.append([f.nazev, fmt(f.t, 0)] + [fmt(-NP[i]) for i in self.i_tab])
        Kr.tabulka(["Fáze", "t [dny]"] + [f"P [kN] {h}" for h in self._x_tab_hlavicka()], rows,
                   "Předpínací síla P_m,t v čase (střední hodnota)")
        P0 = sum(k.P_max for k in self.kabely)
        Pk = -self._sily_predpeti(faze[-1].sigma, faze[-1].k_Ap)[0][im]
        Kr.krok("Celková ztráta ve středu rozpětí na konci životnosti", "(P_{max} − P_{m,∞})/P_{max}",
                f"({fmt(P0)} − {fmt(Pk)})/{fmt(P0)}", 100 * (P0 - Pk) / P0, "%")
        Kr.obrazek("ztraty_rozklad", "Rozklad ztrát předpětí ve středu rozpětí")
        Kr.obrazek("sila_v_case", "Předpínací síla ve středu rozpětí v čase")

    def _rozklad_ztrat(self, j: int, i: int) -> dict:
        """Rozklad ztrát kabelu j v řezu i na konci životnosti [MPa] (součet složek = σ_p,max − σ_p,∞)."""
        k, f = self.kabely[j], self.faze[-1]
        fr = float(self._faktor_prenosu()[i])
        s_tr, s_pk = float(self.sig_tr[j][i]), float(self.sig_pokl[j][i])
        mez = f.ztraty["kabely"][j]["mezi"]

        def v(a):
            return float(np.broadcast_to(np.asarray(a, dtype=float), self.x.shape)[i])

        jm = v(mez["jmenovatel"])
        d = {
            "treni": k.sigma_max - s_tr,
            "pokluz": s_tr - s_pk,
            "prenos": (1.0 - fr) * s_pk,
            "pruzne": float(self.d_el[j][i]),
            "smrstovani": v(mez["clen_smrst"]) / jm * fr,
            "dotvarovani": v(mez["clen_dotv"]) / jm * fr,
            "relaxace": v(mez["clen_relax"]) / jm * fr,
        }
        d["okamzite"] = d["treni"] + d["pokluz"] + d["prenos"] + d["pruzne"]
        d["dlouhodobe"] = d["smrstovani"] + d["dotvarovani"] + d["relaxace"]
        d["celkem"] = k.sigma_max - float(f.sigma[j][i])
        d["sigma_max"], d["sigma_konec"] = k.sigma_max, float(f.sigma[j][i])
        return d

    def _prehled_ztrat(self):
        """Přehledná tabulka ztrát předpětí na konci životnosti v procentech σ_p,max."""
        K = self.protokol.kapitola("Přehled ztrát předpětí na konci životnosti", 2)
        f = self.faze[-1]
        im = self.im
        Ap = np.array([k.Ap for k in self.kabely])
        sloupce = ([("relaxace před uvolněním", "pokluz"), ("nepřenesené v kotevní oblasti", "prenos")]
                   if self.predem else [("tření", "treni"), ("pokluz", "pokluz")])
        sloupce += [("pružné přetvoření", "pruzne"), ("smršťování", "smrstovani"), ("dotvarování", "dotvarovani"),
                    ("relaxace", "relaxace")]
        roz = [self._rozklad_ztrat(j, im) for j in range(len(self.kabely))]
        if self.predem and all(abs(r["prenos"]) < 1e-9 for r in roz):
            sloupce = [s for s in sloupce if s[1] != "prenos"]
        klice = [s[1] for s in sloupce] + ["okamzite", "dlouhodobe", "celkem"]
        # vážený průměr podle A_p: Σ Δσ·A_p / Σ σ_p,max·A_p
        smaxAp = sum(r["sigma_max"] * a for r, a in zip(roz, Ap))
        celk = {kl: sum(r[kl] * a for r, a in zip(roz, Ap)) / smaxAp for kl in klice}
        self.prehled_ztrat = {"x": float(self.x[im]), "kabely": roz, "celkem_pct": {k: 100 * v for k, v in celk.items()}}

        K.text(f"Ztráty jsou vztaženy k napínacímu napětí σ_p,max příslušného kabelu, čas t = {fmt(f.t, 0)} dní "
               f"({f.nazev.lower()}). Dlouhodobá ztráta podle (5.46) je rozdělena na složky podle členů čitatele "
               "(ε_cs·E_p, 0,8·Δσ_pr, α_p·Σφ·σ_c) dělených společným jmenovatelem; záporná hodnota znamená "
               "přírůstek napětí. Řádek „Celkem“ je průměr vážený plochou předpínací výztuže "
               f"(odpovídá úbytku předpínací síly). Řez ve středu rozpětí x = {fmt(self.x[im], 3)} m:")
        rows = []
        for k, r in zip(self.kabely, roz):
            rows.append([k.nazev, fmt(r["sigma_max"], 1)] + [fmt(100 * r[kl] / r["sigma_max"], 1) for kl in klice]
                        + [fmt(r["sigma_konec"], 1)])
        s_kon = sum(r["sigma_konec"] * a for r, a in zip(roz, Ap)) / Ap.sum()
        rows.append(["Celkem", fmt(smaxAp / Ap.sum(), 1)] + [fmt(100 * celk[kl], 1) for kl in klice]
                    + [fmt(s_kon, 1)])
        K.tabulka(["Kabel", "σ_p,max [MPa]"] + [f"{n} [%]" for n, _ in sloupce]
                  + ["okamžité [%]", "dlouhodobé [%]", "celkem [%]", "σ_p,∞ [MPa]"], rows,
                  "Ztráty předpětí na konci životnosti ve středu rozpětí [% σ_p,max]", souhrn=True)

        # celková ztráta po délce (řezy mezi podporami)
        idx = [i for i in self.i_tab if self.v_poli[i]]
        rows = []
        for j, k in enumerate(self.kabely):
            rows.append([k.nazev] + [fmt(100 * (k.sigma_max - float(f.sigma[j][i])) / k.sigma_max, 1) for i in idx])
        tot = []
        for i in idx:
            sm = sum(k.sigma_max * a for k, a in zip(self.kabely, Ap))
            sk = sum(float(f.sigma[j][i]) * a for j, a in enumerate(Ap))
            tot.append(fmt(100 * (sm - sk) / sm, 1))
        rows.append(["Celkem"] + tot)
        K.tabulka(["Kabel"] + [f"x = {fmt(self.x[i], 3)} m" for i in idx], rows,
                  "Celková ztráta předpětí na konci životnosti po délce nosníku [% σ_p,max]", souhrn=True)
        if self.predem:
            K.text("V kotevní oblasti předem předpjatých lan obsahuje celková ztráta i nepřenesenou část předpětí "
                   "(lineární náběh na délce přenosu l_pt1).")

    def _dlouhodobe(self, t: float):
        """Napětí v kabelech po dlouhodobých ztrátách v čase t (5.46 se superpozicí dotvarování)."""
        b, p, P = self.beton, self.predp, self.prurez
        h0 = P.h0
        x = self.x
        eps = reologie.eps_cs(b, self.RH, h0, t, self.t_s) - reologie.eps_cs(b, self.RH, h0, self.t0, self.t_s)
        phi0 = self._phi(t, self.t0, first=True)
        Psum = sum(s * k.Ap for s, k in zip(self.sig_pm0, self.kabely))
        zres = sum(s * k.Ap * z for s, k, z in zip(self.sig_pm0, self.kabely, self.zk)) / np.where(Psum > 0, Psum, 1)
        zcp = P.zt - zres
        # 5.10.6(1): relaxace se stanoví pro napětí σ_p(G + P_m0 + ψ2·Q) – k σ_pm0 (obsahuje už g0)
        # se přičte přírůstek od vnějších kvazistálých zatížení vnesených do času t (soudržné kabely)
        M_ext = sum((Mk for t_k, _, _, Mk in self.kroky_dotv if t_k <= t), np.zeros_like(x))
        alfa_e = p.Ep / b.Ecm
        sigs, det = [], []
        for ik, (k, s_pm0) in enumerate(zip(self.kabely, self.sig_pm0)):
            ds_G = alfa_e * self._napeti(self.zk[ik], 0.0, 0.0, 0.0, M_ext)
            if self.predem:
                # po uvolnění lan klesne napětí na σ_pm0 → kapacita relaxace se přepočte pro fiktivní napětí
                # σ_p + Δσ_pr,proběhlá s ekvivalentním časem t_e (EN 1992-1-1 příl. D, Navrátil 4.5.3)
                cor = float(p.relaxace(k.sigma_max, self.t_rel_h))
                fr = self._faktor_prenosu()
                s_plne = np.where(fr > 1e-9, s_pm0 / np.where(fr > 1e-9, fr, 1.0), k.sigma_max - cor)
                s_rel = np.maximum(s_plne + ds_G, 1.0)
                s_f = s_rel + cor
                t_e = np.where(cor > 0, p.cas_relaxace(s_f, cor / s_f), 0.0)
                t_h_tot = np.minimum(t_e + (t - self.t0) * 24.0, self.n.relaxace_t_max_h)
                d_pr = p.relaxace(s_f, t_h_tot) - cor
            else:
                t_max = self.n.relaxace_t_max_h
                s_rel = np.maximum(s_pm0 + ds_G, 1.0)
                # relaxace proběhlá při podržení na lisu (poměrná ρ) → ekvivalentní čas při napětí s_rel
                rho = self.rho_drzeni[ik]
                t_e = np.where(rho > 0, p.cas_relaxace(s_rel, rho), 0.0)
                d_pr = (p.relaxace(s_rel, np.minimum(t_e + (t - self.t0) * 24.0, t_max))
                        - p.relaxace(s_rel, np.minimum(t_e, t_max)))
            d_pr = np.maximum(d_pr, 0.0) * np.ones_like(x)
            creep = np.zeros_like(x)
            for t_k, _, sk, _ in self.kroky_dotv:
                if t_k <= t:
                    creep += self._phi(t, t_k, first=(t_k == self.t0)) * sk[ik]
            loss, mezi = ztrata_dlouhodoba_546(eps, p.Ep, d_pr, b.Ecm, phi0, 0.0, self.Ap, P.A, P.I,
                                               zcp, creep_term=creep)
            if self.predem:
                loss = loss * self._faktor_prenosu()
            sigs.append(s_pm0 - loss)
            det.append(dict(d_pr=d_pr, creep=creep, loss=loss, mezi=mezi, zcp=zcp, ds_G=ds_G, s_rel=s_rel))
        return sigs, det, eps, phi0, zcp, zres

    def _phi(self, t: float, tk: float, first: bool = False) -> float:
        if t <= tk:
            return 0.0
        ph = reologie.phi(self.beton, self.RH, self.prurez.h0, t, tk)
        if first and self.k_sigma0 > 0.45:
            ph *= math.exp(1.5 * (self.k_sigma0 - 0.45))
        return ph

    # ------------------------------------------------------------------
    def _vnitrni_sily(self):
        n = len(self.x)
        nn = self.n
        K = self.protokol.kapitola("Vnitřní síly")
        if self.rezim_kombinace:
            K.text("Vnitřní síly od vnějšího zatížení jsou převzaty ze zadaných kombinací; vlastní tíha nosníku "
                   "g0 je přičtena programem. Před uvedením do provozu působí (od času vnesení) kvazistálá "
                   "kombinace jako stálé zatížení.")
        else:
            K.text("Vnitřní síly od zatížení jsou spočteny na prostém nosníku pomocí příčinkových čar. Kombinace "
                   "podle ČSN EN 1990 (6.14b) charakteristická, (6.15b) častá, (6.16b) kvazistálá a pro MSÚ "
                   + ("(6.10a) a (6.10b)" if nn.kombinace_msu == "6.10ab" else "(6.10)") + ".")
        K.text("Vnitřní síly od předpětí (staticky určitá konstrukce – pouze primární účinky): "
               "N_P = −ΣP_i·cos α_i, M_P = ΣP_i·cos α_i·(z_i − z_t), V_P = ΣP_i·sin α_i.")
        self.komb = {}
        if self.rezim_kombinace:
            self._komb_ze_vstupu()
        for f in self.faze:
            if self.rezim_kombinace:
                break
            prom = self.promenne if f.provoz else []
            stale_po = [z for z in f.stale if z is not self.zs_g0]
            d = {}
            for druh in ("char", "casta", "kvazistala"):
                d[druh] = kombinace(stale_po, prom, druh, n)
            d["msu"] = kombinace(f.stale, prom, "msu", n, nn.gamma_G, nn.gamma_G_inf, nn.xi, nn.kombinace_msu)
            d["vse_char"] = kombinace(f.stale, prom, "char", n)
            self.komb[f.nazev] = d
        fz = self.faze[-1]
        d = self.komb[fz.nazev]
        NP, MP, VP = self._sily_predpeti(fz.sigma, fz.k_Ap)
        rows = []
        for i in self.i_tab:
            rows.append([fmt(self.x[i], 3), fmt(self.zs_g0.M_max[i]),
                         fmt(d["vse_char"].M_max[i]), fmt(d["casta"].M_max[i] + self.zs_g0.M_max[i]),
                         fmt(d["kvazistala"].M_max[i] + self.zs_g0.M_max[i]), fmt(d["msu"].M_max[i]),
                         fmt(d["msu"].V_max[i]), fmt(d["msu"].V_min[i]), fmt(MP[i]), fmt(VP[i])])
        K.tabulka(["x [m]", "M_g0", "M_char", "M_častá", "M_kvazist.", "M_Ed", "V_Ed,max", "V_Ed,min",
                   "M_P,∞", "V_P,∞"], rows,
                  f"Vnitřní síly [kNm, kN] – fáze {fz.nazev} (kombinace bez předpětí; M_P,∞ a V_P,∞ od předpětí)")
        K.obrazek("vnitrni_sily", "Průběhy ohybových momentů a posouvajících sil")

    def _komb_ze_vstupu(self):
        """Obálky kombinací pro jednotlivé fáze z přímo zadaných kombinací."""
        nn = self.n
        g = self.zs_g0
        G = Obalka(g.M_max, g.M_max, g.V_max, g.V_max)
        nula = Obalka.nula(len(self.x))

        def s_g0(o: Obalka, f_sup: float) -> Obalka:
            a = np.stack([f_sup * G.M_max, nn.gamma_G_inf * G.M_max])
            v = np.stack([f_sup * G.V_max, nn.gamma_G_inf * G.V_max])
            return Obalka(o.M_max + a.max(0), o.M_min + a.min(0), o.V_max + v.max(0), o.V_min + v.min(0))

        for f in self.faze:
            d = {}
            if f.provoz:
                for druh in ("char", "casta", "kvazistala"):
                    d[druh] = self.kv[druh]
                msu = []
                for druh, fac in (("6.10a", nn.gamma_G), ("6.10", nn.gamma_G), ("6.10b", nn.xi * nn.gamma_G)):
                    if druh in self.kv:
                        msu.append(s_g0(self.kv[druh], fac))
                d["msu"] = Obalka.max_z(msu)
            else:
                ext = self.kv["kvazistala"] if f.t >= self.t_vneseni else nula
                for druh in ("char", "casta", "kvazistala"):
                    d[druh] = ext
                d["msu"] = s_g0(Obalka(nn.gamma_G * ext.M_max, nn.gamma_G * ext.M_min, nn.gamma_G * ext.V_max,
                                       nn.gamma_G * ext.V_min), nn.gamma_G)
            d["vse_char"] = d["char"] + G
            self.komb[f.nazev] = d

    def _M_trvale(self, t: float) -> np.ndarray:
        """Dlouhodobě působící vnější moment (bez g0) v čase t – součet zatěžovacích kroků."""
        return sum((M for t_k, _, _, M in self.kroky_dotv if t_k <= t), np.zeros_like(self.x))

    # ------------------------------------------------------------------
    def _mez_tahu(self, druh: str, t: float) -> float:
        b = self.beton
        if druh == "fctm":
            return b.fctm_t(t)
        if druh == "fctk005":
            return b.fctk005_t(t)
        return 0.0

    def _msp(self):
        x, b, nn, p = self.x, self.beton, self.n, self.predp
        K = self.protokol.kapitola("Mezní stavy použitelnosti")
        K.text("Normálová napětí jsou počítána pružně na neporušeném průřezu (tah +, tlak −). Předpětí "
               f"se uvažuje charakteristickými hodnotami P_k,sup = r_sup·P_m,t a P_k,inf = r_inf·P_m,t "
               f"(r_sup = {fmt(nn.r_sup)}, r_inf = {fmt(nn.r_inf)}, čl. 5.10.9); rozhodující hodnota "
               "je použita pro každé kritérium.")
        if self.kategorie:
            dek, trh, wm = KRITERIA_KATEGORIE[self.kategorie]
            zz = self._zivotnost_klic()
            K.text(f"Kategorie mostu {self.kategorie} (ČSN 73 6222, tab. 12.3: informativní zbytková životnost "
                   f"{ZBYTKOVA_ZIVOTNOST[zz][0]} – {zz.replace('-', ' až ')} let, "
                   f"{'předem předpjatý' if self.predem else 'dodatečně předpjatý se soudržnou výztuží'} most). "
                   "Návrhová kritéria podle tab. 12.4: dekomprese – "
                   + (f"kombinace {NAZVY_KOMBINACI[dek]}" if dek != "zadna" else "neověřuje se")
                   + f"; šířka trhlin – kombinace {NAZVY_KOMBINACI[trh]}, w_max = {fmt(wm, 1)} mm. Tahové "
                   "napětí v provozních fázích se proto uvádí jen informativně (kritériem jsou dekomprese a "
                   "šířka trhlin).")
        Mg0 = self.zs_g0.M_max
        h = self.prurez.h
        self.msp_napeti = {}
        for f in self.faze:
            Kf = self.protokol.kapitola(f"Napětí v betonu – {f.nazev_t}", 2)
            NP, MP, _ = self._sily_predpeti(f.sigma, f.k_Ap)
            if f.k_Ap < 1.0:
                Kf.text(f"Předpínací síla je zmenšena oslabením předpínací výztuže korozí "
                        f"({fmt(self.oslabeni['Ap'], 1)} %).")
            d = self.komb[f.nazev]
            fck_t = b.fck_t(f.t)
            if not f.provoz:
                kombinace_list = [("stala", d["char"])]
                lim_t = self._mez_tahu(nn.tah_predpeti, f.t)
                k_tl = nn.k_predpeti if f is self.faze[0] else nn.k1
            else:
                kombinace_list = [("char", d["char"]), ("casta", d["casta"]), ("kvazistala", d["kvazistala"])]
                lim_t = self._mez_tahu(nn.tah_provoz, f.t)
                k_tl = nn.k1
            lim_c = k_tl * fck_t
            lim_qp = nn.k2 * fck_t
            Kf.krok("Mez tlakového napětí", f"{fmt(k_tl)}·f_{{ck}}(t)", f"{fmt(k_tl)}·{fmt(fck_t)}", lim_c, "MPa",
                    "5.10.2.2(5)" if f is self.faze[0] else "7.2(2)")
            Kf.krok("Mez tahového napětí", "f_{ctm}(t)" if (nn.tah_provoz if f.provoz else nn.tah_predpeti) == "fctm"
                    else "f_{ctk,0,05}(t)", "", lim_t, "MPa")
            res = {}
            for druh, ob in kombinace_list:
                out = {}
                for r_naz, r in (("sup", nn.r_sup), ("inf", nn.r_inf)):
                    for mm, Mx in (("max", ob.M_max), ("min", ob.M_min)):
                        sh = self._napeti(h, NP, MP, Mg0, Mx, r)
                        sd = self._napeti(0.0, NP, MP, Mg0, Mx, r)
                        out[(r_naz, mm)] = (sh, sd)
                res[druh] = out
            self.msp_napeti[f.nazev] = res
            # tabulka – charakteristická / stálá, obálka
            hlavni = "stala" if not f.provoz else "char"
            env_h_min = np.min([v[0] for v in res[hlavni].values()], 0)
            env_h_max = np.max([v[0] for v in res[hlavni].values()], 0)
            env_d_min = np.min([v[1] for v in res[hlavni].values()], 0)
            env_d_max = np.max([v[1] for v in res[hlavni].values()], 0)
            rows = []
            for i in self.i_tab:
                rows.append([fmt(x[i], 3), fmt(-NP[i]), fmt(MP[i]), fmt(env_h_min[i], 2), fmt(env_h_max[i], 2),
                             fmt(env_d_min[i], 2), fmt(env_d_max[i], 2)])
            Kf.tabulka(["x [m]", "P_m,t [kN]", "M_P [kNm]", "σ_h,min", "σ_h,max", "σ_d,min", "σ_d,max"], rows,
                       f"Napětí v krajních vláknech [MPa] – kombinace {NAZVY_KOMBINACI[hlavni]} (obálka P_sup/P_inf)")
            # podrobný výpočet ve středu rozpětí
            i = self.im
            sP = self.secP[i]
            sG = self.secG[i]
            sL = self.secL[i]
            Mx = d["char"].M_max[i]
            Kf.text(f"Podrobně – střed rozpětí x = {fmt(x[i], 3)} m, předpětí P_m,t = {fmt(-NP[i])} kN, "
                    f"M_P = {fmt(MP[i])} kNm, M_g0 = {fmt(Mg0[i])} kNm, M_ostatní = {fmt(Mx)} kNm:")
            for r_naz, r in (("sup", nn.r_sup), ("inf", nn.r_inf)):
                for zz, naz in ((h, "horní"), (0.0, "dolní")):
                    val = float(self._napeti(zz, NP[i], MP[i], Mg0[i], Mx, r, idx=i))
                    Kf.krok(f"σ – {naz} vlákna, P_{r_naz}",
                            "σ = r·(N_{P}/A + M_{P}·(z_{t} − z)/I) + M_{g0}·(z_{t,g} − z)/I_{g} + M_{ost}·(z_{t,L} − z)/I_{L}",
                            f"{fmt(r)}·({fmt(NP[i])}·10^{{3}}/{fmt(sP[0])} + {fmt(MP[i])}·10^{{6}}·({fmt(sP[1])} − {fmt(zz)})/{fmt(sP[2])})"
                            f" + {fmt(Mg0[i])}·10^{{6}}·({fmt(sG[1])} − {fmt(zz)})/{fmt(sG[2])}"
                            f" + {fmt(Mx)}·10^{{6}}·({fmt(sL[1])} − {fmt(zz)})/{fmt(sL[2])}",
                            val, "MPa")
            # posudky
            fz = f.nazev
            for druh, out in res.items():
                nazk = NAZVY_KOMBINACI[druh]
                vals_min = np.min([np.minimum(a, c) for a, c in out.values()], 0)
                vals_max = np.max([np.maximum(a, c) for a, c in out.values()], 0)
                if druh in ("stala", "char"):
                    i = int(np.argmin(vals_min))
                    self.protokol.pridej_posudek(Kf, VysledekPosudku(
                        "Tlakové napětí v betonu", "MSP", -float(vals_min[i]), lim_c, "MPa",
                        max(-float(vals_min[i]), 0) / lim_c, fz, nazk, float(x[i]),
                        odkaz="5.10.2.2(5)" if f is self.faze[0] else "7.2(2)", skupina="Napětí v betonu"))
                    i = int(np.argmax(vals_max))
                    if f.provoz and self.kategorie:
                        Kf.krok(f"Největší tahové napětí – {nazk} (x = {fmt(x[i], 3)} m, informativně)", "σ_{ct}",
                                "", float(vals_max[i]), "MPa")
                        continue
                    self.protokol.pridej_posudek(Kf, VysledekPosudku(
                        "Tahové napětí v betonu", "MSP", float(vals_max[i]), lim_t, "MPa",
                        max(float(vals_max[i]), 0) / lim_t if lim_t > 0 else (0 if vals_max[i] <= 0 else math.inf),
                        fz, nazk, float(x[i]), poznamka="předpoklad neporušeného průřezu",
                        skupina="Napětí v betonu"))
                if druh == "kvazistala" or (druh == "stala" and f is not self.faze[0]):
                    # 7.2(3): mez lineárního dotvarování – není mezní stav, při překročení upozornění
                    i = int(np.argmin(vals_min))
                    sc = max(-float(vals_min[i]), 0.0)
                    Kf.krok(f"Tlak vůči mezi lineárního dotvarování – {nazk} (x = {fmt(x[i], 3)} m)",
                            "|σ_{c}|/(k_{2}·f_{ck}(t)) ≤ 1", f"{fmt(sc)}/({fmt(nn.k2)}·{fmt(fck_t)})",
                            sc / lim_qp, "", "7.2(3)")
                    if sc > lim_qp:
                        self.protokol.upozorni(Kf, (
                            f"{fz}, kombinace {nazk}: tlakové napětí v betonu |σc| = {fmt(sc)} MPa "
                            f"(x = {fmt(x[i], 3)} m) překračuje mez lineárního dotvarování k2·fck(t) = "
                            f"{fmt(nn.k2)}·{fmt(fck_t)} = {fmt(lim_qp)} MPa (7.2(3)) – je třeba uvažovat "
                            "nelineární dotvarování (3.1.4(4)). Ztráty předpětí a průhyb jsou spočteny "
                            "s lineárním dotvarováním (nelineární jen od předpětí při vnesení, k_σ > 0,45)."))
            # dekomprese
            if f.provoz and nn.dekomprese != "zadna":
                druh = "casta" if nn.dekomprese == "casta" else "kvazistala"
                ob = d[druh]
                eta, info = self._dekomprese(NP, MP, Mg0, ob)
                i = int(np.argmax(eta))
                self.protokol.pridej_posudek(Kf, VysledekPosudku(
                    "Dekomprese", "MSP", float(info["sE"][i]), float(info["sP"][i]), "MPa", float(eta[i]), fz,
                    NAZVY_KOMBINACI[druh], float(x[i]),
                    poznamka=f"vlákno z = {fmt(info['z'][i])} mm; E_d = napětí od zatížení, R_d = |tlak od P_inf|",
                    odkaz="7.3.1, tab. 7.1N", skupina="Dekomprese"))
            # šířka trhlin (7.3.4; ČSN 73 6222, tab. 12.4)
            if f.provoz and nn.trhliny != "zadna":
                self._sirka_trhlin(Kf, f, NP, MP, Mg0, nn.trhliny)
            # napětí v předpínací výztuži v provozu
            if f.provoz:
                ob = d["char"]
                lim = nn.k5 * p.fpk
                worst = (0.0, 0, "")
                for k, s, z in zip(self.kabely, f.sigma, self.zk):
                    ztL, IL = self.secL[:, 1], self.secL[:, 2]
                    ds = p.Ep / b.Ecm * ob.M_max * 1e6 * (ztL - z) / IL
                    sp = s + np.maximum(ds, 0)
                    i = int(np.argmax(sp))
                    if sp[i] > worst[0]:
                        worst = (float(sp[i]), i, k.nazev)
                self.protokol.pridej_posudek(Kf, VysledekPosudku(
                    "Napětí v předpínací výztuži", "MSP", worst[0], lim, "MPa", worst[0] / lim, fz,
                    "charakteristická", float(x[worst[1]]), poznamka=f"kabel {worst[2]}", odkaz="7.2(5)",
                    skupina="Napětí v předpínací výztuži"))
            Kf.obrazek(f"napeti_{self.faze.index(f)}", f"Napětí v krajních vláknech po délce – {f.nazev}")
        K2 = self.protokol.kapitola("Rozdělení napětí po výšce průřezu", 2)
        K2.obrazek("napeti_profil", "Rozdělení normálových napětí ve středu rozpětí v jednotlivých fázích")

    def _zivotnost_klic(self) -> str:
        return str(self.n.zbytkova_zivotnost).strip().replace(" až ", "-").replace("–", "-").replace(" ", "")

    def _vrstvy_trhliny(self, f: Faze, i: int, NP, MP, r: float) -> list[Vrstva]:
        """Výztuž pro průřez s trhlinou v řezu i: kabely s ε_p0 = r·σ_pm,t/E_p − σ_c,P(z_p)/E_cm."""
        b, p = self.beton, self.predp
        vr = []
        for k, s, z in zip(self.kabely, f.sigma, self.zk):
            sc = float(self._napeti(z[i], NP[i], MP[i], 0.0, 0.0, r, idx=i))
            vr.append(Vrstva(float(z[i]), k.Ap * f.k_Ap, p.Ep, r * float(s[i]) / p.Ep - sc / b.Ecm, True,
                             nazev=k.nazev))
        for v in self.vyztuz:
            vr.append(Vrstva(v.z, v.As * f.k_As, self.betonarska.Es, phi=v.phi, nazev=v.nazev or "výztuž"))
        return vr

    def _sirka_trhlin(self, Kf: Kapitola, f: Faze, NP, MP, Mg0, druh: str):
        """Posudek šířky trhlin: neporušený průřez při σ_ct ≤ f_ctm(t), jinak 7.3.4 na průřezu s trhlinou."""
        b, nn, p = self.beton, self.n, self.predp
        ob = self.komb[f.nazev][druh]
        h, x = self.prurez.h, self.x
        fct = b.fctm_t(f.t)
        xi = nn.xi_p if nn.xi_p else xi_predpinaci(self.predem, p.druh, b.fck)
        nazk = NAZVY_KOMBINACI[druh]
        nej = None            # (výsledek, i, r_naz, σ_ct)
        s_max = (-math.inf, 0)
        nenalezeno = []
        for i in range(len(x)):
            for r_naz, r in (("sup", nn.r_sup), ("inf", nn.r_inf)):
                for strana, Mx, zz in ((1, ob.M_max[i], 0.0), (-1, ob.M_min[i], h)):
                    s_un = float(self._napeti(zz, NP[i], MP[i], Mg0[i], Mx, r, idx=i))
                    if s_un > s_max[0]:
                        s_max = (s_un, i)
                    if s_un <= fct:
                        continue
                    vys = sirka_trhliny(self.prurez, b.Ecm, fct, self._vrstvy_trhliny(f, i, NP, MP, r),
                                        float(Mg0[i] + Mx), xi, strana)
                    if vys is None:
                        nenalezeno.append(float(x[i]))
                    elif nej is None or vys.w > nej[0].w:
                        nej = (vys, i, r_naz, s_un)
        odkaz = "7.3.4" + (", ČSN 73 6222 tab. 12.4" if self.kategorie else "")
        Kf.text(f"<b>Šířka trhlin</b> – kombinace {nazk}, w_max = {fmt(nn.w_max, 2)} mm"
                + (f" (kategorie mostu {self.kategorie}, ČSN 73 6222, tab. 12.4)" if self.kategorie else "")
                + ". Průřez je bez trhlin, nepřekročí-li tahové napětí na neporušeném průřezu f_ct,eff = "
                  f"f_ctm(t) = {fmt(fct)} MPa; jinak se šířka trhliny počítá podle 7.3.4 na pružném průřezu "
                  "s trhlinou (beton v tahu nepůsobí, předpínací výztuž s počátečním přetvořením "
                  "ε_p0 = r·σ_pm,t/E_p − σ_c,P(z_p)/E_cm), k_t = 0,4, ξ1 = √ξ, "
                  f"ξ = {fmt(xi, 2)} (tab. 6.2).")
        if nenalezeno:
            Kf.text(f"Upozornění: v řezech x = {', '.join(fmt(v, 2) for v in sorted(set(nenalezeno)))} m "
                    "nebyl nalezen rovnovážný stav průřezu s trhlinou – šířka trhlin zde není spočtena.")
        if nej is None:
            i = s_max[1]
            Kf.krok(f"Největší tahové napětí na neporušeném průřezu (x = {fmt(x[i], 3)} m)",
                    "σ_{ct} ≤ f_{ct,eff}", f"{fmt(s_max[0])} ≤ {fmt(fct)}", s_max[0], "MPa", "7.3.2(4)")
            self.protokol.pridej_posudek(Kf, VysledekPosudku(
                "Šířka trhlin", "MSP", 0.0, nn.w_max, "mm", 0.0, f.nazev, nazk, float(x[i]),
                poznamka=f"bez trhlin: σ_ct = {fmt(s_max[0])} ≤ f_ctm = {fmt(fct)} MPa",
                odkaz=odkaz, skupina="Trhliny"))
            return
        v, i, r_naz, s_un = nej
        okraj = "dolní" if v.strana > 0 else "horní"
        Kf.text(f"Rozhodující řez x = {fmt(x[i], 3)} m, {okraj} okraj, předpětí P_{r_naz}:")
        Kf.krok("Tahové napětí na neporušeném průřezu", "σ_{ct} > f_{ct,eff}", f"{fmt(s_un)} > {fmt(fct)}",
                s_un, "MPa", "7.3.2(4)")
        Kf.krok("Moment", "M = M_{g0} + M_{ost}", f"{fmt(float(Mg0[i]))} + {fmt(v.M - float(Mg0[i]))}", v.M, "kNm")
        Kf.krok("Výška tlačené oblasti průřezu s trhlinou", "x", "iterace ΣN = 0, ΣM = M", v.x, "mm")
        Kf.krok("Napětí v tlačeném okraji", "σ_{c}", "", v.sigma_c, "MPa")
        if v.vyztuz_s == "betonářská":
            Kf.krok("Napětí v tažené betonářské výztuži", "σ_{s}", "", v.sigma_s, "MPa", "7.3.4(2)")
        else:
            Kf.krok("Přírůstek napětí v předpínací výztuži od dekomprese", "Δσ_{p}", "", v.sigma_s, "MPa",
                    "7.3.4(2)")
        Kf.krok("Účinná výška taženého betonu", "h_{c,ef} = min(2,5·(h − d); (h − x)/3; h/2)", "", v.h_cef, "mm",
                "7.3.2(3)")
        Kf.krok("Účinná plocha taženého betonu", "A_{c,eff}", "", v.A_ceff, "mm²")
        Kf.krok("Stupeň vyztužení", "ρ_{p,eff} = (A_{s} + ξ_{1}^{2}·A'_{p})/A_{c,eff}",
                f"({fmt(v.As_ef)} + {fmt(v.xi1, 3)}^{{2}}·{fmt(v.Ap_ef)})/{fmt(v.A_ceff)}", v.rho, "", "(7.10)")
        Kf.krok("Rozdíl průměrných přetvoření", "ε_{sm} − ε_{cm} = max([σ_{s} − k_{t}·f_{ct,eff}/ρ_{p,eff}·"
                "(1 + α_{e}·ρ_{p,eff})]/E_{s}; 0,6·σ_{s}/E_{s})", f"E_s = {fmt(v.E_s)} MPa, α_e = "
                f"{fmt(v.E_s / b.Ecm, 2)} → {v.deps_vzorec}", v.deps * 1e3, "‰", "(7.9)")
        if v.s_r_vzorec == "(7.11)":
            Kf.krok("Maximální vzdálenost trhlin", "s_{r,max} = k_{3}·c + k_{1}·k_{2}·k_{4}·φ/ρ_{p,eff}",
                    f"3,4·{fmt(v.c)} + 0,8·0,5·0,425·{fmt(v.phi)}/{fmt(v.rho, 4)}", v.s_r, "mm", "(7.11)")
        else:
            Kf.krok("Maximální vzdálenost trhlin (v A_c,eff není betonářská výztuž o zadaném průměru)",
                    "s_{r,max} = 1,3·(h − x)", f"1,3·({fmt(h)} − {fmt(v.x)})", v.s_r, "mm", "(7.14)")
        Kf.krok("Šířka trhliny", "w_{k} = s_{r,max}·(ε_{sm} − ε_{cm})",
                f"{fmt(v.s_r)}·{fmt(v.deps * 1e3)}·10^{{−3}}", v.w, "mm", "(7.8)")
        self.protokol.pridej_posudek(Kf, VysledekPosudku(
            "Šířka trhlin", "MSP", v.w, nn.w_max, "mm", v.w / nn.w_max, f.nazev, nazk, float(x[i]),
            poznamka=f"{okraj} okraj, P_{r_naz}, s_r,max {v.s_r_vzorec}", odkaz=odkaz, skupina="Trhliny"))

    def _dekomprese(self, NP, MP, Mg0, ob: Obalka):
        """Využití z hlediska dekomprese: η = σ_od zatížení / |σ_od předpětí| v rozhodujícím vláknu."""
        nn = self.n
        h = self.prurez.h
        if nn.dekomprese_rezim == "kabel":
            zmin = np.min(self.zk, 0) - nn.a_dek
            zmax = np.max(self.zk, 0) + nn.a_dek
            zd = np.clip(zmin, 0, h)
            zh = np.clip(zmax, 0, h)
        else:
            zd = np.zeros_like(self.x)
            zh = np.full_like(self.x, h)
        best = np.zeros_like(self.x)
        sE_b = np.zeros_like(self.x)
        sP_b = np.zeros_like(self.x)
        z_b = np.zeros_like(self.x)
        for z, Mx in ((zd, ob.M_max), (zh, ob.M_min)):
            sP = self._napeti(z, NP, MP, 0.0, 0.0, nn.r_inf)
            sE = self._napeti(z, 0.0, 0.0, Mg0, Mx)
            # vlákno tlačené předpětím: η = σ_E/|σ_P|; jinak η = 1 + σ/f_ctm (> 1, pokud je vlákno v tahu)
            eta = np.where(sP < 0, np.maximum(sE, 0) / np.where(sP < 0, -sP, 1),
                           np.where(sP + sE > 0, 1.0 + (sP + sE) / self.beton.fctm, 0.0))
            m = eta > best
            best = np.where(m, eta, best)
            sE_b = np.where(m, sE, sE_b)
            sP_b = np.where(m, -sP, sP_b)
            z_b = np.where(m, z, z_b)
        return best, dict(sE=sE_b, sP=sP_b, z=z_b)

    # ------------------------------------------------------------------
    def _hlavni_napeti(self):
        b, nn = self.beton, self.n
        P = self.prurez
        K = self.protokol.kapitola("Hlavní napětí v betonu", 2)
        K.text("Hlavní tahová napětí se ověřují v neporušených oblastech podle ČSN EN 1992-2 (příloha QQ, 12.6.3): "
               "σ_1 ≤ f_ctb = (1 − 0,8·σ_3/f_ck)·f_ctk,0,05. Smyková napětí τ = V·S(z)/(I·b(z)), V zahrnuje "
               "posouvající sílu od předpětí. Kombinace charakteristická; vyhodnocení ve stojině průřezu.")
        zz = np.linspace(0.02 * P.h, 0.98 * P.h, 49)
        bz = P.sirka(zz)
        zz, bz = zz[bz > 1.0], bz[bz > 1.0]
        # vyhodnocení ve stojině (šířka ≤ 1,2·b_min); u plných průřezů v rozsahu 0,1h–0,9h
        stojina = bz <= 1.2 * bz.min()
        if stojina.mean() > 0.9:
            stojina = (zz >= 0.1 * P.h) & (zz <= 0.9 * P.h)
        zz, bz = zz[stojina], bz[stojina]
        Sz = P.staticky_moment(zz)
        # hustá síť po celé výšce se zdvojenými body u zlomů šířky (skoky τ na rozhraní stojina/pásnice)
        zl = np.unique(np.concatenate([P.obrys[:, 1]] + [o[:, 1] for o in P.otvory]))
        zl = zl[(zl > 0) & (zl < P.h)]
        zf = np.unique(np.concatenate([np.linspace(0, P.h, 121), zl - 0.01, zl + 0.01]))
        Sf = P.staticky_moment(zf)
        Mg0 = self.zs_g0.M_max
        self.hlavni = {}
        for f in self.faze:
            if not f.provoz:
                continue
            NP, MP, VP = self._sily_predpeti(f.sigma, f.k_Ap)
            ob = self.komb[f.nazev]["char"]
            g0V = self.zs_g0.V_max
            best = (0.0, 0, 0, 0.0, 0.0, 0.0)
            prof = None
            eta_x = np.zeros_like(self.x)
            for i in np.nonzero(self.v_poli)[0]:
                IL = self.secL[i, 2]
                for r in (nn.r_sup, nn.r_inf):
                    for Mx, Vx in ((ob.M_max[i], ob.V_max[i]), (ob.M_max[i], ob.V_min[i])):
                        V = Vx + g0V[i] + r * VP[i]
                        tau = V * 1e3 * Sz / (IL * bz)
                        sx = self._napeti(zz, NP[i], MP[i], Mg0[i], Mx, r, idx=i)
                        s1 = sx / 2 + np.sqrt((sx / 2) ** 2 + tau ** 2)
                        s3 = sx / 2 - np.sqrt((sx / 2) ** 2 + tau ** 2)
                        fctb = np.where(s3 < 0, (1 - 0.8 * np.abs(s3) / b.fck) * b.fctk005, b.fctk005)
                        eta = np.where(s1 > 0, s1 / fctb, 0)
                        j = int(np.argmax(eta))
                        eta_x[i] = max(eta_x[i], eta[j])
                        if eta[j] > best[0]:
                            best = (float(eta[j]), i, j, float(s1[j]), float(s3[j]), float(fctb[j]))
                            prof = (NP[i], MP[i], Mg0[i], Mx, V, r)
            eta, i, j, s1, s3, fctb = best
            # průběh po celé výšce průřezu v rozhodujícím řezu (pro graf; posudek jen ve stojině)
            if prof is not None:
                NPi, MPi, Mg0i, Mx, V, r = prof
                bf = P.sirka(zf)
                tf = np.divide(V * 1e3 * Sf, self.secL[i, 2] * bf, out=np.zeros_like(zf), where=bf > 1.0)
                sf = self._napeti(zf, NPi, MPi, Mg0i, Mx, r, idx=i)
                rf = np.sqrt((sf / 2) ** 2 + tf ** 2)
                s3f = sf / 2 - rf
                prof = (sf, tf, sf / 2 + rf, s3f,
                        np.where(s3f < 0, (1 - 0.8 * np.abs(s3f) / b.fck) * b.fctk005, b.fctk005))
            self.hlavni[f.nazev] = dict(z=zf, x=self.x, eta_x=eta_x, i=i, prof=prof,
                                        z_stojina=(float(zz.min()), float(zz.max())), z_rozh=float(zz[j]))
            K.krok(f"{f.nazev}: rozhodující místo", "x; z", "", f"{fmt(self.x[i], 3)} m; {fmt(zz[j])} mm")
            K.krok("Hlavní napětí", "σ_{1,3} = σ_{x}/2 ± √((σ_{x}/2)^{2} + τ^{2})", "", f"{fmt(s1)}; {fmt(s3)}", "MPa")
            K.krok("Směrově závislá pevnost v tahu", "f_{ctb} = (1 − 0,8·|σ_{3}|/f_{ck})·f_{ctk,0,05}",
                   f"(1 − 0,8·{fmt(abs(min(s3, 0)))}/{fmt(b.fck)})·{fmt(b.fctk005)}", fctb, "MPa", "QQ.101")
            self.protokol.pridej_posudek(K, VysledekPosudku(
                "Hlavní tahové napětí", "MSP", s1, fctb, "MPa", eta, f.nazev, "charakteristická", float(self.x[i]),
                poznamka=f"z = {fmt(zz[j])} mm", odkaz="EN 1992-2 QQ", skupina="Hlavní napětí"))
        K.obrazek("hlavni_napeti", "Průběh hlavních napětí po výšce průřezu v rozhodujícím řezu")

    # ------------------------------------------------------------------
    def _pruhyb(self):
        """Průhyb – pružný výpočet s účinným modulem pro dotvarování (dvojitá integrace křivosti)."""
        b, x = self.beton, self.x
        K = self.protokol.kapitola("Průhyb", 2)
        K.text("Průhyb je počítán dvojitou integrací křivosti κ = M/(E·I) mezi ložisky (neporušený průřez). "
               "Vliv dotvarování se zahrnuje součinitelem (1 + φ(t,t_k)) pro každý zatěžovací krok, změna "
               "předpětí od dlouhodobých ztrát s (1 + 0,8·φ). Průhyb dolů je kladný.")
        ia, ib = self.ia, self.ib
        xs = x[ia:ib + 1]
        IL = self.secL[ia:ib + 1, 2]
        IP = self.secP[ia:ib + 1, 2]   # předpětí
        IG = self.secG[ia:ib + 1, 2]   # vlastní tíha při vnesení předpětí

        def w_of(M, E, I=IL):
            k = M[ia:ib + 1] * 1e6 / (E * I)  # 1/mm
            xm = xs * 1000
            th = np.concatenate([[0], np.cumsum(0.5 * (k[1:] + k[:-1]) * np.diff(xm))])
            y = np.concatenate([[0], np.cumsum(0.5 * (th[1:] + th[:-1]) * np.diff(xm))])
            y = y - y[-1] * (xm - xm[0]) / (xm[-1] - xm[0])
            return -y  # dolů kladně

        _, MP0, _ = self._sily_predpeti(self.sig_pm0)
        Mg0 = self.zs_g0.M_max
        Ec0 = b.Ecm_t(self.t0)
        w0 = w_of(MP0, Ec0, IP) + w_of(Mg0, Ec0, IG)
        self.w = {"Vnesení předpětí": w0}
        lim = self.L0 * 1000 / self.n.pruhyb_limit
        imid = self.im - ia
        K.krok("Průhyb při vnesení předpětí (krátkodobý)", "w_{0}", f"E_cm(t0) = {fmt(Ec0)} MPa", float(w0[imid]), "mm")
        for f in self.faze[1:]:
            w = np.zeros_like(xs)
            for t_k, naz, _, Mk in self.kroky_dotv:
                if t_k > f.t:
                    continue
                wk = w_of(MP0, b.Ecm, IP) + w_of(Mg0, b.Ecm, IG) + w_of(Mk, b.Ecm) if t_k == self.t0 else w_of(Mk, b.Ecm)
                w += wk * (1 + self._phi(f.t, t_k, first=(t_k == self.t0)))
            _, MPt, _ = self._sily_predpeti(f.sigma, f.k_Ap)
            w += w_of(MPt - MP0, b.Ecm, IP) * (1 + 0.8 * self._phi(f.t, self.t0))
            self.w[f.nazev] = w
            K.krok(f"Průhyb – kvazistálá kombinace, {f.nazev_t}", "w_{qp}(t)", "", float(w[imid]), "mm")
            if f.provoz:
                wq = w_of(self.komb[f.nazev]["casta"].M_max - self._M_trvale(f.t), b.Ecm)
                self.w[f.nazev + " – častá (krátkodobě od Q)"] = w + wq
                K.krok(f"Přírůstek od proměnného zatížení (častá kombinace), {f.nazev}", "w_{Q,fr}", "",
                       float(wq[imid]), "mm")
        wk = self.w[self.faze[-1].nazev]
        i = int(np.argmax(np.abs(wk)))
        K.krok("Mezní průhyb", f"w_{{lim}} = L_{{0}}/{fmt(self.n.pruhyb_limit, 0)}",
               f"{fmt(self.L0 * 1000)}/{fmt(self.n.pruhyb_limit, 0)}", lim, "mm", "7.4.1(4)")
        self.protokol.pridej_posudek(K, VysledekPosudku(
            "Průhyb (kvazistálá kombinace)", "MSP", float(abs(wk[i])), lim, "mm", float(abs(wk[i])) / lim,
            self.faze[-1].nazev, "kvazistálá", float(xs[i]),
            poznamka="nadvýšení (záporný průhyb) i průhyb", odkaz="7.4.1(4)", skupina="Průhyb"))
        self.w_x = xs
        K.obrazek("pruhyb", "Průhyb nosníku v jednotlivých fázích")

    # ------------------------------------------------------------------
    def _vrstvy_msu(self, f: Faze, i: int, eps0_navic: bool = True, redukce: float = 1.0):
        b, p = self.beton, self.predp
        fr = self._faktor_prenosu(msu=True)[i] if self.predem else 1.0
        NP, MP, _ = self._sily_predpeti(f.sigma, f.k_Ap)
        Mperm = float(self._M_trvale(f.t)[i])
        vrstvy = []
        for k, s, z in zip(self.kabely, f.sigma, self.zk):
            sc = float(self._napeti(z[i], NP[i] * redukce, MP[i] * redukce, self.zs_g0.M_max[i], Mperm, idx=i))
            e0 = s[i] / p.Ep - (sc / b.Ecm if eps0_navic else 0.0)
            vrstvy.append(VrstvaPredpeti(float(z[i]), k.Ap * f.k_Ap * fr * redukce, float(e0), k.nazev))
        return vrstvy

    def _kontrola_eps_ud(self, f: Faze, vrstvy: list[VrstvaPredpeti]):
        """Mezní přetvoření předpínací výztuže (oslabené korozí) musí být větší než počáteční přetvoření."""
        if f.eps_ud_p is None or not vrstvy:
            return
        e0 = max(v.eps0 for v in vrstvy)
        if e0 >= f.eps_ud_p:
            raise ValueError(
                f"Tažnost oslabená korozí ε_uk,red = {fmt(self.predp.taznost_oslabena, 1)} ‰: mezní přetvoření "
                f"ε_ud,red = {fmt(f.eps_ud_p * 1e3)} ‰ nepřesahuje počáteční přetvoření předpínací výztuže "
                f"ε_p0 = {fmt(e0 * 1e3)} ‰ ({f.nazev}) – výztuž by se přetrhla již předpětím.")

    def _msu_ohyb(self):
        b, p, s = self.beton, self.predp, self.betonarska
        K = self.protokol.kapitola("Mezní stav únosnosti")
        K1 = self.protokol.kapitola("Ohybová únosnost", 2)
        K1.text("Moment únosnosti je stanoven metodou mezních přetvoření: rovinnost průřezu, beton v tahu "
                "nepůsobí, beton v tlaku parabola-obdélník (3.17), předpínací výztuž bilineární diagram se "
                "stoupající větví (obr. 3.10), betonářská výztuž obdobně. Předpínací výztuž má počáteční "
                "přetvoření ε_p0 = σ_pm,t/E_p − σ_c,perm(z_p)/E_cm (předpětí + dekomprese betonu od stálých "
                "účinků). Poloha neutrálné osy je určena iteračně z podmínky ΣN = 0, porušení nastane "
                f"dosažením ε_cu2 = {fmt(b.eps_cu2 * 1e3)} ‰ v betonu nebo ε_ud v oceli"
                + (f" (ve fázích s tažností oslabenou korozí ε_ud,red = {fmt(p.eps_ud_red * 1e3)} ‰ "
                   "u předpínací výztuže)." if p.oslabena_taznost else "."))
        self.msu_M = {}
        for f in self.faze:
            if not f.provoz:
                continue
            vyz = [VrstvaVyztuze(v.z, v.As * f.k_As, v.nazev) for v in self.vyztuz]
            MEd = self.komb[f.nazev]["msu"].M_max
            MRd = np.full_like(self.x, np.nan)
            vys = {}
            for i in np.nonzero(self.v_poli)[0]:
                vr = self._vrstvy_msu(f, i)
                self._kontrola_eps_ud(f, vr)
                r = ohybova_unosnost(self.prurez, b, p, s, vr, vyz, eps_ud_p=f.eps_ud_p)
                MRd[i] = r.MRd
                vys[i] = r
            eta = np.where(self.v_poli, np.maximum(MEd, 0) / MRd, 0)
            i = int(np.nanargmax(eta))
            r = vys[i]
            self.msu_M[f.nazev] = dict(MEd=MEd, MRd=MRd, eta=eta, vys=vys, i=i)
            osl = self._popis_oslabeni(f, ("Ap", "As", "taznost"))
            K1.text(f"<b>{f.nazev_t}</b> – rozhodující řez x = {fmt(self.x[i], 3)} m"
                    + (f" (oslabení korozí: {osl})" if osl else "") + ":")
            K1.krok("Návrhový moment", "M_{Ed}", "", float(MEd[i]), "kNm")
            K1.krok("Výška tlačené oblasti", "x", "iterace ΣN = 0", r.x, "mm")
            K1.krok("Přetvoření horních / dolních vláken", "ε_{c,h}; ε_{c,d}", "",
                    f"{fmt(r.eps_horni * 1e3)} ‰; {fmt(r.eps_dolni * 1e3)} ‰")
            K1.krok("Rozhoduje", "", "", r.rozhoduje)
            rows = [[v["nazev"], fmt(v["z"]), fmt(v["Ap"]), fmt(v["eps0"] * 1e3), fmt(v["eps"] * 1e3),
                     fmt(v["sigma"]), fmt(v["F"])] for v in r.vrstvy_p]
            rows += [[v["nazev"] or "výztuž", fmt(v["z"]), fmt(v["As"]), "0", fmt(v["eps"] * 1e3),
                      fmt(v["sigma"]), fmt(v["F"])] for v in r.vrstvy_s]
            rows.append(["beton (tlak)", fmt(r.z_Fc), "–", "–", "–", "–", fmt(r.Fc)])
            K1.tabulka(["Vrstva", "z [mm]", "A [mm²]", "ε0 [‰]", "ε [‰]", "σ [MPa]", "F [kN]"], rows,
                       "Síly v průřezu na mezi únosnosti")
            K1.krok("Rameno vnitřních sil", "z", "", r.rameno, "mm")
            K1.krok("Moment únosnosti", "M_{Rd} = ΣF_{i}·(z_{t} − z_{i})", "", r.MRd, "kNm")
            self.protokol.pridej_posudek(K1, VysledekPosudku(
                "Ohybová únosnost", "MSÚ", float(MEd[i]), float(r.MRd), "kNm", float(eta[i]), f.nazev,
                "MSÚ – základní", float(self.x[i]), odkaz="6.1", skupina="Ohyb"))
            if not r.konvergence:
                K1.text("Upozornění: iterace polohy neutrálné osy nekonvergovala – zkontrolujte vstupy.")
        K1.obrazek("msu_ohyb", "Návrhové momenty a momenty únosnosti po délce nosníku")
        K1.obrazek("msu_pretvoreni", "Přetvoření a napětí v rozhodujícím průřezu na mezi únosnosti")

    # ------------------------------------------------------------------
    def _smykova_vyztuz_v(self, xx: float) -> SmykovaVyztuz:
        for sv in self.smykova:
            od = sv.od if sv.od is not None else -1e9
            do = sv.do if sv.do is not None else 1e9
            if od - 1e-9 <= xx <= do + 1e-9:
                return sv
        return SmykovaVyztuz(0.0, 1.0)

    def _ucinna_vyska_smyk(self) -> tuple[float, str]:
        """Účinná výška d [mm] pro smyk: vzdálenost spodní řady ohybové betonářské výztuže od horního
        okraje; bez betonářské výztuže odhad d = h − 50 mm. Vrací (d, popis)."""
        h = self.prurez.h
        z_v = [v.z for v in self.vyztuz if v.As > 0]
        if z_v:
            return h - min(z_v), f"h − z_{{s,min}} = {fmt(h)} − {fmt(min(z_v))}"
        return h - 50.0, f"h − 50 = {fmt(h)} − 50 (betonářská výztuž nezadána – odhad)"

    def _msu_smyk(self):
        b, nn = self.beton, self.n
        P = self.prurez
        K = self.protokol.kapitola("Smyková únosnost", 2)
        K.text("Smyk podle 6.2: v oblastech bez ohybových trhlin (σ_d ≤ f_ctk,0,05/γ_c v MSÚ) únosnost betonu (6.4) "
               "jako minimum přes úrovně stojiny (6.2.2(2) pozn.), jinak (6.2a,b). Únosnost se smykovou výztuží je "
               "min(V_Rd,s (6.8/6.13); V_Rd,max (6.9/6.14)), celková únosnost V_Rd = max(V_Rd,c; min(V_Rd,s; V_Rd,max)). "
               f"cotg θ je volen v mezích {fmt(nn.cot_theta_min)}–{fmt(nn.cot_theta_max)} pro maximální únosnost. "
               "Účinná výška d je vzdálenost spodní řady ohybové betonářské výztuže od horního okraje (bez "
               "betonářské výztuže odhad d = h − 50 mm), rameno vnitřních sil z = 0,9·d po celé délce. Šířka b_w,nom se v každé "
               "úrovni stojiny zmenšuje o k·Σφ kanálků procházejících touto "
               "úrovní (6.2.3(6)). V_Ed zahrnuje příznivý účinek sklonu kabelů V_P (γ_P = 1,0). Přechod mezi "
               "oblastí bez trhlin a s trhlinami je podle normy nespojitý (jiný model únosnosti betonu).")
        k_d = 0.5 if nn.kanalky == "ocel" else 1.2
        zt = P.zt
        d, d_popis = self._ucinna_vyska_smyk()
        K.krok("Účinná výška pro smyk (po celé délce)", "d", d_popis, d, "mm")
        K.krok("Rameno vnitřních sil (po celé délce)", "z = 0,9·d", f"0,9·{fmt(d)}", 0.9 * d, "mm")
        S_t = float(P.staticky_moment(zt)[0])
        vys_ohyb = {}
        self.msu_V = {}
        for f in self.faze:
            if not f.provoz:
                continue
            ob = self.komb[f.nazev]["msu"]
            NP, MP, VP = self._sily_predpeti(f.sigma, f.k_Ap)
            NP, VP = nn.gamma_P * NP, nn.gamma_P * VP
            MP = nn.gamma_P * MP
            Mg0 = self.zs_g0.M_max
            res = {}
            arr = {k: np.full_like(self.x, np.nan) for k in
                   ("VEd", "VRd", "VRdc", "VRds", "VRdmax", "eta", "eta_max", "dF_eta", "cot", "trhliny", "d",
                    "bw_nom")}
            vys_ohyb = self.msu_M.get(f.nazev, {}).get("vys", {})
            for i in np.nonzero(self.v_poli)[0]:
                cand = [ob.V_max[i] + VP[i], ob.V_min[i] + VP[i]]
                VEd = max(cand, key=abs)
                # tažená výztuž (ρ_l) z rovnováhy na mezi únosnosti v ohybu; d a z = 0,9·d jsou po délce stálé
                ro = vys_ohyb.get(i)
                if ro is not None and ro.konvergence and ro.rameno > 0:
                    A_sl = sum(v["Ap"] for v in ro.vrstvy_p if v["F"] > 0)
                    A_sl += sum(v["As"] for v in ro.vrstvy_s if v["F"] > 0)
                else:
                    A_sl = sum(k.Ap * f.k_Ap for z, k in zip(self.zk, self.kabely) if z[i] < zt)
                    A_sl += sum(v.As * f.k_As for v in self.vyztuz if v.z < zt)
                # šířka stojiny v pásmu mezi tlačeným a taženým pásem, oslabení kanálky v každé úrovni
                zr = np.linspace(max(P.h - d, 0.0), min(P.h - 0.1 * d, P.h), 80)
                b_z = P.sirka(zr)
                phi_z = np.zeros_like(zr)
                if not self.predem:
                    for k, z in zip(self.kabely, self.zk):
                        if k.d_kanalku > 0:
                            v_kanalku = np.abs(zr - z[i]) < k.d_kanalku / 2
                            phi_z += np.where(v_kanalku & (k.d_kanalku > b_z / 8), k.d_kanalku, 0.0)
                bnom_z = b_z - k_d * phi_z
                bw = float(b_z.min())
                bw_nom = float(bnom_z.min())
                # trhliny od ohybu v MSÚ
                sd = float(self._napeti(0.0, NP[i], MP[i], 0.0, ob.M_max[i], idx=i))
                sh = float(self._napeti(P.h, NP[i], MP[i], 0.0, ob.M_min[i], idx=i))
                trhliny = max(sd, sh) > b.fctk005 / b.gamma_c
                al = 1.0
                if self.predem:
                    lx = min(self.x[i], self.L - self.x[i]) * 1000
                    al = min(lx / (1.2 * self.lpt), 1.0)
                # (6.4) jako minimum přes úrovně stojiny se skutečným σ_cp(z) a b_nom(z)
                S_z = P.staticky_moment(zr)
                s_cp = -self._napeti(zr, NP[i], MP[i], 0.0, ob.M_max[i], idx=i)  # tlak kladně
                arg = np.maximum(b.fctd ** 2 + al * s_cp * b.fctd, 0.0)
                with np.errstate(divide="ignore", invalid="ignore"):
                    vz = np.where(S_z > 1e-6 * P.I, P.I * bnom_z / S_z * np.sqrt(arg) * 1e-3, np.inf)
                jz = int(np.argmin(vz))
                urov = dict(V=float(vz[jz]), I=P.I, b=float(bnom_z[jz]), S=float(S_z[jz]), z=float(zr[jz]),
                            sigma_cp=float(s_cp[jz]))
                sv = self._smykova_vyztuz_v(self.x[i])
                if f.k_Asw < 1.0:                       # oslabení smykové výztuže korozí
                    sv = replace(sv, Asw=sv.Asw * f.k_Asw)
                r = smykova_unosnost(b, self.betonarska, abs(VEd), NP[i], self.secL[i, 0], self.secL[i, 2],
                                     S_t, float(P.sirka(zt)[0]), bw, bw_nom, d, A_sl, sv.Asw_s, sv.alpha, trhliny,
                                     nn.cot_theta_min, nn.cot_theta_max, al, vrdc_uroven=urov)
                res[i] = (r, VEd, sv)
                arr["VEd"][i] = abs(VEd)
                arr["VRd"][i] = r.V_Rd
                arr["VRdc"][i] = r.V_Rd_c
                arr["VRds"][i] = r.V_Rd_s
                arr["VRdmax"][i] = r.V_Rd_max
                arr["cot"][i] = r.cot_theta
                arr["trhliny"][i] = float(trhliny)
                arr["d"][i] = d
                arr["bw_nom"][i] = bw_nom
                arr["eta"][i] = abs(VEd) / r.V_Rd if r.V_Rd > 0 else math.inf
                if abs(VEd) > r.V_Rd_c:
                    arr["eta_max"][i] = abs(VEd) / r.V_Rd_max
                else:
                    lim = 0.5 * bw * d * r.nu1 * b.fcd * 1e-3
                    arr["eta_max"][i] = abs(VEd) / lim
                Md = self.msu_M.get(f.nazev)
                if Md is not None and trhliny and abs(VEd) > r.V_Rd_c:
                    zlev = 0.9 * d
                    arr["dF_eta"][i] = (max(ob.M_max[i], 0) * 1e6 / zlev + r.dF_td * 1e3) / (Md["MRd"][i] * 1e6 / zlev)
            self.msu_V[f.nazev] = dict(arr=arr, res=res)
            i = int(np.nanargmax(arr["eta"]))
            r, VEd, sv = res[i]
            osl = self._popis_oslabeni(f, ("Ap", "Asw"))
            K.text(f"<b>{f.nazev_t}</b> – rozhodující řez x = {fmt(self.x[i], 3)} m"
                   + (f" (oslabení korozí: {osl})" if osl else "") + ":")
            K.krok("Návrhová posouvající síla (vč. V_P)", "V_{Ed} = V_{Ed,ext} + V_{P}", "", abs(VEd), "kN")
            K.krok("Napětí od předpětí v těžišti", "σ_{cp} = N_{Ed}/A_{c}", "", r.sigma_cp, "MPa")
            K.krok("Účinná výška; šířka stojiny; nominální šířka", "d; b_{w}; b_{w,nom}", "",
                   f"{fmt(r.d)} mm; {fmt(r.bw)} mm; {fmt(r.bw_nom)} mm")
            if not r.trhliny:
                u = r.mezi["uroven"]
                K.krok("Oblast bez ohybových trhlin – rozhodující úroveň (minimum přes stojinu)", "z", "", u["z"], "mm",
                       "6.2.2(2)")
                K.krok("Únosnost betonu v této úrovni",
                       "V_{Rd,c} = I·b_{nom}(z)/S(z)·√(f_{ctd}^{2} + α_{l}·σ_{cp}(z)·f_{ctd})",
                       f"{fmt(u['I'])}·{fmt(u['b'])}/{fmt(u['S'])}·√({fmt(b.fctd)}^{{2}} + "
                       f"{fmt(r.mezi['alpha_l'])}·{fmt(u['sigma_cp'])}·{fmt(b.fctd)})·10^{{−3}}", r.V_Rd_c, "kN", "(6.4)")
            else:
                K.krok("Oblast s ohybovými trhlinami – únosnost betonu",
                       "V_{Rd,c} = [C_{Rd,c}·k·(100·ρ_{l}·f_{ck})^{1/3} + k_{1}·σ_{cp}]·b_{w}·d",
                       f"[{fmt(0.18 / b.gamma_c)}·{fmt(r.k)}·(100·{fmt(r.rho_l)}·{fmt(b.fck)})^{{1/3}} + 0,15·"
                       f"{fmt(min(r.sigma_cp, 0.2 * b.fcd))}]·{fmt(r.bw)}·{fmt(r.d)}·10^{{−3}}", r.V_Rd_c, "kN", "(6.2)")
            K.krok("Smyková výztuž", "A_{sw}/s", f"{fmt(sv.Asw)}/{fmt(sv.s)}", sv.Asw_s, "mm²/mm")
            K.krok("Součinitel α_cw; redukce ν1; cotg θ", "α_{cw}; ν_{1} = 0,6·(1 − f_{ck}/250); cotg θ", "",
                   f"{fmt(r.alpha_cw)}; {fmt(r.nu1)}; {fmt(r.cot_theta)}", "", "(6.6N), (6.11N)")
            c, Asw_s, fywd = fmt(r.cot_theta), fmt(sv.Asw_s), fmt(r.mezi['fywd'])
            if abs(sv.alpha - 90.0) < 1e-9:             # svislé třmínky (6.8), (6.9)
                K.krok("Únosnost smykové výztuže", "V_{Rd,s} = (A_{sw}/s)·z·f_{ywd}·cotg θ",
                       f"{Asw_s}·{fmt(r.z)}·{fywd}·{c}·10^{{−3}}", r.V_Rd_s, "kN", "(6.8)")
                K.krok("Únosnost tlakové diagonály",
                       "V_{Rd,max} = α_{cw}·b_{w,nom}·z·ν_{1}·f_{cd}/(cotg θ + tg θ)",
                       f"{fmt(r.alpha_cw)}·{fmt(r.bw_nom)}·{fmt(r.z)}·{fmt(r.nu1)}·{fmt(b.fcd)}/({c} + "
                       f"{fmt(1.0 / r.cot_theta)})·10^{{−3}}", r.V_Rd_max, "kN", "(6.9)")
            else:                                       # šikmá smyková výztuž (6.13), (6.14)
                ca, sa = fmt(r.mezi["cot_alpha"]), fmt(math.sin(math.radians(sv.alpha)))
                K.krok("Únosnost smykové výztuže", "V_{Rd,s} = (A_{sw}/s)·z·f_{ywd}·(cotg θ + cotg α)·sin α",
                       f"{Asw_s}·{fmt(r.z)}·{fywd}·({c} + {ca})·{sa}·10^{{−3}}", r.V_Rd_s, "kN", "(6.13)")
                K.krok("Únosnost tlakové diagonály",
                       "V_{Rd,max} = α_{cw}·b_{w,nom}·z·ν_{1}·f_{cd}·(cotg θ + cotg α)/(1 + cotg^{2}θ)",
                       f"{fmt(r.alpha_cw)}·{fmt(r.bw_nom)}·{fmt(r.z)}·{fmt(r.nu1)}·{fmt(b.fcd)}·({c} + {ca})/(1 + "
                       f"{c}^{{2}})·10^{{−3}}", r.V_Rd_max, "kN", "(6.14)")
            K.krok("Smyková únosnost", "V_{Rd} = max(V_{Rd,c}; min(V_{Rd,s}; V_{Rd,max}))",
                   f"max({fmt(r.V_Rd_c)}; min({fmt(r.V_Rd_s)}; {fmt(r.V_Rd_max)}))", r.V_Rd, "kN", "6.2.1")
            self.protokol.pridej_posudek(K, VysledekPosudku(
                "Smyková únosnost", "MSÚ", abs(VEd), r.V_Rd, "kN", float(arr["eta"][i]), f.nazev,
                "MSÚ – základní", float(self.x[i]), poznamka="bez trhlin" if not r.trhliny else "s trhlinami",
                odkaz="6.2", skupina="Smyk"))
            j = int(np.nanargmax(arr["eta_max"]))
            rj = res[j][0]
            self.protokol.pridej_posudek(K, VysledekPosudku(
                "Únosnost tlakové diagonály", "MSÚ", float(arr["VEd"][j]),
                float(arr["VEd"][j] / arr["eta_max"][j]) if arr["eta_max"][j] > 0 else rj.V_Rd_max, "kN",
                float(arr["eta_max"][j]), f.nazev, "MSÚ – základní", float(self.x[j]), odkaz="6.2.2(6), 6.2.3(3)",
                skupina="Smyk"))
            # minimální smyková výztuž
            sv_min = min((self._smykova_vyztuz_v(self.x[i]) for i in np.nonzero(self.v_poli)[0]),
                         key=lambda q: q.Asw_s)
            rho_w = (sv_min.Asw_s * f.k_Asw / (r.bw * math.sin(math.radians(sv_min.alpha)))
                     if r.bw > 0 else 0)
            self.protokol.pridej_posudek(K, VysledekPosudku(
                "Minimální smyková výztuž", "MSÚ", rho_w * 100, r.rho_w_min * 100, "%",
                r.rho_w_min / rho_w if rho_w > 0 else math.inf, f.nazev, "", None,
                poznamka="ρ_w ≥ ρ_w,min = 0,08·√f_ck/f_yk", odkaz="9.2.2(5)", skupina="Smyk"))
            if np.any(np.isfinite(arr["dF_eta"])):
                j = int(np.nanargmax(arr["dF_eta"]))
                self.protokol.pridej_posudek(K, VysledekPosudku(
                    "Ohyb + přídavná tahová síla ΔF_td", "MSÚ", float(arr["dF_eta"][j]), 1.0, "–",
                    float(arr["dF_eta"][j]), f.nazev, "MSÚ – základní", float(self.x[j]),
                    poznamka="(M_Ed/z + ΔF_td)/(M_Rd/z), ΔF_td = 0,5·V_Ed·(cotg θ − cotg α)", odkaz="6.2.3(7)",
                    skupina="Ohyb"))
        K.obrazek("msu_smyk", "Posouvající síly a smykové únosnosti po délce nosníku")

    # ------------------------------------------------------------------
    def _kotveni_lan(self):
        """Kotvení předem předpjatých lan v MSÚ (8.10.2.3) včetně přídavné síly od smyku ΔF_td."""
        b, p, P, nn = self.beton, self.predp, self.prurez, self.n
        K = self.protokol.kapitola("Kotvení předem předpjatých lan v MSÚ", 2)
        K.text("Ověření podle 8.10.2.3 ČSN EN 1992-1-1 (Navrátil, kap. 10.2.2): v průřezech, kde tahové napětí v betonu "
               "v MSÚ překročí f_ctk,0,05, musí kotvení soudržností přenést sílu v lanech. Největší napětí, které "
               "mohou lana ve vzdálenosti l_x od konce nosníku přenést, roste lineárně do σ_pm,t na délce l_pt2 a "
               "dále do f_pd na kotevní délce l_bpd. Požadovaná síla v tažené výztuži je F_td = M_Ed/z + ΔF_td, "
               "ΔF_td = 0,5·V_Ed·(cotg θ − cotg α) se smykovou výztuží, resp. V_Ed·d/z bez ní (a_l = d); "
               "tažená betonářská výztuž se uvažuje silou A_s·f_yd (předpokládá se její zakotvení za podporou).")
        d_l = p.d_lana or 15.7
        lpt2 = 1.2 * self.lpt
        tah = [ik for ik, z in enumerate(self.zk) if z[self.im] < self.secL[self.im, 1]]
        if not tah:
            K.text("Žádná lana v tažené oblasti – posudek se neprovádí.")
            return
        Ap_t = sum(self.kabely[ik].Ap for ik in tah)
        As_t = sum(v.As for v in self.vyztuz if v.z < P.zt)
        fr_sls = self._faktor_prenosu()
        fr_msu = self._faktor_prenosu(msu=True)
        for f in self.faze:
            if not f.provoz:
                continue
            fctd_t = b.alpha_ct * 0.7 * b.fctm_t(f.t) / b.gamma_c
            fbpd = self.eta_p2 * 1.0 * fctd_t
            s_inf = sum(float(f.sigma[ik][self.im]) * self.kabely[ik].Ap for ik in tah) / Ap_t
            lbpd = lpt2 + self.a2_pt * d_l * max(p.fpd - s_inf, 0.0) / fbpd
            K.text(f"<b>{f.nazev_t}</b>:")
            K.krok("Pevnost v soudržnosti pro kotvení", "f_{bpd} = η_{p2}·η_{1}·f_{ctd}(t)",
                   f"{fmt(self.eta_p2)}·1,0·{fmt(fctd_t)}", fbpd, "MPa", "8.10.2.3(2)")
            K.krok("Kotevní délka", "l_{bpd} = l_{pt2} + α_{2}·φ·(f_{pd} − σ_{pm,t})/f_{bpd}",
                   f"{fmt(lpt2)} + {fmt(self.a2_pt)}·{fmt(d_l)}·({fmt(p.fpd)} − {fmt(s_inf)})/{fmt(fbpd)}", lbpd, "mm",
                   "8.10.2.3(4)")
            ob = self.komb[f.nazev]["msu"]
            sig_msu = [np.where(fr_sls > 1e-9, s / np.where(fr_sls > 1e-9, fr_sls, 1.0), 0.0) * fr_msu
                       for s in f.sigma]
            NP, MP, _ = self._sily_predpeti(sig_msu)
            Vres = self.msu_V.get(f.nazev, {}).get("res", {})
            Mres = self.msu_M.get(f.nazev, {}).get("vys", {})
            best = None
            for i in np.nonzero(self.v_poli)[0]:
                lx = min(self.x[i], self.L - self.x[i]) * 1000
                if lx >= lbpd or i not in Vres:
                    continue
                sd = float(self._napeti(0.0, nn.gamma_P * NP[i], nn.gamma_P * MP[i], 0.0, ob.M_max[i], idx=i))
                if sd <= b.fctk005_t(f.t):
                    continue
                r, VEd, sv = Vres[i]
                ro = Mres.get(i)
                z = ro.rameno if ro is not None and ro.konvergence and ro.rameno > 0 else r.z
                dF = r.dF_td * 1e3 if sv.Asw_s > 0 else abs(VEd) * 1e3 * r.d / z
                F_td = max(ob.M_max[i], 0.0) * 1e6 / z + dF
                F_p = max(F_td - As_t * self.betonarska.fyd, 0.0)
                s_req = F_p / Ap_t
                if lx <= lpt2:
                    s_env = s_inf * lx / lpt2
                else:
                    s_env = s_inf + (p.fpd - s_inf) * (lx - lpt2) / max(lbpd - lpt2, 1e-9)
                eta = s_req / s_env if s_env > 0 else math.inf
                if best is None or eta > best[0]:
                    best = (eta, i, s_req, s_env, F_td * 1e-3, dF * 1e-3, lx, sd)
            if best is None:
                K.text("V oblasti kotvení (l_x < l_bpd) nepřekročí tahové napětí v betonu v MSÚ f_ctk,0,05 – "
                       "kotvení lan se podle 8.10.2.3(1) neověřuje.")
                continue
            eta, i, s_req, s_env, F_td, dF, lx, sd = best
            K.krok("Rozhodující řez – vzdálenost od konce nosníku", "l_{x}", "", lx, "mm")
            K.krok("Tahové napětí v dolních vláknech (MSÚ)", "σ_{ct} > f_{ctk,0,05}(t)", "",
                   f"{fmt(sd)} > {fmt(b.fctk005_t(f.t))}", "MPa", "8.10.2.3(1)")
            K.krok("Požadovaná tahová síla", "F_{td} = M_{Ed}/z + ΔF_{td}", f"ΔF_td = {fmt(dF)} kN", F_td, "kN",
                   "6.2.3(7), 9.2.1.3")
            K.krok("Požadované napětí v lanech", "σ_{p,req} = (F_{td} − A_{s}·f_{yd})/A_{p}", "", s_req, "MPa")
            K.krok("Napětí přenositelné kotvením", "σ_{p,kotv}(l_{x})", "", s_env, "MPa", "obr. 8.17")
            self.protokol.pridej_posudek(K, VysledekPosudku(
                "Kotvení lan soudržností", "MSÚ", s_req, s_env, "MPa", eta, f.nazev, "MSÚ – základní",
                float(self.x[i]), poznamka=f"l_x = {fmt(lx)} mm, l_bpd = {fmt(lbpd)} mm, ΔF_td = {fmt(dF)} kN",
                odkaz="8.10.2.3", skupina="Kotvení"))

    # ------------------------------------------------------------------
    def _krehky_lom(self):
        b, s = self.beton, self.betonarska
        P = self.prurez
        K = self.protokol.kapitola("Výztuž pro vyloučení křehkého lomu", 2)
        K.text("Ověření podle ČSN EN 1992-2, 6.1(109): (a) minimální betonářská výztuž A_s,min = M_rep/(z_s·f_yk), "
               "kde M_rep je moment na mezi vzniku trhlin s f_ctm bez účinku předpětí; nebo (b) ověření, že při "
               "redukované ploše předpínací výztuže (tah f_ctm v dolních vláknech při časté kombinaci) je "
               "únosnost vyšší než účinek časté kombinace. Posudek vyhoví, je-li splněna alespoň jedna podmínka.")
        f = next(ff for ff in self.faze if ff.provoz)
        i = self.im
        Mrep = b.fctm * P.W_d * 1e-6
        zs_v = [v for v in self.vyztuz if v.z < P.zt]
        As_prov = sum(v.As for v in zs_v)
        d_s = P.h - (sum(v.z * v.As for v in zs_v) / As_prov if As_prov > 0 else 0.1 * P.h)
        z_s = 0.9 * d_s
        As_min = Mrep * 1e6 / (z_s * s.fyk)
        K.krok("Moment na mezi vzniku trhlin", "M_{rep} = f_{ctm}·W_{d}", f"{fmt(b.fctm)}·{fmt(P.W_d)}·10^{{−6}}",
               Mrep, "kNm")
        K.krok("Minimální plocha výztuže", "A_{s,min} = M_{rep}/(z_{s}·f_{yk})",
               f"{fmt(Mrep)}·10^{{6}}/({fmt(z_s)}·{fmt(s.fyk)})", As_min, "mm²", "(6.101a)")
        K.krok("Navržená výztuž v tažené oblasti", "A_{s,prov}", "", As_prov, "mm²")
        eta_a = As_min / As_prov if As_prov > 0 else math.inf
        # (b) redukovaná plocha předpětí
        NP, MP, _ = self._sily_predpeti(f.sigma, f.k_Ap)
        Mfr = self.komb[f.nazev]["casta"].M_max[i]
        Mg0 = self.zs_g0.M_max[i]
        sP = float(self._napeti(0.0, NP[i], MP[i], 0.0, 0.0, idx=i))
        sE = float(self._napeti(0.0, 0.0, 0.0, Mg0, Mfr, idx=i))
        rho = (b.fctm - sE) / sP if sP < 0 else 1.0
        rho = min(max(rho, 0.0), 1.0)
        K.krok("Redukce předpětí pro dosažení f_ctm (častá kombinace)", "ρ_{red} = (f_{ctm} − σ_{E})/σ_{P}",
               f"({fmt(b.fctm)} − {fmt(sE)})/{fmt(sP)}", rho, "")
        vyz = [VrstvaVyztuze(v.z, v.As, v.nazev) for v in self.vyztuz]
        vr = self._vrstvy_msu(f, i, redukce=rho)
        r = ohybova_unosnost(P, b, self.predp, s, vr, vyz, eps_ud_p=f.eps_ud_p)
        M_ed_fr = Mfr + Mg0
        K.krok("Únosnost s redukovanou plochou předpětí", "M_{Rd,red}", "", r.MRd, "kNm")
        K.krok("Moment od časté kombinace", "M_{fr}", "", M_ed_fr, "kNm")
        eta_b = M_ed_fr / r.MRd if r.MRd > 0 else math.inf
        if eta_a <= eta_b:
            v = VysledekPosudku("Křehký lom – min. výztuž", "MSÚ", As_min, As_prov, "mm²", eta_a, f.nazev, "", float(self.x[i]),
                                poznamka=f"varianta (a); varianta (b): η = {fmt(eta_b)}", odkaz="EN 1992-2 6.1(109)",
                                skupina="Křehký lom")
        else:
            v = VysledekPosudku("Křehký lom – redukované předpětí", "MSÚ", M_ed_fr, r.MRd, "kNm", eta_b, f.nazev,
                                "častá", float(self.x[i]), poznamka=f"varianta (b); varianta (a): η = {fmt(eta_a)}",
                                odkaz="EN 1992-2 6.1(109)", skupina="Křehký lom")
        self.protokol.pridej_posudek(K, v)
