# Bridge Load Calculator (BLC) – v9

Posouzení přechodnosti vojenských vozidel (třídy MLC dle NATO AEP-3.12.1.5) na silničních mostech
a porovnání s výjimečnou zatížitelností **Ve**. Program počítá spojitý nosník o více polích
(1D model), příčný rozdělení zatížení deskovým 2D modelem (MKP, prvek MITC4) a výsledky
vyhodnocuje po kontrolních řezech.

Vzniká v rámci diplomové práce na ČVUT v Praze (Kloknerův ústav) – téma hodnocení krizové
zatížitelnosti silničních mostů.

## Co verze 9 umí

- spojitý nosník o *n* polích s libovolnými rozpětími,
- dva typy konstrukce: **nosníky** (mostovka z N nosníků, volitelně s podélnou spárou) a **deska** (pás 1 m),
- kolmé i **šikmé mosty** (úhel šikmosti 90°–165°, pravá / levá šikmost),
- třída betonu (E = Ecm dle ČSN EN 1992-1-1), typické prefabrikáty z tabulky `Prefabrikáty.xlsx`,
- **okrajové podmínky podpor**: kloub tvrdý / měkký, vetknutí, pružné vetknutí,
- grafické rozhraní (Tkinter) i skriptové použití, obálky M a V, využití MLC/Ve v řezech, příčný rozdělení.

Podrobný popis ovládání, metody výpočtu, výstupů a omezení je v
[`bridge_load_calculator_v9/README.txt`](bridge_load_calculator_v9/README.txt).

## Rychlý start (Windows)

```bat
git clone https://github.com/<uzivatel>/bridge-load-calculator.git
cd bridge-load-calculator\bridge_load_calculator_v9

setup.bat            :: jednou – nainstaluje numpy, scipy, matplotlib, openpyxl
spustit_v9.bat       :: spustí grafické rozhraní
```

Nebo z příkazového řádku:

```bash
cd bridge_load_calculator_v9
python -m pip install -r requirements.txt
python main.py            # GUI
python main.py --demo     # ukázkový výpočet v konzoli + uložení grafů do PNG
python test_v9.py         # ověřovací testy
```

Vyžaduje Python 3.11+ (s `tkinter` pro GUI).

> **Pozor:** složka s balíčkem se musí jmenovat `bridge_load_calculator_v9` – `main.py` i testy
> importují `bridge_load_calculator_v9` z nadřazené složky. Při přesunu nebo přejmenování
> složky je potřeba upravit importy.

## Struktura

```
bridge-load-calculator/
└── bridge_load_calculator_v9/
    ├── main.py            spouštěcí skript (GUI / --demo)
    ├── gui.py             grafické rozhraní (Tkinter)
    ├── comparison.py      porovnání MLC vs Ve po kontrolních řezech
    ├── beam_1d.py         1D analýza spojitého nosníku (Hermitovy prvky)
    ├── plate_fem.py       2D MKP model mostovky přes více polí (MITC4)
    ├── slab_fem.py        deska – 2D MKP s kosoúhlou sítí (šikmý most)
    ├── geometry.py        geometrie konstrukce a kontrolní řezy
    ├── vehicles.py        zatížení vozidel MLC (pásová, kolová)
    ├── prefabrikaty.py    načtení prefabrikátů z Prefabrikáty.xlsx
    ├── plotting.py        grafy
    ├── test_v9.py         ověřovací testy
    ├── Prefabrikáty.xlsx  tabulka typických prefabrikovaných nosníků
    ├── setup.bat, spustit_v9.bat, requirements.txt, README.txt
    └── __init__.py
```

## Použití z Pythonu

```python
from bridge_load_calculator_v9 import porovnani_zatizeni

cr = porovnani_zatizeni(
    typ="k", MLC="MLC80",
    L=[10.0, 14.0, 10.0],        # rozpětí polí [m]
    n=30, dist=30.5, Ve=80.0,
    N=8, beton="C35/45", Iy=0.0144, b=1.0, nu=0.2,
    d=0.55, ex=0.25,
)
```

Více v `main.py` (funkce `demo`).

## Verze

Tento repozitář obsahuje aktuální vývojovou verzi **v9**. Starší verze (v1–v8) zde nejsou;
rozdíly mezi verzemi shrnuje dokument `BLC_v5-v9_shrnuti.docx` (mimo repozitář).
