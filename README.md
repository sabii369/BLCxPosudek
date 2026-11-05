# BLC × Posudek PB – most → zatížení nosníku → posudek předpjatého nosníku

Jeden program: **model celého mostu** (BLC – 2D MKP, příčný roznos) spočítá vnitřní síly
od **g0** (vlastní tíha), **g − g0** (skladba vozovky a chodníků, svodidla, zábradlí)
a **q** (přejezd vybraného vozidla) na každém nosníku, vybere **nejzatíženější nosník**
a jeho obálky převezme jako zatížení **posudku předpjatého nosníku** (Posudek PB,
ČSN EN 1992-1-1/-2) – bez ručního zadávání zatížení.

## Spojený program (rychlý start)

```bat
setup.bat                :: jednou – instalace knihoven
spustit_posudek.bat      :: GUI (dvojklik; přetažením .toml se otevře soubor)
```

nebo `python -m blc_posudek` (GUI s příkladem), `python -m blc_posudek most.toml -o vystup`
(dávkově: most → posudek → HTML protokol + vnitřní síly mostu).

Prostředí je Posudek PB s novou první kartou:

| karta | obsah |
|---|---|
| **0 Most a zatížení (BLC)** | konstrukce mostu (N, b, d, spára, uložení, šikmost, k_v), vybavení (šířka chodníku vlevo/vpravo, tíha skladby chodníku a vozovky, zábradlí, svodidla, další liniová), **vozidlo** (Ve [t], MLC kolové / pásové, volitelně kolona), dynamický součinitel, ψ; tabulka nosníků, grafy průběhů a příčného rozdělení |
| 1–4 | materiály, průřez, nosník a předpětí, výztuž (Posudek PB) |
| **5 Zatížení a čas** | prostředí a časová osa; **vnější zatížení se nezadává** – je převzato z obálek posuzovaného nosníku (náhled kombinací) |
| 6, 7 | nastavení posouzení, výsledky (Posudek PB) |

- Rozpětí L0, délka L a beton jsou společné (karta 0 ↔ 1, 3), A a Iy nosníku se berou
  z průřezu (karta 2), γ_G, ξ a kombinace MSÚ z nastavení (karta 6).
- **F5** spočítá most (jen změnily-li se jeho vstupy) i posudek; HTML protokol obsahuje
  kapitolu „Zatížení z modelu mostu (BLC)“ s tabulkou nosníků a grafy: půdorys mostu se
  zatížením g0, g − g0 a vozidlem v poloze pro max M ve středu rozpětí a max V u podpory,
  vedle nich napětí v betonu po výšce průřezu ve středu rozpětí a u podpory.
- Soubor = vstup Posudku PB + sekce `[blc]`, vzor [`priklady/most_KA67_12.toml`](priklady/most_KA67_12.toml).
- Balíček `pb_posudek` je převzat z repa `sabii369/PB_posudek` (git subtree) – viz `CLAUDE.md`.

## Samostatné části

