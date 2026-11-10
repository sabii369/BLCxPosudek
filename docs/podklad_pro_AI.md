# Podklad pro AI – jak funguje BLC × Posudek PB (parametrická studie)

Dokument je určený AI asistentovi, který bude v tomto repu připravovat a spouštět
**parametrickou studii**. Popisuje, co program počítá, jak data tečou mezi částmi, jaké
parametry lze měnit, co se kvůli nim musí přepočítat, kolik to trvá a kde jsou pasti.
Stav kódu: listopad 2026 (BLC 1.5.0, commit `4bb10f1`). Při změně chování programu
dokument aktualizovat.

Doplňkové zdroje: `CLAUDE.md` (pravidla repa, modelová rozhodnutí), `docs/navod.md`
(uživatelský návod, kap. 7 a 8), `../LOAD/VYZKUM_KONTEXT.md` (výzkumný kontext a ověření
BLC proti SCIA).

---

## 0. Pravidla práce (stručně)

- Komunikace **česky**; v kódu české názvy proměnných, funkcí a docstringů.
- Jednotky: kN, m, MPa; t pro tíhu vozidla; k_v v **MN/m na 1 m podpory** (interně kN/m/m);
  v posudku průřez a výztuž v **mm / mm²**.
- `pb_posudek/` je **git subtree** z repa Posudek PB – **needitovat** zde. Rozšíření dělat
  v `blc_posudek/` (dědičnost, přepsání metod) nebo ve vlastních skriptech studie.
- **Modelová rozhodnutí** v `CLAUDE.md` neměnit bez dohody s uživatelem (g0 nosníků bez
  spolupůsobení, g − g0 a q na 2D MKP, spára bez podpory, export bez g0 …).
- Skripty studie a jejich výstupy dávat mimo zdrojový kód; složky `vystupy/`, `vystup/`,
  `vystup_*/` jsou v `.gitignore`.
- Po změně kódu `python -m pytest` (~40 s). Commit jen na požádání, push jen po potvrzení.
- Spouštět z kořene repa (`C:\Users\OEM\Desktop\BLCxPosudek`), `PYTHONIOENCODING=utf-8`
  (výstupy obsahují češtinu a řecká písmena). `MPLBACKEND=Agg` globálně nenastavovat;
  ve skriptu bez GUI stačí `matplotlib.use("Agg")` před kreslením.

---

## 1. Co program dělá – jedním odstavcem

Spojený program `blc_posudek` vezme **jeden vstupní soubor** (vstup Posudku PB + sekce
`[blc]` s popisem mostu), spočte na **2D MKP modelu celého mostu** (BLC) vnitřní síly všech
nosníků od zatěžovacích stavů **g0, g − g0, q_ch (chodci), q (vozidlo)**, vybere
**nejzatíženější nosník**, z jeho obálek sestaví **kombinace podle ČSN EN 1990** a předá je
modulu **Posudek PB**, který posoudí předpjatý nosník (ztráty předpětí, časová osa, MSP,
MSÚ) a vrátí **využití η** každého posudku. Volitelně místo posouzení hledá
**zatížitelnost** – tíhu vozidla Ve [t], při které je η = 100 % v každém mezním stavu.

```
vstup .toml (posudek + [blc])
   │  blc_posudek.vypocet.nacti()
   ▼
parametry_blc(d) ──► blc.vnitrni_sily(...) ──► VysledekSil  (2D MKP celého mostu)
                       g0 (1D, každý nosník zvlášť), g−g0 (2D), q_ch (2D obálka), q (2D obálka pojezdu)
   │  vyber_nosnik(vys, d)  → o  (index posuzovaného nosníku, nejzatíženější podle MSÚ 6.10)
   ▼
data_pro_posudek(vys, d, o) = kopie d bez [blc] + [zatizeni] z obálek nosníku o
   │  (blc.export_pb.zatizeni_pb_dict: kombinace 6.10a, 6.10b, char, častá, kvazistálá, bez g0)
   ▼
pb_posudek.vstup.model_ze_slovniku(...) → NosnikPB ; .spocitej()
   ▼
model.protokol.posudky  → [VysledekPosudku(mezni_stav, nazev, faze, kombinace, x, E_d, R_d, vyuziti …)]
   │
   └─ (volitelně) blc_posudek.zatizitelnost.zatizitelnost(d) → Ve pro η = 1 každého posudku
```

---

## 2. Mapa kódu

