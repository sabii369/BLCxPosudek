"""pb_posudek – posudek nosníku z předpjatého betonu podle ČSN EN 1992-1-1 / 1992-2.

Základní použití::

    from pb_posudek import nacti_model, vytvor_protokol
    model = nacti_model("examples/nosnik_I_20m_dodatecne.toml")
    model.spocitej()
    vytvor_protokol(model, "vystup")
"""
from .materialy import Beton, BetonarskaVyztuz, PredpinaciVyztuz
from .model import Nastaveni, NosnikPB, SmykovaVyztuz
from .prurez import Prurez
from .vstup import model_ze_slovniku, nacti_model

__version__ = "0.1.0"

__all__ = [
    "Beton", "BetonarskaVyztuz", "PredpinaciVyztuz", "Nastaveni", "NosnikPB", "SmykovaVyztuz",
    "Prurez", "model_ze_slovniku", "nacti_model", "vytvor_protokol", "__version__",
]


def vytvor_protokol(model, adresar="vystup"):
    """Vykreslí grafy a uloží HTML protokol, JSON s výsledky; vrací cestu k HTML."""
    from .report import uloz_protokol
    return uloz_protokol(model, adresar)
