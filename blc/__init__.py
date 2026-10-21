"""
blc – Bridge Load Calculator
============================
Výpočet přechodnosti vojenských vozidel na mostech – deskový model,
SPOJITÝ NOSNÍK o více polích; třída betonu (E = Ecm), podélné spáry,
typické prefabrikáty, typ konstrukce nosníky / deska (pás 1 m), šikmost
a okrajové podmínky podpor (kloub tvrdý / měkký, vetknutí, pružné vetknutí).

Hlavní funkce:
  porovnani_zatizeni(typ, MLC, L, n, dist, Ve, N, E, Iy, b, ...) → ComparisonResult
  spustit_gui()

Spuštění:  python -m blc  (GUI),  python -m blc --demo  (ukázkový výpočet)
"""

__version__ = "1.0.0"

from .geometry   import Konstrukce, Rez, E_betonu, ECM_GPA
from .prefabrikaty import nacti_prefabrikaty, prefabrikat, Prefabrikat
from .vehicles   import pasove_vozidlo, kolove_vozidlo, seznam_mlc
from .comparison import porovnani_zatizeni, ComparisonResult, RezVysledek

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
]