| Soubor | Obsah / klíčové funkce |
|---|---|
| `blc_posudek/vypocet.py` | **řídicí vrstva**: `nacti`, `VYCHOZI_BLC`, `parametry_blc(d)`, `vlastnosti_prurezu(d)`, `nastaveni_posudku(d)`, `vyber_nosnik(vys, d)`, `zatizeni_z_blc(vys, d, o)`, `data_pro_posudek(vys, d, o)`, `spocti(d, vys=None, o=None)`, `kapitola_blc`, `uloz_protokol_most(model, adr)` |
| `blc_posudek/zatizitelnost.py` | `zatizitelnost(d, vys=None, o=None, tol=1e-3)` → `VysledekZatizitelnosti`; `vys_pro_Ve(vys, Ve)` (přeškálování q); `klic_posudku(p)` |
| `blc_posudek/__main__.py` | dávka / CLI (`python -m blc_posudek soubor.toml -o slozka [--zatizitelnost]`) |
| `blc_posudek/gui.py`, `grafy_most.py` | GUI (`AplikaceMost`, karta 0 „Most a zatížení“), grafy mostu do protokolu |
| `blc/vnitrni_sily.py` | `vnitrni_sily(...)` → `VysledekSil`; `Soucinitele`; `StavSil`; `polohy_q` |
| `blc/dynamicky_soucinitel.py` | `dynamicky_soucinitel(vozidlo, dyn)` → (δ, zdroj) podle ČSN 73 6222, kap. 8 |
| `blc/export_pb.py` | `toml_zatizeni_pb`, `zatizeni_pb_dict`, `uloz_vysledky` (JSON/CSV/TOML) |
| `blc/stale_zatizeni.py` | `Vybaveni` (chodníky, skladby, zábradlí, svodidla), `LiniovaZatizeni` |
| `blc/geometry.py` | `Konstrukce` (geometrie, uložení, šikmost, validace), `E_betonu` (Ecm z třídy) |
| `blc/plate_fem.py` | `DeskaMKP` – 2D MKP (MITC4, Mindlin κ = 5/6) z podélných pruhů; `obalky_2D` |
| `blc/slab_fem.py` | `DeskaSikmaMKP` – deska (i šikmá) |
| `blc/beam_1d.py` | `Nosnik1D` (1D spojitý nosník), generátory poloh vozidel `stavy_Ve`, `stavy_MLC`; konstanty vozidla `VE_*` |
| `blc/vehicles.py` | vozidla MLC (kolová / pásová) |
| `blc/comparison.py` | `porovnani_zatizeni` – původní účel BLC: porovnání účinků MLC vs Ve (není součástí posudku) |
| `blc/prefabrikaty.py` | katalog prefabrikátů (I-62, I-67, I-73, KA-61, KA-67, KA-73: L, b, Iy, spára) |
| `pb_posudek/` | Posudek PB (subtree): `vstup.py` (`model_ze_slovniku`), `model.py` (`NosnikPB`, `Nastaveni`, `Faze`), `protokol.py` (`VysledekPosudku`), `msu.py`, `ztraty.py`, `kabel.py`, `prurez.py`, `materialy.py` |
| `priklady/most_KA67_12.toml` | **jediný kompletní vzorový vstup** spojeného programu (10 × KA-67/12, Ve 80 t) |
| `tests/test_blc_posudek.py` | testy spojeného programu – dobré ukázky volání API |

---

## 3. Vstupní data

Jeden slovník `d` (TOML/JSON) = vstup Posudku PB + sekce `[blc]`. Sekce `[zatizeni]` se
**nezadává** – vytvoří ji program z obálek posuzovaného nosníku.

### 3.1 Sekce posudku (sdílené i jen posudkové)

| Sekce | Klíče (výběr) | Použije |
|---|---|---|
| `[projekt]` | `nazev`, `popis` | protokol |
| `[beton]` | `trida` (např. "C35/45"), `cement` ("N"/"R"/"S"), `objemova_tiha` (25), `Ecm` (volitelně) | **oba** (BLC: E = Ecm třídy nebo `Ecm`, γ_b pro g0) |
| `[predpinaci_vyztuz]` | `typ`, `fpk`, `Ep`, `trida_relaxace` …, `taznost` (neoslabená ε_uk [‰], 35; sklon zpevnění), **`taznost_oslabena`** (ε_uk,red [‰] od koroze, volitelně; 0 < ε_uk,red ≤ ε_uk) | posudek |
| `[betonarska_vyztuz]` | `typ` ("B500B"), `fyk` … | posudek |
| `[prurez]` | `obrys` [[y, z] mm], `otvory`, nebo `vrstvy`, nebo `b`+`h` | **oba** (BLC: A a Iy brutto, je-li `prurez_z_posudku = true`) |
| `[nosnik]` | `L` (délka nosníku), **`L0` (rozpětí = osa ložisek)**, `predpeti` ("dodatecne"/"predem…"), `charakteristiky` ("brutto"/"idealni"), `pocet_rezu` (41), `pocet_napinani`, `postup_napinani` | **oba** (BLC: rozpětí = L0) |
| `[[kabel]]` | `nazev`, `pocet_lan`, `geometrie` ("parabola"/"polygon"/"primka"), `body` [[x m, z mm]], `polomery`, `z_L`/`z_S`/`z_P`, `sigma_max`, `napinani`, `mu`, `k`, `pokluz`, `d_kanalku` | posudek |
| `[[smykova_vyztuz]]` | `Asw` [mm²], `s` [mm], `alpha`, `od`, `do` | posudek |
| `[[vyztuz]]` | `z` [mm], `As` [mm²], `nazev` | posudek |
| `[prostredi]` | `RH` [%], `t_s` [dny] | posudek |
| `[casova_osa]` | `t0` (vnesení předpětí), `t_provoz`, `t_konec`, **`t_akt`** (aktuální stáří, volitelně) [dny] | posudek |
| `[predem]` | `eta_p1`, `alpha1`, `alpha2` … (jen předem předpjaté) | posudek |
| `[posouzeni]` | pole `Nastaveni` (`pb_posudek/model.py`): `gamma_G` 1,35, `gamma_G_inf` 1,0, `xi` 0,85, `kombinace_msu` "6.10ab"/"6.10", `k1_nap`, `k2_nap`, `k7`, `k8`, `k1`, `k2`, `k5`, `tah_predpeti`, `tah_provoz`, `dekomprese`, `pruhyb_limit`, `hlavni_napeti` … | posudek; **γ_G, γ_G,inf, ξ i BLC** (kombinace) |
| `[degradace]` | `oslabeni_predpinaci`, `oslabeni_betonarske`, `oslabeni_smykove` [%] (0 až < 100) | posudek |

