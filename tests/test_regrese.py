"""
Regrese: výsledky v kontrolních řezech (a obálky) se shodují s uloženými
referenčními hodnotami (`referencni_hodnoty.json`, viz `referencni_pripady.py`).
"""
import json

import pytest
from pytest import approx

from blc import porovnani_zatizeni
from referencni_pripady import SOUBOR, spocti, vsechny_nazvy

with open(SOUBOR, encoding="utf-8") as _f:
    REFERENCE = json.load(_f)


def test_reference_pokryva_vsechny_pripady():
    assert sorted(REFERENCE) == sorted(vsechny_nazvy())


@pytest.mark.parametrize("nazev", vsechny_nazvy())
def test_shoda_s_referenci(nazev):
    ref = REFERENCE[nazev]
    nove = spocti(porovnani_zatizeni, nazev)
    assert list(nove["rezy"]) == list(ref["rezy"]), "změnil se seznam kontrolních řezů"
    for rez, hodnoty in ref["rezy"].items():
        for velicina, h in hodnoty.items():
            assert nove["rezy"][rez][velicina] == approx(h, rel=1e-6, abs=1e-6), \
                f"{rez}: {velicina}"
    for velicina, h in ref.get("obalky", {}).items():
        assert nove["obalky"][velicina] == approx(h, rel=1e-6, abs=1e-6), velicina
