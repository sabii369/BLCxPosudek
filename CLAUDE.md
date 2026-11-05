# BLC × Posudek – vnitřní síly pro posudek nosníku (git repo sabii369/BLCxPosudek)

Tato složka (`Desktop/BLCxPosudek`) je upravená verze BLC (Bridge Load Calculator) – vznikla
klonem `LOAD/BLC` (repo `sabii369/bridge-load-calculator`, remote `upstream`) a zachovává jeho
historii. Navíc počítá vnitřní síly od zatěžovacích stavů **g0, g − g0, q** na nosnících
a exportuje je jako vstup modulu **Posudek PB** (`Desktop/Posudek PB`, repo `sabii369/PB_posudek`),
který posuzuje nejzatíženější nosník. Modul je základ parametrické studie.
Širší kontext projektu (SCIA_BLC, režim 2, výzkum) je v `../LOAD/CLAUDE.md` a `../LOAD/VYZKUM_KONTEXT.md`.

Komunikace česky. Jednotky: kN, m, MPa; k_v v MN/m na 1 m podpory (interně kN/m).

## Příkazy (z kořene repa)
```bash
python -m pytest                      # všechny testy (~30 s)
python -m pytest tests/test_vnitrni_sily.py
python -m blc --sily priklady/sily_KA67_12.toml [--pb "../Posudek PB/examples/nosnik_KA67_12.toml"]
python -m blc --demo                  # konzolový výpočet MLC vs Ve + PNG do vystupy/demo (gitignore)
python -m blc                         # GUI (Tkinter) – sekce „Vnitřní síly pro posudek“
python tests/referencni_pripady.py    # přegenerovat referenční hodnoty – JEN po záměrné změně modelu
```
- `PYTHONIOENCODING=utf-8` nastavuje `.claude/settings.json` (výstup obsahuje češtinu a řecká písmena).
- `--demo` a `--sily` si backend Agg nastaví samy; `MPLBACKEND=Agg` globálně nenastavovat (GUI volá `plt.show()`).
- Prostředí: Python 3.14, numpy, scipy, matplotlib, openpyxl, pytest.
- Ověření s posudkem: `python -m pb_posudek <vystup>/<vstup>_BLC.toml -o <slozka>` spuštěné ve složce `Posudek PB`.

## Struktura
- `blc/` balíček: `comparison.py` (`porovnani_zatizeni` – MLC vs Ve), `beam_1d.py` (`Nosnik1D`, konstanty vozidla `VE_*`),
  `plate_fem.py` (`DeskaMKP`, `KAPPA`, `obalky_2D`), `slab_fem.py` (`DeskaSikmaMKP`), `geometry.py` (`Konstrukce`),
  `vehicles.py`, `prefabrikaty.py` + `data/Prefabrikáty.xlsx`, `plotting.py`, `gui.py` (`App`, `OknoSil`), `__main__.py`.
- Vnitřní síly pro posudek:
  - `stale_zatizeni.py` – `Vybaveni` (chodník L/P, g chodníku a vozovky [kN/m²], zábradlí, svodidla, `LiniovaZatizeni`) → plošky MKP,
  - `vnitrni_sily.py` – `vnitrni_sily(...)` → `VysledekSil` (`stavy` g0 / g-g0 / q jako `StavSil` na síti 2D,
    `tabulka(o, stav)`, `kombinace(o, druh)`, `souhrn()`, `rozhodujici()`), `Soucinitele`,
  - `export_pb.py` – `uloz_vysledky` (JSON, CSV, `zatizeni_PB.toml`, kopie vstupu PB), `toml_zatizeni_pb`,
    `zatizeni_pb_dict`, `vloz_do_vstupu_pb`,
  - `vstup_sily.py` – vstupní TOML (`priklady/sily_KA67_12.toml`), `plotting_sily.py` – grafy.
- `tests/`: `test_nosnik_1d.py`, `test_deska_mkp.py`, `test_porovnani.py`, `test_vnitrni_sily.py`,
  `test_regrese.py` + `referencni_pripady.py` + `referencni_hodnoty.json` (výsledky ověřeného stavu z 21. 10. 2026).
- `docs/navod.md` = uživatelský návod (kap. 7 = vnitřní síly pro posudek) – při změně chování aktualizovat.
- Verze: `blc/__init__.py` `__version__` a `pyproject.toml` (držet shodně); označení verzí nepatří do názvů souborů ani komentářů – historii nese git.

## Modelová rozhodnutí (neměnit bez dohody)
- Spára nikdy nemá vlastní podporu; `delka_podpory = N·b` (deska: B).
- `Konstrukce.uloz`: `tvrde` (výchozí, u pružné podpory β_s = ∂w/∂s), `mekke`, `vetknuti` (k_rot); `beta_s_pevne=True` = zjednodušená vazba jen pro srovnání se SCIA.
- Mindlin κ = 5/6; m_x nad podporou lineární extrapolací; reakce pružné podpory = k_v·w; výchozí k_v = 2000, prázdné/0 = tuhá.
- Nosníky = pruhy 2D s h_ekv = (12·Iy/b)^(1/3); šikmé nosníkové mosty: kolmá čela, schodovitý posun.
- V šikmých konstrukcí vyhodnocovat z 2D obálky (prvek 0,0625 m), ne z kontrolních řezů.
- **g0 u nosníků: každý nosník samostatně bez spolupůsobení** (1D, stejné uložení, k_v·b); u desky 2D MKP (h·γ).
- **g − g0: 2D MKP**; výplň spáry nesou samostatně sousední nosníky (½ + ½).
- **q: obálka pojezdu Ve** (2D, krok 0,25 m) v ose vozovky (mezi chodníky), × δ.
- Export do posudku: bez g0 (posudek si g0 počítá z průřezu, `obsahuje_vlastni_tihu = false`),
  x posudku = x od podpory + (L − L0)/2; výchozí režim „kombinace“ (6.10a, 6.10b, char, častá, kvazistálá).
- Výchozí ψ0 = ψ1 = 0,75, ψ2 = 0, γ_Q = 1,35 (TS) – pro Ve neověřeno, je to vstup.

## Pravidla práce
- Kódový styl: české názvy proměnných a funkcí, docstringy česky – držet se okolního kódu.
- Po každé změně spustit `python -m pytest`. Pokud změna modelu ZÁMĚRNĚ mění výsledky: přegenerovat
  referenční hodnoty, rozdíl v `referencni_hodnoty.json` ukázat uživateli a popsat v commitu.
- Commit jen na požádání; push na `origin` jen po potvrzení. `upstream` = původní BLC (jen fetch).
- Otevřené: další pohyblivá zatížení (Vn, Vr, LM1 …), hledání nejnepříznivější příčné polohy vozidla,
  tabulka M_max/M_min/V_max/V_min pro proměnné stavy v Posudku PB, parametrická studie.