Souřadnice posudku: x [m] od **levého konce nosníku** (ložiska v (L − L0)/2 od konců),
z [mm] **od spodního líce** průřezu.

### 3.2 Sekce `[blc]` – model mostu a předání zatížení

Výchozí hodnoty jsou v `blc_posudek/vypocet.py: VYCHOZI_BLC` (chybějící klíč = výchozí).

| Klíč | Výchozí | Jednotka | Význam |
|---|---|---|---|
| `typ_konstrukce` | "nosniky" | – | "nosniky" \| "deska" |
| `N` | 10 | – | počet nosníků |
| `b` | 1.0 | m | šířka nosníku = rozteč (deska: šířka desky) |
| `prurez_z_posudku` | true | – | A, Iy nosníku z `[prurez]` (brutto); false → `A_nosniku` [m²], `Iy` [m⁴] |
| `h` | – | m | tloušťka desky (jen deska) |
| `nu` | 0.2 | – | Poissonovo číslo |
| `d` | 0.5 | m | účinná výška (řez pro V v d od podpory; musí platit 2d < L0) |
| `spara`, `b_s`, `Iy_s`, `beton_s`, `g_spary` | false | m, m⁴, –, kN/m | podélné spáry mezi nosníky (kloubově připojené, bez vlastní podpory) |
| `alfa`, `sikmost` | 90, "prava" | °, – | šikmost 90 (kolmý) … 165; "prava"/"leva" |
| `k_v` | 2000 | MN/m/m | svislá tuhost podpory na 1 m podepřené délky (N·b); 0/prázdné = tuhá |
| `uloz` | "tvrde" | – | "tvrde" \| "mekke" \| "vetknuti" (+ `k_rot` [MNm/rad/m]) |
| `spoj` | "kloub" | – | spojení nosníků bez spáry: "kloub" \| "deska" (tuhé) |
| `chodnik_L`, `chodnik_P` | 1.5, 1.5 | m | šířky chodníků u okrajů mostovky (vozovka mezi nimi) |
| `g_chodnik`, `g_vozovka` | 5.0, 2.6 | kN/m² | skladby chodníku a vozovky |
| `g_zabradli`, `g_svodidla` | 0.5, 0.6 | kN/m | každá strana (pásy 0,2 m) |
| `[[blc.liniova]]` | – | – | další liniová: `nazev`, `g` [kN/m], `y` [m od levého okraje], `sirka` [m] |
| `q_chodnik` | 3.0 | kN/m² | chodci (0 = bez stavu q_ch) |
| `vozidlo` | "Ve" | – | "Ve" \| "MLC_k" \| "MLC_p" |
| `Ve` | 80 | t | tíha vozidla Ve |
| `MLC`, `dist` | "MLC80", – | –, m | třída MLC; `dist` = rozestup v koloně (prázdné = jedno vozidlo) |
| `dyn` | vynechat | – | dynamický součinitel δ (násobí q); vynechaný = ČSN 73 6222, kap. 8: Ve **1,05** (čl. 8.4), MLC 1,0 + varování (`blc/dynamicky_soucinitel.py`); použitý `vys.dyn`, zdroj `vys.dyn_zdroj` |
| `y_vozidla` | osa vozovky | m | příčná poloha osy vozidla od levého okraje |
| `roznos`, `t_voz` | true, 0.0 | –, m | roznos plošky kola do střednice (h_ekv + 2·t_voz) |
| `krok` | 0.25 | m | krok poloh vozidla pro obálku |
| `ex` | 0.125 | m | velikost prvku MKP (viz kap. 9) |
| `vystup` | "auto" | – | posuzovaný nosník: "auto" = nejzatíženější, jinak popisek "N1" … |
| `kriterium` | "M" | – | výběr nejzatíženějšího: "M" \| "M-" \| "V" (MSÚ 6.10 vč. g0) |
| `rezim` | "kombinace" | – | předání: "kombinace" \| "zatezovaci_stavy" |
| `gamma_Q`, `psi0`, `psi1`, `psi2` | 1.35, 0.75, 0.75, 0.0 | – | doprava q (hodnoty TS – **pro Ve neověřeno**, je to vstup) |
| `gamma_Qch`, `psi0_ch`, `psi1_ch`, `psi2_ch` | 1.35, 0.75, 0.75, 0.0 | – | chodci |
| `t_vneseni` | (t_provoz) | dny | od kdy působí kvazistálá kombinace (g − g0 …) jako stálá |
| `t_stale` | (t_vneseni) | dny | jen režim "zatezovaci_stavy" |
| `zatizitelnost` | false | – | true = místo posouzení výpočet zatížitelnosti |

---

## 4. Model mostu (BLC) – co se počítá

`vnitrni_sily(**parametry_blc(d))` → `VysledekSil` (`vys`). `parametry_blc` bere rozpětí
`L0` z `[nosnik]` (**vždy jedno pole** – spojený program řeší prostý nosník), E z třídy
betonu, A a Iy z průřezu posudku, γ_G/γ_G,inf/ξ z `[posouzeni]`, zbytek z `[blc]`.

### 4.1 Geometrie a MKP

