"""
stale_zatizeni.py
=================
Ostatní stálé zatížení mostovky (g − g0): skladba vozovky, skladba chodníků,
svodidla, zábradlí a další liniová zatížení.

Příčné uspořádání (y od levého okraje mostovky, B = šířka mostovky
z modelu konstrukce):

    0 ── chodník L ── chodnik_L ──── vozovka ──── B − chodnik_P ── chodník P ── B

  • skladba chodníku g_chodnik [kN/m²] na obou chodnících,
  • skladba vozovky  g_vozovka [kN/m²] mezi chodníky,
  • zábradlí g_zabradli [kN/m] na každé straně u vnějšího okraje
    (pás šířky 0,2 m, osa 0,1 m od okraje),
  • svodidla g_svodidla [kN/m] na každé straně na okraji vozovky
    (pás šířky 0,2 m na chodníku, těsně u vozovky; bez chodníku u okraje),
  • další liniová zatížení (název, g [kN/m], y osy [m], šířka [m]).

Plošná i liniová zatížení působí po celé délce mostu (podél osy prvku);
do 2D MKP se zadávají jako rovnoměrně zatížené obdélníky (plošky) – část
mimo konstrukci (za osou krajní podpory) jde do opěry.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple

Platek = Tuple[float, float, float, float, float]    # (F [kN], x0, x1, y0, y1)

SIRKA_LINIOVE = 0.2          # šířka pásu liniového zatížení [m]


@dataclass
class LiniovaZatizeni:
    """Liniové zatížení podél mostu (svodidlo, zábradlí, římsa …)."""
    nazev: str
    g: float                  # [kN/m]
    y: float                  # osa [m] od levého okraje mostovky
    sirka: float = SIRKA_LINIOVE


@dataclass
class Vybaveni:
    """Příčné uspořádání a tíhy vybavení mostu (ostatní stálé zatížení)."""
    chodnik_L: float = 0.0          # šířka chodníku vlevo [m]
    chodnik_P: float = 0.0          # šířka chodníku vpravo [m]
    g_chodnik: float = 0.0          # tíha skladby chodníku [kN/m²]
    g_vozovka: float = 0.0          # tíha skladby vozovky [kN/m²]
    g_zabradli: float = 0.0         # zábradlí na každé straně [kN/m]
    g_svodidla: float = 0.0         # svodidlo na každé straně [kN/m]
    liniova: List[LiniovaZatizeni] = field(default_factory=list)

    def kontrola(self, B: float) -> None:
        for nazev, v in (("chodnik_L", self.chodnik_L), ("chodnik_P", self.chodnik_P),
                         ("g_chodnik", self.g_chodnik), ("g_vozovka", self.g_vozovka),
                         ("g_zabradli", self.g_zabradli), ("g_svodidla", self.g_svodidla)):
            if v < 0:
                raise ValueError(f"{nazev} musí být nezáporné.")
        if self.chodnik_L + self.chodnik_P >= B - 1e-9:
            raise ValueError(f"Chodníky ({self.chodnik_L:g} + {self.chodnik_P:g} m) "
                             f"zabírají celou šířku mostovky B = {B:g} m.")
        for l in self.liniova:
            if not (0.0 <= l.y <= B):
                raise ValueError(f"Liniové zatížení '{l.nazev}': y = {l.y:g} m leží mimo "
                                 f"mostovku 0 … {B:g} m.")
            if l.sirka <= 0:
                raise ValueError(f"Liniové zatížení '{l.nazev}': šířka musí být kladná.")

    # ---- geometrie ------------------------------------------------------
    def sirka_vozovky(self, B: float) -> float:
        return B - self.chodnik_L - self.chodnik_P

    def y_osy_vozovky(self, B: float) -> float:
        """Osa vozovky [m] od levého okraje (výchozí poloha vozidla Ve)."""
        return self.chodnik_L + 0.5 * self.sirka_vozovky(B)

    def zony(self, B: float) -> List[Tuple[str, float, float, float]]:
        """Plošná zatížení: (název, g [kN/m²], y0, y1)."""
        out = []
        if self.chodnik_L > 0 and self.g_chodnik:
            out.append(("chodník L", self.g_chodnik, 0.0, self.chodnik_L))
        if self.g_vozovka:
            out.append(("vozovka", self.g_vozovka, self.chodnik_L, B - self.chodnik_P))
        if self.chodnik_P > 0 and self.g_chodnik:
            out.append(("chodník P", self.g_chodnik, B - self.chodnik_P, B))
        return out

    def liniova_vse(self, B: float) -> List[LiniovaZatizeni]:
        """Všechna liniová zatížení (zábradlí, svodidla + zadaná)."""
        w = SIRKA_LINIOVE
        out = []
        if self.g_zabradli:
            out += [LiniovaZatizeni("zábradlí L", self.g_zabradli, 0.5 * w),
                    LiniovaZatizeni("zábradlí P", self.g_zabradli, B - 0.5 * w)]
        if self.g_svodidla:
            yl = max(self.chodnik_L - 0.5 * w, 0.5 * w)
            yp = min(B - self.chodnik_P + 0.5 * w, B - 0.5 * w)
            out += [LiniovaZatizeni("svodidlo L", self.g_svodidla, yl),
                    LiniovaZatizeni("svodidlo P", self.g_svodidla, yp)]
        return out + list(self.liniova)

    def popis(self, B: float) -> str:
        t = (f"chodníky {self.chodnik_L:g} + {self.chodnik_P:g} m "
             f"(g = {self.g_chodnik:g} kN/m²), vozovka {self.sirka_vozovky(B):g} m "
             f"(g = {self.g_vozovka:g} kN/m²)")
        lin = self.liniova_vse(B)
        if lin:
            t += "; " + ", ".join(f"{l.nazev} {l.g:g} kN/m (y = {l.y:.2f} m)" for l in lin)
        return t

    def tiha_na_metr(self, B: float) -> float:
        """Celková tíha vybavení na 1 m délky mostu [kN/m] (kontrola)."""
        s = sum(g * (y1 - y0) for _, g, y0, y1 in self.zony(B))
        return s + sum(l.g for l in self.liniova_vse(B))

    # ---- zatížení pro MKP ----------------------------------------------
    def platky(self, B: float, x_od: float, x_do: float) -> List[Platek]:
        """Plošky (F, x0, x1, y0, y1) po celé délce x_od … x_do."""
        out: List[Platek] = []
        for _, g, y0, y1 in self.zony(B):
            out += platky_plosne(g, x_od, x_do, y0, y1)
        for l in self.liniova_vse(B):
            y0 = max(0.0, l.y - 0.5 * l.sirka)
            y1 = min(B, l.y + 0.5 * l.sirka)
            if y1 > y0:
                out += platky_plosne(l.g / (y1 - y0), x_od, x_do, y0, y1)
        return out


def platky_plosne(g: float, x0: float, x1: float, y0: float, y1: float,
                  dx: float = 2.0, dy: float = 0.5) -> List[Platek]:
    """Rovnoměrné plošné zatížení g [kN/m²] na obdélníku rozdělené na menší
    plošky (≤ dx × dy) – MKP plošky integruje body, menší plošky = méně bodů."""
    if g == 0 or x1 <= x0 or y1 <= y0:
        return []
    nx = max(1, int(math.ceil((x1 - x0) / dx - 1e-9)))
    ny = max(1, int(math.ceil((y1 - y0) / dy - 1e-9)))
    hx, hy = (x1 - x0) / nx, (y1 - y0) / ny
    return [(g * hx * hy, x0 + i * hx, x0 + (i + 1) * hx, y0 + j * hy, y0 + (j + 1) * hy)
            for i in range(nx) for j in range(ny)]
