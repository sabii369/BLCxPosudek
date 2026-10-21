"""
vehicles.py
===========
Definice zatížení vojenských vozidel dle NATO AEP 3.12.1.5.

Obsahuje dva typy vozidel:
  - pasove_vozidlo(MLC)  – pásová vozidla
  - kolove_vozidlo(MLC)  – kolová vozidla

Vstup: třída MLC (string), např. "MLC80"
Výstup: tuple s parametry vozidla (viz docstrings funkcí)
"""

from dataclasses import dataclass
from typing import Tuple

# ---------------------------------------------------------------------------
# Datové třídy pro přehledné předávání parametrů
# ---------------------------------------------------------------------------

@dataclass
class PasoveVozidlo:
    """Parametry pásového vozidla."""
    F: float        # Lineární zatížení [kN/m]
    a1: float       # Začátek kontaktní plochy od referenčního bodu [m]
    a2: float       # Délka pásu [m]
    rozvor: float   # Rozvor (vzdálenost středů pásů) [m]
    b_k: float      # Šířka pásu [m]


@dataclass
class KoloveVozidlo:
    """Parametry kolového vozidla."""
    F1: float   # Síla 1. nápravy [kN]
    F2: float   # Síla 2. nápravy [kN]
    F3: float   # Síla 3. nápravy [kN]
    F4: float   # Síla 4. nápravy [kN]
    F5: float   # Síla 5. nápravy [kN]
    a1: float   # Poloha 1. nápravy [m]
    a2: float   # Vzdálenost 1.–2. nápravy [m]
    a3: float   # Vzdálenost 2.–3. nápravy [m]
    a4: float   # Vzdálenost 3.–4. nápravy [m]
    a5: float   # Vzdálenost 4.–5. nápravy [m]
    N1: float   # Max. zatížení nápravy [kg]
    d: float    # Kontaktní délka kola [m]
    rozvor: float  # Rozvor (vzdálenost středů kol) [m]
    b_k: float  # Kontaktní šířka kola [m]


# ---------------------------------------------------------------------------
# Tabulka pásových vozidel (MLC třída → parametry)
# ---------------------------------------------------------------------------

_PASOVE_DATA = {
    "MLC4":   dict(hmotnost=3630,   delka_pasu=1.83, b_n=1.83, b_k=0.30),
    "MLC8":   dict(hmotnost=7260,   delka_pasu=1.98, b_n=1.98, b_k=0.30),
    "MLC12":  dict(hmotnost=10880,  delka_pasu=2.74, b_n=2.03, b_k=0.30),
    "MLC16":  dict(hmotnost=14510,  delka_pasu=2.74, b_n=2.13, b_k=0.30),
    "MLC20":  dict(hmotnost=18140,  delka_pasu=2.74, b_n=2.44, b_k=0.41),
    "MLC24":  dict(hmotnost=21770,  delka_pasu=2.74, b_n=2.54, b_k=0.46),
    "MLC30":  dict(hmotnost=27220,  delka_pasu=3.35, b_n=2.54, b_k=0.46),
    "MLC40":  dict(hmotnost=36290,  delka_pasu=3.66, b_n=2.84, b_k=0.56),
    "MLC50":  dict(hmotnost=45360,  delka_pasu=3.96, b_n=3.25, b_k=0.66),
    "MLC60":  dict(hmotnost=54430,  delka_pasu=4.27, b_n=3.35, b_k=0.71),
    "MLC70":  dict(hmotnost=63500,  delka_pasu=4.57, b_n=3.51, b_k=0.79),
    "MLC80":  dict(hmotnost=72580,  delka_pasu=4.88, b_n=3.66, b_k=0.84),
    "MLC90":  dict(hmotnost=81650,  delka_pasu=5.18, b_n=3.81, b_k=0.89),
    "MLC100": dict(hmotnost=90720,  delka_pasu=5.49, b_n=3.96, b_k=0.94),
    "MLC120": dict(hmotnost=108860, delka_pasu=6.10, b_n=4.27, b_k=1.02),
    "MLC150": dict(hmotnost=136080, delka_pasu=7.32, b_n=4.67, b_k=1.27),
}

# ---------------------------------------------------------------------------
# Tabulka kolových vozidel (MLC třída → parametry)
# Síly jsou v kg, konvertujeme na kN dělením 100 (1 kN ≈ 100 kg síly)
# ---------------------------------------------------------------------------