- Mostovka z **N podélných pruhů** (nosník = pruh šířky b s náhradní tloušťkou
  h_ekv = (12·Iy/b)^(1/3)); volitelně pruhy spár mezi nimi. MITC4, Mindlin (κ = 5/6),
  stupně volnosti w, βx, βy. Šířka mostovky B = N·b + (N − 1)·b_s; osa nosníku k:
  y_k = k·(b + b_s) + b/2.
- Podpory liniové přes šířku nosníku (spára nikdy nemá podporu, délka podpory = N·b).
  Pružná podpora k_v; reakce = k_v·w. Uložení „tvrdé“: β_s = ∂w/∂s u pružné podpory.
- Šikmé nosníkové mosty: kolmá čela nosníků, schodovitý posun podpor
  x0(y) = −s·(y − B/2)·cot(180° − α); x výstupu se měří **od osy podpory daného nosníku**.
- Výsledky jsou na podélné síti 2D modelu (uzly `vys.xs`), výslednice M, V(x⁻), V(x⁺) na
  každém nosníku (deska: na pás 1 m). Znaménka: **kladný M táhne dolní vlákna, V = dM/dx**.

### 4.2 Zatěžovací stavy (`vys.stavy`)

| Stav | Obsah | Model |
|---|---|---|
| `g0` | vlastní tíha nosníku g0 = A·γ_b [kN/m] | **každý nosník samostatně, bez spolupůsobení** (1D, stejné uložení, k_v·b); deska: 2D MKP h·γ_b |
| `g-g0` | skladby vozovky a chodníků, zábradlí, svodidla, další liniová; výplň spáry | 2D MKP (příčný roznos); výplň spáry nesou sousední nosníky ½ + ½ samostatně |
| `qch` | chodci q_chodnik [kN/m²] | 2D MKP – obálka: chodníky rozdělené na úseky 0,5 m, max = Σ kladných, min = Σ záporných účinků |
| `q` | jedno vozidlo (Ve nebo MLC) × δ (Ve: 1,05 podle ČSN 73 6222, čl. 8.4) | 2D MKP – **obálka pojezdu** (max/min přes polohy) |

**Vozidlo Ve** (`blc/beam_1d.py`): 9 náprav po 1,5 m, celková tíha 10·Ve kN (náprava
10·Ve/9 kN), ploška kola 0,15 m × 1,2 m, osová vzdálenost stop 1,5 m (šířka vozidla 2,7 m).
Ploška se zvětší o roznos h_ekv (+ 2·t_voz). Polohy: mřížka s krokem `krok` + polohy, kdy
hrana zatížení padne do řezu d od podpory; vjezd i sjezd (nápravy mimo most se oříznou).
Vozidlo stojí v **jediné příčné poloze** (osa vozovky mezi chodníky nebo `y_vozidla`);
nejnepříznivější příčná poloha se nehledá. Přesah vozovky → jen varování (`vys.varovani`).

### 4.3 Kombinace a výběr nosníku

`Soucinitele.gama_psi(skupina, druh)`; účinek kombinace = Σ γ·ψ·E, chodci a doprava
působí současně; stálé max(γ_sup·G, γ_inf·G):

| Kombinace | G (g0 + g − g0) | q_ch | q |
|---|---|---|---|
| char | 1 | 1 | 1 |
| casta | 1 | ψ1,ch | ψ1 |
| kvazistala | 1 | ψ2,ch | ψ2 |
| 6.10a | γ_G | γ_Qch·ψ0,ch | γ_Q·ψ0 |
| 6.10b | ξ·γ_G | γ_Qch | γ_Q |
| 6.10 | γ_G | γ_Qch | γ_Q |

`vyber_nosnik(vys, d)`: `vystup` = popisek → ten nosník; jinak `vys.rozhodujici(kriterium)`
= max M_Ed ("M"), max −M_Ed,min ("M-") nebo max |V_Ed| ("V") z kombinace **6.10 včetně g0**.
Pozor: výběr podle M nemusí dát nosník rozhodující pro smyk (kap. 9).

### 4.4 Užitečné metody `VysledekSil`

- `vys.popisky` (["N1", …]), `vys.n_vyst`, `vys.vyst.y` (osy), `vys.popis`, `vys.varovani`, `vys.kontrola` (ΣF, ΣR).
- `vys.tabulka(o, "q")` → `TabulkaSil(x, M_max, M_min, V_max, V_min)` (x od osy 1. podpory nosníku).
- `vys.kombinace(o, "6.10a", vcetne_g0=False)` → obálka kombinace.
- `vys.souhrn()` → po nosnících `M_<stav>`, `Mmin_<stav>`, `V_<stav>` (max |V|), `M_Ed`, `Mmin_Ed`, `V_Ed`.
- `vys.extremy_kombinace(druh)` → po nosnících max/min M (s x), max/min V.
- `polohy_q(vys, o)` → rozhodující polohy vozidla (max M ve středu, max V v řezu d).

---

## 5. Předání do posudku (`blc/export_pb.py`)

`zatizeni_z_blc(vys, d, o)` → sekce `[zatizeni]` (slovník):

- `zpusob = "kombinace"` (výchozí): obálky **6.10a, 6.10b** (nebo 6.10 podle
  `[posouzeni] kombinace_msu`), **char, častá, kvazistálá** s M_max, M_min, V_max, V_min.
- **Bez g0** (`obsahuje_vlastni_tihu = false`) – posudek si g0 počítá sám z průřezu
  (A·γ_b) a přičítá ho s γ_G (6.10a, 6.10) a ξ·γ_G (6.10b).