Upravená verze **Bridge Load Calculator (BLC)** počítá vnitřní síly g0, g − g0, q i samostatně
(`python -m blc --sily`, export TOML do Posudku PB) – viz [Vnitřní síly pro posudek](#vnitřní-síly-pro-posudek).

Původní funkce BLC zůstávají: posouzení přechodnosti vojenských vozidel (třídy MLC dle
NATO AEP-3.12.1.5) na silničních mostech a porovnání s výjimečnou zatížitelností **Ve**.
Program počítá spojitý nosník o více polích
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

## Vnitřní síly pro posudek

| stav | model |
|---|---|
| g0 | nosníky: každý nosník samostatně bez spolupůsobení (1D), g0 = A·γ_b; deska: 2D MKP |
| g − g0 | 2D MKP: skladba vozovky [kN/m²], skladba chodníků [kN/m²] (šířka chodníku vlevo a vpravo), svodidla, zábradlí [kN/m], výplň spáry |
| q | 2D MKP: obálka pojezdu vozidla Ve v ose vozovky, dynamický součinitel |

```bash
python -m blc --sily priklady/sily_KA67_12.toml --pb "../Posudek PB/examples/nosnik_KA67_12.toml"
```

Výstup (`vystupy/…`): `vnitrni_sily.json` (všechny nosníky a stavy), `souhrn.csv`,
`<nosník>_stavy.csv`, `zatizeni_PB.toml` (sekce `[zatizeni]` posudku – obálky kombinací
6.10a/b, char., častá, kvazistálá, nebo zatěžovací stavy), kopie vstupu posudku se zatížením
z BLC a grafy. V GUI sekce „Vnitřní síly pro posudek“. Z Pythonu:

```python
from blc import vnitrni_sily, Vybaveni, uloz_vysledky, zatizeni_pb_dict

vys = vnitrni_sily(L=11.4, N=10, b=1.0, Iy=0.014375, beton="C35/45", d=0.55, k_pod=2e6,
                   vybaveni=Vybaveni(chodnik_L=1.5, chodnik_P=0.75, g_chodnik=5.0,
                                     g_vozovka=2.6, g_zabradli=0.5, g_svodidla=0.6),
                   A_nosniku=0.3116, Ve=80.0)
o = vys.rozhodujici("M")                       # nejzatíženější nosník (MSÚ, vč. g0)
t = vys.tabulka(o, "q")                        # x, M_max, M_min, V_max, V_min
uloz_vysledky(vys, "vystupy/most", pb_vstup="nosnik_KA67_12.toml")
# parametrická studie bez souborů (Posudek PB):
#   d = pb_posudek.vstup.nacti_soubor("nosnik.toml")
#   d["zatizeni"] = zatizeni_pb_dict(vys, o, d["nosnik"]["L"])
#   model = pb_posudek.vstup.model_ze_slovniku(d)
```

Ověření s Posudkem PB: vstup `nosnik_KA67_12.toml` se zatížením z BLC se spočítá v obou
režimech (kombinace / zatěžovací stavy) se shodnými výsledky.
Podrobnosti (modely, konvence, napojení na posudek, omezení): [`docs/navod.md`](docs/navod.md), kap. 7.

## Rychlý start (Windows)

```bat
git clone https://github.com/sabii369/BLCxPosudek.git
cd BLCxPosudek

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
- `tests/test_vnitrni_sily.py` – g0 proti analytice (prostý i spojitý nosník, deska), rovnováha g − g0,
  vybavení, obálka q proti 1D, kombinace, export TOML pro posudek,
- `tests/test_blc_posudek.py` – spojený program: vstupy z posudku, výběr vozidla, zatížení z obálek,
  posudek, dávkový výpočet, GUI,
- `tests/test_regrese.py` – výsledky v kontrolních řezech proti uloženým referenčním hodnotám
  (`tests/referencni_hodnoty.json`). Po **záměrné** změně modelu se přegenerují
  příkazem `python tests/referencni_pripady.py` a změna se zkontroluje v `git diff`.

## Struktura

```
BLCxPosudek/
├── blc/                     balíček BLC
│   ├── __main__.py          spouštění (python -m blc: GUI / --demo)
│   ├── gui.py               grafické rozhraní (Tkinter)
│   ├── comparison.py        porovnání MLC vs Ve po kontrolních řezech (porovnani_zatizeni)
│   ├── vnitrni_sily.py      vnitřní síly g0, g−g0, q na nosnících (vnitrni_sily)
│   ├── stale_zatizeni.py    chodníky, vozovka, svodidla, zábradlí (Vybaveni)
│   ├── export_pb.py         JSON/CSV a export [zatizeni] do Posudku PB
│   ├── vstup_sily.py        vstupní soubor TOML pro python -m blc --sily
│   ├── plotting_sily.py     grafy vnitřních sil
│   ├── beam_1d.py           1D analýza spojitého nosníku (Hermitovy prvky), pojezd vozidel
│   ├── plate_fem.py         2D MKP model nosníků přes více polí (MITC4, spáry, šikmost)
│   ├── slab_fem.py          2D MKP model desky (kosoúhlá síť, šikmý most)
│   ├── geometry.py          geometrie konstrukce, okrajové podmínky, kontrolní řezy, třídy betonu
│   ├── vehicles.py          zatížení vozidel MLC (pásová, kolová)
│   ├── prefabrikaty.py      načtení tabulky prefabrikátů
│   ├── plotting.py          grafy
│   └── data/Prefabrikáty.xlsx
├── blc_posudek/             spojený program BLC × Posudek PB
│   ├── gui.py               okno posudku + karta 0 „Most a zatížení (BLC)“ (AplikaceMost)
│   ├── vypocet.py           most → zatížení nosníku z obálek → posudek (spocti, parametry_blc)
│   └── __main__.py          python -m blc_posudek (GUI / dávka)
├── pb_posudek/              Posudek PB (git subtree z sabii369/PB_posudek – needitovat zde)
├── priklady/                most_KA67_12.toml (spojený vstup), sily_KA67_12.toml (jen BLC)
├── tests/                   testy (pytest) + referenční hodnoty
├── docs/navod.md            uživatelský návod
├── setup.bat, spustit.bat   instalace a spuštění BLC (MLC vs Ve)
├── spustit_posudek.bat      spuštění spojeného programu
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