_KOLOVE_DATA = {
    "MLC4":   dict(F1=910,   F2=1590,  F3=1590,  F4=0,     F5=0,
                   a1=0, a2=2.44, a3=1.22, a4=0,    a5=0,
                   N1=2270,  d=0.15, b_n=1.98, b_k=0.15),
    "MLC8":   dict(F1=2720,  F2=2720,  F3=2720,  F4=0,     F5=0,
                   a1=0, a2=3.05, a3=1.22, a4=0,    a5=0,
                   N1=4990,  d=0.20, b_n=1.98, b_k=0.20),
    "MLC12":  dict(F1=2720,  F2=4540,  F3=4540,  F4=1810,  F5=0,
                   a1=0, a2=3.05, a3=1.22, a4=3.66, a5=0,
                   N1=7260,  d=0.25, b_n=1.98, b_k=0.25),
    "MLC16":  dict(F1=2720,  F2=5900,  F3=5900,  F4=2270,  F5=0,
                   a1=0, a2=3.05, a3=1.22, a4=3.66, a5=0,
                   N1=8620,  d=0.25, b_n=2.45, b_k=0.25),
    "MLC20":  dict(F1=3630,  F2=7710,  F3=7710,  F4=2720,  F5=0,
                   a1=0, a2=3.05, a3=1.22, a4=3.66, a5=0,
                   N1=9980,  d=0.25, b_n=2.45, b_k=0.30),
    "MLC24":  dict(F1=4540,  F2=9070,  F3=9070,  F4=2720,  F5=0,
                   a1=0, a2=3.05, a3=1.22, a4=3.66, a5=0,
                   N1=10890, d=0.25, b_n=2.45, b_k=0.30),
    "MLC30":  dict(F1=5440,  F2=9980,  F3=9980,  F4=5440,  F5=0,
                   a1=0, a2=3.05, a3=1.22, a4=3.66, a5=0,
                   N1=13150, d=0.30, b_n=2.45, b_k=0.35),
    "MLC40":  dict(F1=6350,  F2=11790, F3=11790, F4=12700, F5=0,
                   a1=0, a2=3.66, a3=1.22, a4=4.88, a5=0,
                   N1=15420, d=0.30, b_n=2.45, b_k=0.35),
    "MLC50":  dict(F1=7260,  F2=13610, F3=13610, F4=18140, F5=0,
                   a1=0, a2=3.66, a3=1.22, a4=4.88, a5=0,
                   N1=18140, d=0.30, b_n=2.45, b_k=0.40),
    "MLC60":  dict(F1=7260,  F2=16330, F3=16330, F4=11790, F5=11790,
                   a1=0, a2=3.66, a3=1.52, a4=4.57, a5=1.22,
                   N1=20860, d=0.35, b_n=2.98, b_k=0.60),
    "MLC70":  dict(F1=9520,  F2=19050, F3=19050, F4=12700, F5=12700,
                   a1=0, a2=3.66, a3=1.52, a4=4.57, a5=1.22,
                   N1=23130, d=0.35, b_n=2.98, b_k=0.66),
    "MLC80":  dict(F1=10890, F2=21770, F3=21770, F4=14510, F5=14510,
                   a1=0, a2=3.66, a3=1.52, a4=5.49, a5=1.52,
                   N1=25400, d=0.40, b_n=2.98, b_k=0.72),
    "MLC90":  dict(F1=12250, F2=24490, F3=24490, F4=16330, F5=16330,
                   a1=0, a2=3.66, a3=1.52, a4=5.49, a5=1.52,
                   N1=27210, d=0.40, b_n=2.98, b_k=0.80),
    "MLC100": dict(F1=13610, F2=27220, F3=27220, F4=18140, F5=18140,
                   a1=0, a2=3.66, a3=1.68, a4=6.25, a5=1.52,
                   N1=29030, d=0.40, b_n=3.48, b_k=0.90),
    "MLC120": dict(F1=16330, F2=32660, F3=32660, F4=21770, F5=21770,
                   a1=0, a2=3.66, a3=1.83, a4=6.10, a5=1.52,
                   N1=32660, d=0.40, b_n=3.48, b_k=1.00),
    "MLC150": dict(F1=19960, F2=38100, F3=38100, F4=29030, F5=29030,
                   a1=0, a2=3.66, a3=2.13, a4=6.71, a5=1.83,
                   N1=38100, d=0.40, b_n=3.48, b_k=1.00),
}


def pasove_vozidlo(MLC: str) -> PasoveVozidlo:
    """Vrátí parametry pásového vozidla pro zadanou třídu MLC."""
    MLC = MLC.upper()
    if MLC not in _PASOVE_DATA:
        raise ValueError(f"Neznámá třída MLC: '{MLC}'. "
                         f"Dostupné: {sorted(_PASOVE_DATA.keys())}")
    d = _PASOVE_DATA[MLC]
    hmotnost = d["hmotnost"]
    delka    = d["delka_pasu"]
    b_n      = d["b_n"]
    b_k      = d["b_k"]
    F        = hmotnost / 100.0 / delka
    rozvor   = b_n - b_k
    return PasoveVozidlo(F=F, a1=0.0, a2=delka, rozvor=rozvor, b_k=b_k)


def kolove_vozidlo(MLC: str) -> KoloveVozidlo:
    """Vrátí parametry kolového vozidla pro zadanou třídu MLC."""
    MLC = MLC.upper()
    if MLC not in _KOLOVE_DATA:
        raise ValueError(f"Neznámá třída MLC: '{MLC}'. "
                         f"Dostupné: {sorted(_KOLOVE_DATA.keys())}")
    d = _KOLOVE_DATA[MLC]
    return KoloveVozidlo(
        F1=d["F1"] / 100.0, F2=d["F2"] / 100.0,
        F3=d["F3"] / 100.0, F4=d["F4"] / 100.0,
        F5=d["F5"] / 100.0,
        a1=d["a1"], a2=d["a2"], a3=d["a3"],
        a4=d["a4"], a5=d["a5"],
        N1=d["N1"], d=d["d"],
        rozvor=d["b_n"] - d["b_k"],
        b_k=d["b_k"],
    )


def seznam_mlc() -> list:
    """Vrátí seřazený seznam dostupných tříd MLC."""
    order = [int(k.replace("MLC", "")) for k in _PASOVE_DATA]
    return [f"MLC{n}" for n in sorted(order)]