- **x posudku = x od podpory + (L − L0)/2**; na převislých koncích nuly. Dvojice x nad
  vnitřní podporou se sloučí (u prostého nosníku nenastává).
- `t_vneseni` z `[blc]`: od tohoto stáří působí kvazistálá kombinace jako stálé zatížení
  (dotvarování, ztráty); bez zadání = t_provoz.
- Režim `"zatezovaci_stavy"`: g − g0 jako stálý stav, q_ch a q jako proměnné (skupina "BLC",
  V s větší absolutní hodnotou) – kombinace sestaví posudek sám. Pro studii stačí výchozí.

---

## 6. Posudek PB (`pb_posudek`)

`NosnikPB.spocitej()`: síť (`pocet_rezu` řezů po délce L), průřez (brutto/ideální),
kabely a okamžité ztráty (tření, pokluz, postupné napínání), fáze a dlouhodobé ztráty
(dotvarování, smršťování, relaxace), vnitřní síly, MSP, hlavní napětí, průhyb, MSÚ ohyb
(nelineární), MSÚ smyk, (kotvení lan u předem předpjatých), křehký lom. Statické schéma:
**prostý nosník**, předpětí jen primární účinky; spřažená deska se neuvažuje.

### 6.1 Fáze (`model.faze`)

| Fáze | t | Zatížení |
|---|---|---|
| Vnesení předpětí | t0 | g0 (+ kvazistálá, je-li t_vneseni ≤ t0) |
| Vnesení ostatních stálých zatížení | t_vneseni (je-li > t0) | g0 + kvazistálá kombinace |
| Uvedení do provozu | t_provoz | provoz: char, častá, kvazistálá, MSÚ |
| Aktuální stáří (volitelně) | t_akt | provoz |
| Konec životnosti | t_konec | provoz |

Proměnná zatížení (doprava, chodci) jen v provozních fázích (t ≥ t_provoz). Oslabení
korozí `[degradace]` se uplatní v provozních fázích od t_akt (bez t_akt jen na konci
životnosti): předpínací výztuž → P = σ_p·A_p·(1 − ρ_p) a A_p v MSÚ; A_s v MSÚ; A_sw ve
smyku. Ztráty a průřezové charakteristiky se počítají pro neoslabenou výztuž. Ve stejných
fázích platí `taznost_oslabena`: mezní přetvoření předpínací výztuže v MSÚ (ohyb) ε_ud,red =
0,9·ε_uk,red, pracovní diagram (sklon zpevnění z neoslabené `taznost`) se nemění, takže výztuž
nedosáhne k·f_pd a M_Rd klesne, jakmile rozhoduje výztuž. Pozor: samotné snížení `taznost`
dává strmější zpevnění a vyšší M_Rd – pro vliv koroze použít `taznost_oslabena`.
Je-li ε_ud,red ≤ počátečnímu přetvoření výztuže ε_p0, výpočet skončí chybou (ValueError).

### 6.2 Výsledky – `model.protokol.posudky`

Seznam `VysledekPosudku`: `mezni_stav` ("MSP"/"MSÚ"), `nazev`, `faze`, `kombinace`,
`x` [m od konce nosníku, None = globální], `E_d`, `R_d`, `jednotka`, **`vyuziti` (η)**,
`vyhovuje` (η ≤ 1), `skupina`. Jednoznačný klíč: `klic_posudku(p)` =
`(mezni_stav, nazev, faze, kombinace)`.

Posudky pro vzorový příklad (38 položek; počet závisí na kabelech a fázích):

| MS | Posudek | Fáze / kombinace | Závisí na q? |
|---|---|---|---|
| MSP | Napínací napětí – každý kabel | napínání | ne |
| MSP | Napětí po zakotvení σ_pm0 – každý kabel | po vnesení předpětí | ne |
| MSP | Tlakové / Tahové napětí v betonu | Vnesení předpětí, Vnesení ost. stálých (stálá) | ne |
| MSP | Tlakové / Tahové napětí v betonu | provoz, charakteristická | ano |
| MSP | Dekomprese | provoz, častá | ano |
| MSP | Napětí v předpínací výztuži | provoz, charakteristická | jen kabely v tažené oblasti (ve vzoru rozhoduje horní kabel K1 → ne) |
| MSP | Hlavní tahové napětí | provoz, charakteristická | ano |
| MSP | Průhyb (kvazistálá kombinace) | konec životnosti | jen přes ψ2 |
| MSÚ | Ohybová únosnost | provoz, MSÚ – základní | ano |
| MSÚ | Smyková únosnost, Únosnost tlakové diagonály | provoz, MSÚ – základní | ano |
| MSÚ | Minimální smyková výztuž | provoz | ne |
| MSÚ | Křehký lom – redukované předpětí (– min. výztuž) | uvedení do provozu, častá | ano, **η s q klesá** |

Vlastnosti η důležité pro studii:
- **Tahové napětí** má η = 0, dokud v průřezu nevznikne tah → nehladký průběh v Ve.
- **Křehký lom** – η klesá s rostoucím zatížením (nevyhovuje jen při malém zatížení).
- Část posudků na zatížení dopravou **nezávisí** (napínání, výstavba, minimální výztuž) –
  ve studii zatížitelnosti je oddělovat (dělá to `zatizitelnost`).
