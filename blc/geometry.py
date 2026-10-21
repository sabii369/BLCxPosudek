"""
geometry.py
===========
Geometrie konstrukce – spojitý nosník o n polích – a seznam kontrolních řezů.

Dva typy konstrukce
  • "nosniky" – mostovka z N nosníků (případně se spárami),
  • "deska"   – jedna deska šířky b a tloušťky h; posuzují se síly
                zintegrované na pás šířky 1 m (jen podélný směr),
  a šikmost: úhel alfa [°] mezi osou podpory a osou prvku; 90° = kolmý most,
  šikmost roste k 180° (teoretická mez); ve výpočtu se použije ostrý úhel
  α' = 180° − alfa,
  druh "prava" | "leva".  Souřadnice x je vždy ve směru osy prvku (nosníku),
  y napříč.  Podpora pruhu (nosníku) s osou v y je posunuta o
        x0(y) = −s·(y − B/2)·cot(180° − alfa),   s = +1 pravá, −1 levá,
  tj. osa podpory je šikmá; nosníky mají kolmé čelo a podporu přes celou
  svou šířku v bodě, kde jejich osa protíná osu podpory (obr. 1), deska je
  uložena liniově podél šikmé osy podpory (obr. 2, aproximace po pruzích).

Konstrukce
----------
  • n polí o rozpětích L[0..n-1], n+1 liniových podpor v x_k = ΣL[:k],
  • d = statická účinná výška průřezu; posouvající síla se posuzuje
    ve vzdálenosti d od podpory, tj. v řezu  x_k ± d,
  • stejný průřez (Iy, E) ve všech polích,
  • volitelná podélná spára mezi sousedními nosníky: šířka b_s,
    moment setrvačnosti Iy_s, náhradní tloušťka h_s = (12·Iy_s/b_s)^(1/3),
    vlastní beton (E_s = Ecm třídy betonu spáry);
    spára je s nosníky spojena kloubově.  Šířka mostovky
    B = N·b + (N−1)·b_s, osa nosníku k: y_k = k·(b + b_s) + b/2.
  • podepřeny jsou vždy jen nosníky (spára vlastní podporu nemá, kolmý
    i šikmý most) → délka podpory napříč N·b (deska: B), viz delka_podpory;
    na ni se vztahují k_v a k_rot i v 1D modelu.

Okrajové podmínky podpor – jednou pro celý most
------------------------------------------------
  uloz = "tvrde"     kloubové TVRDÉ uložení: w = 0 (nebo pružina k_v), natočení
                     podél osy podpory β_s = 0; u pružné podpory konzistentně
                     β_s = ∂w/∂s (podpora se natáčí s průhybem, bez parazitního smyku)
         "mekke"     kloubové MĚKKÉ uložení: jen w; obě natočení volná
                     (odpovídá liniové podpoře s volnými rotacemi, např. SCIA)
         "vetknuti"  vetknutí: navíc natočení kolem osy podpory β_n = 0,
                     s k_rot pružné vetknutí (rotační pružina)
  k_rot              tuhost pružného vetknutí [kNm/rad na 1 m délky podpory];
                     None = dokonalé vetknutí (jen pro uloz = "vetknuti")
  beta_s_pevne       True: β_s = 0 i u pružné podpory (zjednodušená vazba; odpovídá
                     modelu SCIA s pružnou liniovou podporou a vetknutým natočením
                     podél osy podpory) – POZOR: parazitní smyk κGh·∂w/∂s

Kontrolní řezy
--------------
  M+  pole i           maximum kladného momentu v poli i (rozhodující řez se hledá)
  M-  podpora k        záporný moment nad vnitřní podporou k (2 … n);
                       u vetknutí i nad krajními podporami (1 a n+1)
  V   podpora k, L/P   posouvající síla vlevo (L) a vpravo (P) od podpory k
                        v řezu x_k ∓ d; koncové podpory mají jeden řez

Poloha zatížení pro V
---------------------
Zatížení může stát KDEKOLI na mostě, včetně pásu šířky d u podpory.
Posuzuje se jen hodnota V v řezu x_k ± d (maximum přes všechny polohy).
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Optional

EPS = 1e-9

# typy uložení – klíč → popis
ULOZENI = {
    "tvrde": "kloubové tvrdé (β_s = 0)",
    "mekke": "kloubové měkké (rotace volné)",
    "vetknuti": "vetknutí",
}


@dataclass
class Rez:
    """Jeden kontrolní řez."""
    id: str                    # např. "M+ pole 1", "V podpora 2 vpravo"
    typ: str                   # "M+" | "M-" | "V"
    x: float = 0.0             # poloha řezu (V), osa podpory (M-)
    x_lo: float = 0.0          # M+: začátek pole
    x_hi: float = 0.0          # M+: konec pole
    podpora: int = -1          # M-, V: index podpory
    pole: int = -1             # M+ i V: index pole
    strana: str = ""           # V: "L" (vlevo od podpory) | "P" (vpravo)
    na_podpore: bool = False   # V: řez leží přesně v ose podpory (d = 0)


@dataclass
class Konstrukce:
    """Spojitý nosník (mostovka z N nosníků nebo deska) o n polích."""
    L: List[float]                     # rozpětí polí [m]
    N: int                             # počet nosníků (deska: nepoužito)
    b: float                           # šířka nosníku [m] (deska: šířka desky)
    E: float                           # modul pružnosti [MPa]
    Iy: float                          # moment setrvačnosti nosníku [m⁴]
    nu: float = 0.2
    d: float = 0.0                     # statická účinná výška [m]
    spara: bool = False                # podélné spáry mezi nosníky
    b_s: float = 0.0                   # šířka spáry [m]
    Iy_s: float = 0.0                  # moment setrvačnosti spáry [m⁴]
    E_s: Optional[float] = None        # modul pružnosti betonu spáry [MPa] (None = E)
    typ: str = "nosniky"               # "nosniky" | "deska"
    h: float = 0.0                     # tloušťka desky [m] (typ "deska")
    alfa: float = 90.0                 # úhel šikmosti [°] (90 = kolmý, → 180 = max. šikmost)
    sikmost: str = "prava"             # "prava" | "leva"
    k_pod: Optional[float] = None      # svislá tuhost podpory [kN/m na 1 m délky
                                       # podpory]; None / 0 = tuhá podpora
    uloz: str = "tvrde"                # "tvrde" | "mekke" | "vetknuti"
    k_rot: Optional[float] = None      # pružné vetknutí [kNm/rad na 1 m podpory];
                                       # None / 0 = dokonalé vetknutí
    beta_s_pevne: bool = False         # β_s = 0 i u pružné podpory (jen pro srovnání se SCIA)

    def __post_init__(self):
        self.L = [float(v) for v in self.L]
        self.typ = self.typ.lower()
        if self.typ not in ("nosniky", "deska"):
            raise ValueError("Typ konstrukce musí být 'nosniky' nebo 'deska'.")
        if self.typ == "deska":
            if self.h <= 0:
                raise ValueError("Tloušťka desky h musí být kladná.")
            self.N = 1
            self.spara = False
            self.Iy = self.b * self.h ** 3 / 12.0
        self.sikmost = self.sikmost.lower()
        if self.sikmost not in ("prava", "leva"):
            raise ValueError("Šikmost musí být 'prava' nebo 'leva'.")
        if self.k_pod is not None and self.k_pod <= 0:
            self.k_pod = None
        self.uloz = (self.uloz or "tvrde").lower().replace("é", "e").replace("í", "i")
        if self.uloz not in ULOZENI:
            raise ValueError("Uložení musí být 'tvrde', 'mekke' nebo 'vetknuti'.")
        if self.k_rot is not None and self.k_rot <= 0:
            self.k_rot = None
        if self.uloz != "vetknuti":
            self.k_rot = None
        if self.uloz == "mekke":
            self.beta_s_pevne = False
        if not (90.0 <= self.alfa <= 165.0):
            raise ValueError("Úhel šikmosti alfa musí být v intervalu 90° (kolmý most) "
                             "až 165° (180° je teoretická mez).")
        if len(self.L) < 1:
            raise ValueError("Je nutné zadat alespoň jedno pole.")
        if any(v <= 0 for v in self.L):
            raise ValueError("Rozpětí polí musí být kladná.")
        if self.N < 1 or self.b <= 0:
            raise ValueError("Počet nosníků a jejich rozteč musí být kladné.")
        if self.d < 0:
            raise ValueError("d musí být nezáporné.")
        if self.spara:
            if self.N < 2:
                raise ValueError("Spára vyžaduje alespoň 2 nosníky.")
            if self.b_s <= 0 or self.Iy_s <= 0:
                raise ValueError("Šířka i Iy spáry musí být kladné.")
            if self.E_s is not None and self.E_s <= 0:
                raise ValueError("Modul pružnosti spáry musí být kladný.")
        else:
            self.b_s, self.Iy_s = 0.0, 0.0
        for i, Li in enumerate(self.L):
            if 2 * self.d >= Li - EPS:
                raise ValueError(
                    f"Pole {i + 1}: 2·d = {2 * self.d:g} m není menší než rozpětí {Li:g} m.")

    # ---- odvozené veličiny ------------------------------------------------
    @property
    def n_poli(self) -> int:
        return len(self.L)

    @property
    def x_podpor(self) -> List[float]:
        x = [0.0]
        for v in self.L:
            x.append(x[-1] + v)
        return x

    @property
    def Ltot(self) -> float:
        return sum(self.L)

    @property
    def B(self) -> float:
        return self.N * self.b + (self.N - 1) * self.b_s

    @property
    def delka_podpory(self) -> float:
        """Podepřená délka jedné podpory napříč mostem [m]: deska B, nosníky N·b
        (podepřeny jsou jen nosníky, spára vlastní podporu nemá).  Na tuto
        délku se vztahují k_v a k_rot (v 1D modelu k_v·delka_podpory)."""
        return self.B if self.je_deska else self.N * self.b

    @property
    def pruzna(self) -> bool:
        """Pružné (ne tuhé) uložení ve svislém směru."""
        return self.k_pod is not None

    @property
    def vetknuti(self) -> bool:
        """Natočení kolem osy podpory zabráněno (dokonale nebo pružně)."""
        return self.uloz == "vetknuti"

    @property
    def tvrde(self) -> bool:
        """Natočení podél osy podpory vázáno (tvrdé kloubové uložení i vetknutí)."""
        return self.uloz in ("tvrde", "vetknuti")

    def popis_ulozeni(self) -> str:
        t = ULOZENI[self.uloz]
        if self.vetknuti:
            t += (f", pružné k_rot = {self.k_rot / 1000:g} MNm/rad/m" if self.k_rot
                  else ", dokonalé")
        t += (f"; svisle pružné k_v = {self.k_pod / 1000:g} MN/m/m" if self.pruzna
              else "; svisle tuhé")
        if self.pruzna and self.tvrde:
            t += ("; β_s = 0 (zjednodušeně)" if self.beta_s_pevne else "; β_s = ∂w/∂s")
        return t

    @property
    def beta_s_sleduje(self) -> bool:
        """Natočení podél osy pružné podpory sleduje její průhyb (β_s = ∂w/∂s)."""
        return self.tvrde and self.pruzna and not self.beta_s_pevne

    @property
    def EI_celk(self) -> float:
        """Ohybová tuhost celého průřezu mostu [kN·m²] (pro 1D model)."""
        if self.typ == "deska":
            return self.E * 1000.0 * self.b * self.h ** 3 / 12.0
        ei = self.E * 1000.0 * self.Iy * self.N
        if self.spara:
            ei += self.E_spary * 1000.0 * self.Iy_s * (self.N - 1)
        return ei

    @property
    def je_deska(self) -> bool:
        return self.typ == "deska"

    @property
    def cot(self) -> float:
        """cot(180° − alfa) ≥ 0; 0 pro kolmý most."""
        if abs(self.alfa - 90.0) < 1e-9:
            return 0.0
        return 1.0 / math.tan(math.radians(180.0 - self.alfa))

    @property
    def sikmy(self) -> bool:
        return self.cot > 1e-12

    def x0(self, y: float) -> float:
        """Posun podpor v podélném směru pro příčnou souřadnici y [m]."""
        s = 1.0 if self.sikmost == "prava" else -1.0
        return -s * (y - 0.5 * self.B) * self.cot

    @property
    def rozted(self) -> float:
        """Osová vzdálenost nosníků [m]."""
        return self.b + self.b_s

    @property
    def y_nos(self) -> List[float]:
        """Osy nosníků (příčná souřadnice) [m]."""
        return [k * self.rozted + 0.5 * self.b for k in range(self.N)]

    @property
    def E_spary(self) -> float:
        """Modul pružnosti betonu spáry [MPa] (není-li zadán, = E nosníků)."""
        return self.E if self.E_s is None else self.E_s

    @property
    def h_spary(self) -> float:
        """Náhradní tloušťka deskového prvku spáry z Iy spáry."""
        return (12.0 * self.Iy_s / self.b_s) ** (1.0 / 3.0) if self.spara else 0.0

    @property
    def h_ekv(self) -> float:
        if self.typ == "deska":
            return self.h
        return self._h_ekv_nosnik

    @property
    def _h_ekv_nosnik(self) -> float:
        """Náhradní tloušťka desky z Iy nosníku."""
        return (12.0 * self.Iy / self.b) ** (1.0 / 3.0)

    # ---- kontrolní řezy ---------------------------------------------------
    def kontrolni_rezy(self) -> List[Rez]:
        xp = self.x_podpor
        n, d = self.n_poli, self.d
        out: List[Rez] = []
        for i in range(n):
            out.append(Rez(id=f"M+ pole {i + 1}", typ="M+", pole=i,
                           x_lo=xp[i], x_hi=xp[i + 1]))
        for k in (range(0, n + 1) if self.vetknuti else range(1, n)):
            out.append(Rez(id=f"M- podpora {k + 1}", typ="M-", podpora=k, x=xp[k]))
        for k in range(n + 1):
            if k > 0:                               # řez vlevo – pole k-1
                out.append(Rez(id=f"V podpora {k + 1} vlevo", typ="V", podpora=k,
                               pole=k - 1, strana="L", x=xp[k] - d,
                               na_podpore=(d < EPS)))
            if k < n:                               # řez vpravo – pole k
                out.append(Rez(id=f"V podpora {k + 1} vpravo", typ="V", podpora=k,
                               pole=k, strana="P", x=xp[k] + d,
                               na_podpore=(d < EPS)))
        return out

    def popis(self) -> str:
        pol = " + ".join(f"{v:g}" for v in self.L)
        slovo = "pole" if self.n_poli < 5 else "polí"
        txt = f"{self.n_poli} {slovo}: {pol} m"
        if self.sikmy:
            txt += f", šikmost {self.alfa:g}° {'pravá' if self.sikmost == 'prava' else 'levá'}"
        return txt


# ---------------------------------------------------------------------------
# Třídy betonu – E = Ecm dle ČSN EN 1992-1-1, tab. 3.1 [GPa]
# ---------------------------------------------------------------------------

ECM_GPA = {
    "C12/15": 27, "C16/20": 29, "C20/25": 30, "C25/30": 31, "C30/37": 33,
    "C35/45": 34, "C40/50": 35, "C45/55": 36, "C50/60": 37, "C55/67": 38,
    "C60/75": 39, "C70/85": 41, "C80/95": 42, "C90/105": 44, "C100/115": 45,
}


def E_betonu(trida: str) -> float:
    """Modul pružnosti E = Ecm [MPa] pro třídu betonu (např. "C30/37")."""
    t = trida.strip().upper().replace(" ", "")
    for k, v in ECM_GPA.items():
        if k.upper() == t:
            return 1000.0 * v
    raise ValueError(f"Neznámá třída betonu '{trida}'. Možnosti: {', '.join(ECM_GPA)}")
