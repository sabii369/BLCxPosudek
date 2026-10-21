# Bridge Load Calculator (BLC)

Posouzení přechodnosti vojenských vozidel (třídy MLC dle NATO AEP-3.12.1.5) na silničních mostech
a porovnání s výjimečnou zatížitelností **Ve**. Program počítá spojitý nosník o více polích
(1D model), příčné rozdělení zatížení deskovým 2D modelem (MKP, prvek MITC4) a výsledky
vyhodnocuje po kontrolních řezech.

## Co program umí

- spojitý nosník o *n* polích s libovolnými rozpětími,
- dva typy konstrukce: **nosníky** (mostovka z N nosníků, volitelně s podélnou spárou) a **deska** (pás 1 m),
- kolmé i **šikmé mosty** (úhel šikmosti 90°–165°, pravá / levá šikmost),
- třída betonu (E = Ecm dle ČSN EN 1992-1-1), typické prefabrikáty z tabulky `blc/data/Prefabrikáty.xlsx`,
- **okrajové podmínky podpor**: kloub tvrdý / měkký, vetknutí, pružné vetknutí, pružné podpory k_v,
- grafické rozhraní (Tkinter) i skriptové použití, obálky M a V, využití MLC/Ve v řezech, příčné rozdělení.

Ovládání, metoda výpočtu, výstupy a omezení: [`docs/navod.md`](docs/navod.md).

## Rychlý start (Windows)

```bat
git clone https://github.com/sabii369/bridge-load-calculator.git
cd bridge-load-calculator

setup.bat            :: jednou – nainstaluje numpy, scipy, matplotlib, openpyxl
spustit.bat          :: spustí grafické rozhraní
```

Z příkazového řádku (ve složce repozitáře):

```bash
python -m pip install -r requirements.txt
python -m blc                 # GUI
python -m blc --demo          # ukázkový výpočet v konzoli + grafy do vystupy/demo/
```

Vyžaduje Python 3.11+ (s `tkinter` pro GUI). Volitelně lze balíček nainstalovat
(`python -m pip install -e .[dev]`), pak je k dispozici i příkaz `blc`.

## Testy

```bash
python -m pip install pytest
python -m pytest
```

- `tests/test_nosnik_1d.py` – 1D model proti analytickým řešením (spojitý nosník, vetknutí, pružné podpory),
- `tests/test_deska_mkp.py` – 2D MKP: prvek MITC4, smyk κ = 5/6, spáry, šikmost, pružné podpory, okrajové podmínky 2D = 1D,
- `tests/test_porovnani.py` – celý výpočet `porovnani_zatizeni`, rovnováha Σ nosníků = statika, síť MKP, prefabrikáty,
- `tests/test_regrese.py` – výsledky v kontrolních řezech proti uloženým referenčním hodnotám
  (`tests/referencni_hodnoty.json`). Po **záměrné** změně modelu se přegenerují
  příkazem `python tests/referencni_pripady.py` a změna se zkontroluje v `git diff`.

## Struktura

```
bridge-load-calculator/
├── blc/                     balíček programu
│   ├── __main__.py          spouštění (python -m blc: GUI / --demo)
│   ├── gui.py               grafické rozhraní (Tkinter)
│   ├── comparison.py        porovnání MLC vs Ve po kontrolních řezech (porovnani_zatizeni)
│   ├── beam_1d.py           1D analýza spojitého nosníku (Hermitovy prvky), pojezd vozidel
│   ├── plate_fem.py         2D MKP model nosníků přes více polí (MITC4, spáry, šikmost)
│   ├── slab_fem.py          2D MKP model desky (kosoúhlá síť, šikmý most)
│   ├── geometry.py          geometrie konstrukce, okrajové podmínky, kontrolní řezy, třídy betonu
│   ├── vehicles.py          zatížení vozidel MLC (pásová, kolová)
│   ├── prefabrikaty.py      načtení tabulky prefabrikátů
│   ├── plotting.py          grafy
│   └── data/Prefabrikáty.xlsx
├── tests/                   testy (pytest) + referenční hodnoty
├── docs/navod.md            uživatelský návod
├── setup.bat, spustit.bat   instalace a spuštění na Windows
├── requirements.txt, pyproject.toml
└── CLAUDE.md                pokyny pro vývoj s Claude Code
```

## Použití z Pythonu

```python
from blc import porovnani_zatizeni

cr = porovnani_zatizeni(
    typ="k", MLC="MLC80",
    L=[10.0, 14.0, 10.0],        # rozpětí polí [m]
    n=30, dist=30.5, Ve=80.0,
    N=8, beton="C35/45", Iy=0.0144, b=1.0, nu=0.2,
    d=0.55, ex=0.25,
)
print(cr.rozhodujici.rez.id, cr.max_vyuziti)
```

Další příklady (spára, šikmá deska, vetknutí) jsou ve funkci `demo` v `blc/__main__.py`.