- **Vzorový příklad KA-67/12 celkově NEVYHOVUJE nezávisle na vozidle**: napínací napětí
  η = 1,05 (všechny kabely), tlak v betonu při vnesení předpětí η = 1,114. Na dopravě
  závislé posudky mají při Ve 80 t η ≤ 0,46 (MSP) a ≤ 0,32 (MSÚ). Dávka proto končí kódem 1.

### 6.3 Upozornění – `model.protokol.upozorneni`

Seznam textů pro uživatele, které **nejsou posudky** a výsledek (VYHOVUJE / NEVYHOVUJE,
η, zatížitelnost) neovlivňují. Zobrazují se v souhrnu HTML protokolu, u příslušné kapitoly,
v GUI (pruh pod kartami na kartě Výsledky) a ve výpisu dávky (`! Upozornění: …`).

- **Mez lineárního dotvarování** (7.2(3)): ve fázích po vnesení předpětí (kombinace stálá,
  v provozu kvazistálá) se porovná největší tlak v betonu s k2·f_ck(t) (k2 = 0,45,
  `[posouzeni] k2`). V protokolu je to krok výpočtu (poměr |σc|/(k2·f_ck(t))); při
  překročení vznikne upozornění, že je třeba uvažovat nelineární dotvarování (program
  ztráty a průhyb počítá s lineárním, nelineární jen od předpětí při vnesení, k_σ > 0,45).
  Ve vzoru překročeno: vnesení ostatních stálých 19,11 MPa a uvedení do provozu 18,52 MPa
  > 15,75 MPa. Závisí na q jen přes ψ2 (výchozí 0 → ne).
- Ve studii ukládat počet / texty upozornění ke každému běhu – jinak se tato informace ztratí.

---

## 7. Zatížitelnost (`blc_posudek/zatizitelnost.py`)

`res = zatizitelnost(d, vys=None, o=None)`; jen pro `vozidlo = "Ve"`.

1. Most se spočte **jednou** s referenčním Ve (z `[blc] Ve`). Účinky vozidla jsou v Ve
   lineární → pro jiné Ve se stav q přeškáluje (`vys_pro_Ve(vys, Ve)`), polohy se nemění.
   δ násobí Ve; g0, g − g0, q_ch zůstávají. **Posuzovaný nosník je pevný** (vybraný při ref. Ve).
2. Pro každé zkoušené Ve se spočte celý posudek (jeden výpočet dá η všech posudků).
3. Rozsah: od Ve_ref se zvětšuje (odhad z lineárního průběhu, nejvýše 4× za krok, max
   64·Ve_ref), dokud všechny rostoucí posudky nedosáhnou η ≥ 1.
4. Pro každý posudek regula falsi (Illinois) se sdílenými výpočty; přesnost |η − 1| ≤ 1e-3
   nebo interval ≤ 0,01 t.

Výsledek `VysledekZatizitelnosti`: `res.Ve` (= nejmenší Ve přes posudky), `res.minimum("MSÚ")`,
`res.minimum("MSP")`, `res.posudky` (`PosudekZat`: `klic`, `Ve`, `stav`, `eta_ref`, `eta_0`),
`res.n_vypoctu`, `res.Ve_max`, `res.poznamky`, `res.model` (posudek při Ve = zatížitelnost),
`res.vys`, `res.o`. Stavy: `"Ve"` (nalezeno), `"neomezuje"` (do Ve_max η < 1),
`"nezavisi_ok"` / `"nezavisi_nok"` (nezávisí na Ve), `"klesa"` (η klesá s Ve),
`"bez_vozidla"` (nevyhovuje už při Ve = 0).

Vzorový příklad: Ve = **228,3 t** (MSÚ smyková únosnost, konec životnosti), 27 výpočtů
posudku, ~13 s; MSP rozhoduje hlavní tahové napětí 317,7 t; ohyb MSÚ ~493 t; 8 posudků
nevyhovuje nezávisle na Ve (napínání, tlak při vnesení předpětí).
Upozornění (kap. 6.3) do zatížitelnosti nevstupují; `res.model.protokol.upozorneni` platí
pro posudek při Ve = zatížitelnost.

---

## 8. Spouštění

### 8.1 Příkazová řádka

```bash
python -m blc_posudek priklady/most_KA67_12.toml -o vystupy/zakladni
```

```bash
python -m blc_posudek priklady/most_KA67_12.toml -o vystupy/zat --zatizitelnost
```

Výstup: `protokol.html` (+ `obrazky/`), `vysledky.json` (`posudky` jako slovníky,
`x`, `faze` s P a σ_p), složka `most/` (`vnitrni_sily.json`, `souhrn.csv`, `<N>_stavy.csv`,
`zatizeni_PB.toml`, grafy). CSV: oddělovač `;`, desetinná čárka. Návratový kód: 0 = vše
vyhovuje, 1 = něco nevyhovuje, 2 = chyba vstupu. Pro studii s mnoha běhy je CLI pomalé
(protokol + grafy ~9 s na běh) – používat Python API.

### 8.2 Python API – rychlá cesta bez protokolu

