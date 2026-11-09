"""
blc – Bridge Load Calculator
============================
Výpočet přechodnosti vojenských vozidel na mostech – deskový model,
SPOJITÝ NOSNÍK o více polích; třída betonu (E = Ecm), podélné spáry,
typické prefabrikáty, typ konstrukce nosníky / deska (pás 1 m), šikmost
a okrajové podmínky podpor (kloub tvrdý / měkký, vetknutí, pružné vetknutí).

Hlavní funkce:
  porovnani_zatizeni(typ, MLC, L, n, dist, Ve, N, E, Iy, b, ...) → ComparisonResult
  vnitrni_sily(L, N, b, Iy, ..., vybaveni, A_nosniku, Ve, ...) → VysledekSil
      (g0, g − g0, q na nosnících / pásech 1 m – vstup pro Posudek PB)
  uloz_vysledky(vys, slozka, ...)  → JSON, CSV, TOML pro Posudek PB
  spustit_gui()

Spuštění:  python -m blc  (GUI),  python -m blc --demo  (ukázkový výpočet),
           python -m blc --sily vstup.toml  (vnitřní síly pro posudek)
"""

__version__ = "1.5.0"

from .geometry   import Konstrukce, Rez, E_betonu, ECM_GPA
from .prefabrikaty import nacti_prefabrikaty, prefabrikat, Prefabrikat
from .vehicles   import pasove_vozidlo, kolove_vozidlo, seznam_mlc
from .comparison import porovnani_zatizeni, ComparisonResult, RezVysledek
from .stale_zatizeni import Vybaveni, LiniovaZatizeni
from .vnitrni_sily import vnitrni_sily, VysledekSil, Soucinitele
from .export_pb import uloz_vysledky, toml_zatizeni_pb, zatizeni_pb_dict

try:
    from .plotting import (plot_obalky, plot_obalky_nosniky, plot_vyuziti_rezy,
                           plot_pricny_roznos, plot_profily_nosniky, plot_zatizeni, plot_sit)
except ImportError:          # chybí matplotlib
    pass
try:
    from .gui import spustit_gui
except ImportError:
    def spustit_gui():
        print("GUI není dostupné (chybí tkinter).")

__all__ = [
    "__version__",
    "Konstrukce", "Rez", "E_betonu", "ECM_GPA", "nacti_prefabrikaty", "prefabrikat",
    "Prefabrikat", "pasove_vozidlo", "kolove_vozidlo", "seznam_mlc",
    "porovnani_zatizeni", "ComparisonResult", "RezVysledek", "spustit_gui",
    "Vybaveni", "LiniovaZatizeni", "vnitrni_sily", "VysledekSil", "Soucinitele",
    "uloz_vysledky", "toml_zatizeni_pb", "zatizeni_pb_dict",
]
