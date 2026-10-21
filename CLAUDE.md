# BLC – Bridge Load Calculator (git repo sabii369/bridge-load-calculator)

Tato složka (`LOAD/BLC`) je **autoritativní git klon** repa `sabii369/bridge-load-calculator`.
Vývoj probíhá jen zde. Repo je samostatné: nenavazuje na historické verze v1–v9 ve složce `LOAD`
(ty jsou archiv, needitovat, neimportovat). Širší kontext projektu (SCIA_BLC, režim 2, výzkum)
je v `../CLAUDE.md` a `../VYZKUM_KONTEXT.md`.

Komunikace česky. Jednotky: kN, m, MPa; k_v v MN/m na 1 m podpory (interně kN/m).

## Příkazy (z kořene repa)
```bash
python -m pytest                      # všechny testy (~20 s)
python -m pytest tests/test_regrese.py
python -m blc --demo                  # konzolový výpočet + PNG do vystupy/demo (gitignore)
python -m blc                         # GUI (Tkinter)
python tests/referencni_pripady.py    # přegenerovat referenční hodnoty – JEN po záměrné změně modelu
```
- `PYTHONIOENCODING=utf-8` nastavuje `.claude/settings.json` (výstup obsahuje češtinu a řecká písmena).
- `--demo` si backend Agg nastaví sám; `MPLBACKEND=Agg` globálně nenastavovat (GUI volá `plt.show()`).
- Prostředí: Python 3.14, numpy, scipy, matplotlib, openpyxl, pytest.

## Struktura
- `blc/` balíček: `comparison.py` (`porovnani_zatizeni` – hlavní API), `beam_1d.py` (`Nosnik1D`),
  `plate_fem.py` (`DeskaMKP`, `KAPPA`), `slab_fem.py` (`DeskaSikmaMKP`, šikmá deska), `geometry.py` (`Konstrukce`),
  `vehicles.py`, `prefabrikaty.py` + `data/Prefabrikáty.xlsx`, `plotting.py`, `gui.py`, `__main__.py`.
- `tests/`: `test_nosnik_1d.py`, `test_deska_mkp.py`, `test_porovnani.py` (analytika, rovnováha, vlastnosti modelu),
  `test_regrese.py` + `referencni_pripady.py` + `referencni_hodnoty.json` (výsledky ověřeného stavu z 21. 10. 2026).
- `docs/navod.md` = uživatelský návod (metoda, výstupy, omezení) – při změně chování aktualizovat.
- Verze: `blc/__init__.py` `__version__` a `pyproject.toml` (držet shodně); označení verzí nepatří do názvů souborů ani komentářů – historii nese git.

## Modelová rozhodnutí (neměnit bez dohody)
- Spára nikdy nemá vlastní podporu; `delka_podpory = N·b` (deska: B).
- `Konstrukce.uloz`: `tvrde` (výchozí, u pružné podpory β_s = ∂w/∂s), `mekke`, `vetknuti` (k_rot); `beta_s_pevne=True` = zjednodušená vazba jen pro srovnání se SCIA.
- Mindlin κ = 5/6; m_x nad podporou lineární extrapolací; reakce pružné podpory = k_v·w; výchozí k_v = 2000, prázdné/0 = tuhá.
- Nosníky = pruhy 2D s h_ekv = (12·Iy/b)^(1/3); šikmé nosníkové mosty: kolmá čela, schodovitý posun.
- V šikmých konstrukcí vyhodnocovat z 2D obálky (prvek 0,0625 m), ne z kontrolních řezů.

## Pravidla práce
- Kódový styl: české názvy proměnných a funkcí, docstringy česky – držet se okolního kódu.
- Po každé změně spustit `python -m pytest`. Pokud změna modelu ZÁMĚRNĚ mění výsledky: přegenerovat
  referenční hodnoty, rozdíl v `referencni_hodnoty.json` ukázat uživateli a popsat v commitu.
- Práce ve větvích, commit jen na požádání; push na `origin` jen po potvrzení.
- Otevřené: integrace režimu 2 (Rezim2_prejezd) do GUI, sjednocení tabulky E betonu s EN 1992-1-1.