```python
import copy
from blc_posudek.vypocet import nacti, parametry_blc, vyber_nosnik, data_pro_posudek
from blc_posudek.zatizitelnost import zatizitelnost, vys_pro_Ve, klic_posudku
from blc.vnitrni_sily import vnitrni_sily
from pb_posudek.vstup import model_ze_slovniku

ZAKLAD = nacti("priklady/most_KA67_12.toml")

def most(d):
    """Model mostu (BLC) – drahá část (~1,6 s)."""
    return vnitrni_sily(**parametry_blc(d))

def posudek(d, vys, o=None):
    """Posudek nosníku o (výchozí podle [blc] vystup/kriterium) – ~0,35 s."""
    o = vyber_nosnik(vys, d) if o is None else o
    m = model_ze_slovniku(data_pro_posudek(vys, d, o))
    m.spocitej()
    return o, m

d = copy.deepcopy(ZAKLAD)                 # nikdy neměnit ZAKLAD na místě
d["blc"].update(N=8, k_v=1000.0)
vys = most(d)
o, m = posudek(d, vys)
eta = {klic_posudku(p): p.vyuziti for p in m.protokol.posudky}
# max přes všechny MSÚ – včetně křehkého lomu (η klesá s q) a min. smykové výztuže
max_msu = max(p.vyuziti for p in m.protokol.posudky if p.mezni_stav == "MSÚ")
upozorneni = list(m.protokol.upozorneni)   # např. překročená mez lineárního dotvarování
```

Balíčky nejsou nainstalované (`pip install -e .` neproběhlo) – kód funguje při spuštění
z kořene repa (`python -c …`, `python -m …`). Skript uložený jinde (např. `studie/beh.py`)
potřebuje `PYTHONPATH=.` při spuštění z kořene, nebo na začátku
`sys.path.insert(0, r"C:\Users\OEM\Desktop\BLCxPosudek")`; relativní cesty (`priklady/…`)
se vztahují k aktuální složce.

- `spocti(d, vys=None, o=None)` (z `vypocet.py`) dělá totéž + kapitolu BLC, polohy
  vozidla a obrázky do protokolu (~1,1 s navíc); potřebné jen pro `uloz_protokol_most`.
- Protokol pro vybrané případy: `vys, o, m = spocti(d, vys, o); uloz_protokol_most(m, "vystupy/…")`
  (+ `blc.export_pb.uloz_vysledky(vys, slozka, vystup=vys.popisky[o])` pro síly mostu).
- Zatížitelnost s již spočteným mostem: `res = zatizitelnost(d, vys=vys, o=o)`.
- Jiná tíha Ve bez přepočtu MKP: `posudek(d, vys_pro_Ve(vys, 120.0), o)` (q ∝ δ·Ve).
- Závislost posudků na dopravě: porovnat η z `posudek(d, vys_pro_Ve(vys, 0.0), o)` a z `vys`.

### 8.3 Co se musí přepočítat při změně parametru

Most (BLC) je drahý; posudek levný. Most přepočítat, právě když se změní
`parametry_blc(d)` – stejný klíč jako v GUI: `repr(sorted(parametry_blc(d).items()))`
(lze použít pro cache).

| Změna | Přepočet mostu (BLC)? | Pozn. |
|---|---|---|
| `[blc]` geometrie, uložení, k_v, šikmost, vybavení, chodci, vozidlo, `krok`, `ex` | **ano** | |
| `[blc] Ve` (při vozidle Ve), `dyn` | ne nutně | `vys_pro_Ve` (lineární přeškálování q) |
| `[blc] gamma_Q`, `psi*`, `[posouzeni] gamma_G`, `gamma_G_inf`, `xi` | jen kombinace | MKP se nemění; `vys2 = copy.copy(vys); vys2.soucinitele = Soucinitele(...)` (všechna pole, `blc.vnitrni_sily.Soucinitele`), pak `posudek(d, vys2, o)`; posudek bere γ_G a ξ pro g0 z `d["posouzeni"]` – měnit obojí shodně |
| `[blc] vystup`, `kriterium`, `rezim`, `t_vneseni`, `t_stale` | ne | jen `posudek(...)` |
| `[nosnik] L0`, `[beton] trida`/`Ecm`/`objemova_tiha`, `[prurez]` (při `prurez_z_posudku`) | **ano** | sdílené vstupy |
| `[nosnik] L` (délka nosníku) | ne (most používá L0) | **pozor na geometrii kabelů**, kap. 9 |
| kabely, výztuž, materiály výztuže, `[prostredi]`, `[casova_osa]`, `[degradace]`, ostatní `[posouzeni]` | ne | jen `posudek(...)` |

### 8.4 Výkon a paralelizace

Naměřeno na vzorovém příkladu (10 nosníků, L0 = 11,4 m, Windows):

| Krok | Čas |
|---|---|
| model mostu, `ex` = 0,125 m, `krok` 0,25 m | ~1,6 s |
| model mostu, `ex` = 0,0625 m | ~7 s (V_q +1,2 %, M beze změny) |
| model mostu, `krok` 0,5 m | ~1,5 s (výsledek beze změny) |
| posudek (`model_ze_slovniku` + `spocitej`) | ~0,35 s |
| `spocti` se spočteným mostem | ~1,1 s |
| zatížitelnost (27 výpočtů posudku) | ~13 s |
| CLI dávka s protokolem a grafy | ~9 s |

Čas mostu roste s počtem uzlů (N, L0, B, 1/ex²) a počtem poloh (L0/krok). Matice tuhosti
se faktorizuje jednou (`splu`), polohy vozidla se řeší dávkově. Pro mnoho běhů použít
`concurrent.futures.ProcessPoolExecutor` (funkce na úrovni modulu, na Windows
`if __name__ == "__main__":`), každý úkol vrací malý slovník výsledků (ne celé objekty).

---

## 9. Meze platnosti a pasti

1. **Jen prostý nosník**: `parametry_blc` předává jedno rozpětí L0 (posudek PB řeší
   prostý nosník). Spojité mosty jen v samostatném BLC (`vnitrni_sily(L=[…])`).
