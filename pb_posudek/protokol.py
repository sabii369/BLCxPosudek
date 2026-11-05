"""Záznam podrobného postupu výpočtu a výsledků posudků."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


def fmt(v: Any, nd: int = 3) -> str:
    """Formátování čísla s desetinnou čárkou a rozumným počtem platných míst."""
    if v is None:
        return "–"
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "ano" if v else "ne"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f):
        return "–"
    if math.isinf(f):
        return "∞"
    a = abs(f)
    if nd == 0:
        return f"{f:,.0f}".replace(",", " ")
    if a != 0 and (a >= 1e7 or a < 1e-3):
        s = f"{f:.{nd}e}"
        mant, exp = s.split("e")
        return f"{mant.replace('.', ',')}·10^{{{int(exp)}}}"
    if a >= 1000:
        s = f"{f:,.{max(nd - 3, 0)}f}".replace(",", " ")
    elif a >= 100:
        s = f"{f:.{max(nd - 2, 1)}f}"
    elif a >= 10:
        s = f"{f:.{max(nd - 1, 1)}f}"
    else:
        s = f"{f:.{nd}f}"
    return s.replace(".", ",")


@dataclass
class Krok:
    popis: str
    vzorec: str = ""
    dosazeni: str = ""
    vysledek: Any = None
    jednotka: str = ""
    odkaz: str = ""


@dataclass
class Tabulka:
    hlavicka: list[str]
    radky: list[list[Any]]
    popisek: str = ""
    souhrn: bool = False   # poslední řádek je souhrnný (zvýrazní se)


@dataclass
class Obrazek:
    soubor: str
    popisek: str = ""


@dataclass
class VysledekPosudku:
    """Výsledek jednoho posudku (jedno kritérium, rozhodující místo)."""

    nazev: str
    mezni_stav: str            # "MSP" | "MSÚ"
    E_d: float
    R_d: float
    jednotka: str
    vyuziti: float
    faze: str = ""
    kombinace: str = ""
    x: float | None = None
    poznamka: str = ""
    odkaz: str = ""
    skupina: str = ""

    @property
    def vyhovuje(self) -> bool:
        return self.vyuziti <= 1.0 + 1e-9

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["vyhovuje"] = self.vyhovuje
        return d


@dataclass
class Kapitola:
    nazev: str
    uroven: int = 1
    polozky: list[tuple[str, Any]] = field(default_factory=list)

    def text(self, t: str):
        self.polozky.append(("text", t))
        return self

    def krok(self, popis: str, vzorec: str = "", dosazeni: str = "", vysledek: Any = None,
             jednotka: str = "", odkaz: str = ""):
        self.polozky.append(("krok", Krok(popis, vzorec, dosazeni, vysledek, jednotka, odkaz)))
        return self

    def tabulka(self, hlavicka: list[str], radky: list[list[Any]], popisek: str = "", souhrn: bool = False):
        self.polozky.append(("tabulka", Tabulka(hlavicka, radky, popisek, souhrn)))
        return self

    def obrazek(self, soubor: str, popisek: str = ""):
        self.polozky.append(("obrazek", Obrazek(soubor, popisek)))
        return self

    def posudek(self, v: VysledekPosudku):
        self.polozky.append(("posudek", v))
        return self


@dataclass
class Protokol:
    nazev: str = "Posudek nosníku z předpjatého betonu"
    kapitoly: list[Kapitola] = field(default_factory=list)
    posudky: list[VysledekPosudku] = field(default_factory=list)

    def kapitola(self, nazev: str, uroven: int = 1) -> Kapitola:
        k = Kapitola(nazev, uroven)
        self.kapitoly.append(k)
        return k

    def pridej_posudek(self, kap: Kapitola | None, v: VysledekPosudku) -> VysledekPosudku:
        self.posudky.append(v)
        if kap is not None:
            kap.posudek(v)
        return v