2. **Geometrie kabelů při změně délky**: `polygon` má body v **absolutních x [m]** (vzor
   končí v x = 11,96 = L). Při změně L/L0 je nutné body přepočítat (např. škálovat x
   poměrem L_nová/L); `parabola` a `primka` se přizpůsobí L samy. Ložiska jsou
   v (L − L0)/2 od konců – měnit L a L0 společně.
3. **Průřez je sdílený**: změna `[prurez]` mění v BLC A (→ g0) i Iy (→ h_ekv, tuhost,
   roznos plošky kola). Pro jiný typ prefabrikátu je potřeba celý vstup posudku (průřez,
   kabely, výztuž) – v repu je kompletní jen KA-67/12; katalog `blc/prefabrikaty.py` má
   jen L, b, Iy, spáru. Další vzory posudku: `../Posudek PB/examples/` (bez `[blc]`).
4. **Deska** (`typ_konstrukce = "deska"`): výsledky na pás 1 m (kNm/m, kN/m) → průřez
   posudku musí být pás šířky 1 m.
5. **Výběr nosníku**: "auto" + `kriterium = "M"` volí podle M_Ed; smyk může rozhodovat na
   jiném nosníku (ve vzoru rozhoduje N6 pro M i V, η smyku po nosnících 0,18–0,29).
   Pro jistotu ve studii posoudit všechny nosníky
   (`for o in range(vys.n_vyst)`, ~0,35 s / nosník) nebo porovnat kritéria "M" a "V".
   Zatížitelnost drží nosník vybraný při referenčním Ve.
6. **Příčná poloha vozidla** je jedna (osa vozovky / `y_vozidla`) – nehledá se
   nejnepříznivější. Při změně chodníků se mění osa vozovky, a tím i rozhodující nosník.
7. **Šikmé konstrukce**: V vyhodnocovat z 2D obálky; u šikmých nosníků singularita V
   v čele (nekonverguje se sítí) – používat V(d). Pro šikmé mosty volit `ex = 0.0625`.
   x výstupu je od osy podpory daného nosníku.
8. **Součinitele pro Ve** (γ_Q = 1,35, ψ0 = ψ1 = 0,75, ψ2 = 0) jsou převzaty z TS a pro Ve
   **nejsou ověřené** – ve studii je uvádět jako předpoklad, případně variovat.
9. **Validace** vyhazuje `ValueError`: 2d ≥ L0, α mimo 90–165°, chodníky ≥ B, spára bez
   b_s/Iy_s, N < 2 se spárou, t_akt mimo (t_provoz, t_konec), oslabení mimo 0–100 %,
   `taznost_oslabena` mimo (0, `taznost`] nebo ε_ud,red ≤ ε_p0.
   Přesah vozidla mimo vozovku a ignorované vstupy jsou jen **varování** (`vys.varovani`) –
   ve studii je ukládat.
10. **Nehladké η**: tahové napětí (0 až do vzniku tahu), křehký lom (klesá s q), fáze
    s/bez oslabení. Interpolace mezi body studie může být zavádějící.
11. **Neměnit `ZAKLAD` na místě** – vždy `copy.deepcopy`; `vys_pro_Ve` vrací mělkou
    kopii se sdíleným modelem MKP (jen pro čtení).
12. Exportované kombinace se zaokrouhlují na 0,01 kNm / kN a x na 1 mm (zanedbatelné).
13. **Dynamický součinitel**: vstup s explicitním `dyn = 1.0` (starší vstupy) počítá bez
    dynamiky; δ podle ČSN 73 6222 (Ve 1,05) platí jen při vynechaném `dyn`. Výsledky se
    liší o 5 % účinků q – ve studii uvádět, s jakým δ se počítalo (`vys.dyn`).

---

## 10. Návrh postupu parametrické studie

1. **Základní případ** = `priklady/most_KA67_12.toml`; ověřit, že reprodukuje η a Ve z kap. 6–7.
2. **Definovat parametry a rozsahy** jako slovník změn (cesta v `d` → hodnota), např.
   `("blc", "N")`, `("blc", "k_v")`, `("blc", "alfa")`, `("blc", "Ve")`,
   `("degradace", "oslabeni_predpinaci")`, `("casova_osa", "t_akt")`, `("blc", "chodnik_L")`.
3. **Seskupit běhy podle klíče mostu** (kap. 8.3): pro každou kombinaci parametrů mostu
   spočítat `vys` jednou, nad ním všechny posudkové varianty (koroze, stáří, součinitele).
4. **Ukládat** pro každý běh: vstupní parametry, posuzovaný nosník, `vys.souhrn()[o]`
   (M, V od stavů), `vys.varovani`, `m.protokol.upozorneni`, η všech posudků (klíč `klic_posudku`), max η za MSÚ
   a MSP jen z posudků závislých na dopravě, případně zatížitelnost `res.Ve`,
   `res.minimum("MSÚ"/"MSP")` s rozhodujícím posudkem. Formát: CSV (`;`) nebo JSON
   do `vystupy/<studie>/`.
5. **Kontroly**: rovnováha `vys.kontrola` (g_F ≈ g_R), citlivost na `ex` a `krok` u krajních
   případů, protokol HTML pro několik vybraných bodů.
6. Výsledky interpretovat s ohledem na kap. 9 (jedna příčná poloha, neověřené ψ pro Ve,
   pevný nosník u zatížitelnosti).
