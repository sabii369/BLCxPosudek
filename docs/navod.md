# Bridge Load Calculator – uživatelský návod

Posouzení přechodnosti vojenských vozidel MLC na mostech – porovnání s výjimečnou
zatížitelností Ve, deskový model (2D MKP), spojitý nosník o více polích, šikmé mosty,
volitelné okrajové podmínky podpor (kloub tvrdý / měkký, vetknutí, pružné vetknutí).

## 1. Před prvním spuštěním

### 1.1 Instalace Pythonu (jen jednou na počítači)

1. Stáhněte instalátor Pythonu 3 pro Windows (3.11 nebo novější):
   <https://www.python.org/downloads/windows/> → „Windows installer (64-bit)“.
2. Spusťte stažený soubor a **v prvním okně**:
   - zaškrtněte **„Add python.exe to PATH“** ← důležité!
   - klikněte na „Customize installation“ a zkontrolujte, že je zaškrtnuto
     **pip** a **tcl/tk and IDLE** (potřeba pro grafické okno),
   - dokončete instalaci („Next“ → „Install“).

### 1.2 Instalace potřebných balíčků (jen jednou)

Ve složce programu spusťte dvojklikem **`setup.bat`**. Skript nainstaluje přes pip
balíčky numpy, scipy, matplotlib, openpyxl (seznam je v `requirements.txt`), ověří
jejich načtení a zkontroluje tkinter. Na konci má být „Hotovo“. Je potřeba připojení
k internetu.

Ruční varianta (příkazový řádek ve složce programu):

```bat
python -m pip install -r requirements.txt
```

## 2. Spuštění

| Co | Jak |
|---|---|
| Grafické rozhraní | dvojklik na `spustit.bat`, nebo `python -m blc` |
| Ukázkový výpočet v konzoli + grafy do PNG | `python -m blc --demo` (grafy ve `vystupy/demo/`) |

## 3. Ovládání – vstupy

### Konstrukce

| Vstup | Význam |
|---|---|
| Prefabrikát | předvyplní rozpětí, šířku b, Iy a spáru z tabulky `blc/data/Prefabrikáty.xlsx` (bez souboru se použije vestavěná kopie). Hodnoty lze potom libovolně přepsat. |
| Typ konstrukce | **nosníky** – mostovka z N nosníků (hodnoty na nosník); **deska** – jedna deska šířky b a tloušťky h (hodnoty zintegrované na pás šířky 1 m) |
| Počet polí, L1 … Ln | spojitý nosník o n polích |
| N, b, Iy | počet nosníků, šířka nosníku, moment setrvačnosti nosníku |
| h | tloušťka desky (jen typ „deska“) |
| Třída betonu | E = Ecm dle ČSN EN 1992-1-1 |
| Spára | podélná spára mezi nosníky: šířka b_s, Iy spáry, beton spáry (dobetonávka); spojení se spárou kloubové; spára vlastní podporu nemá (podepřeny jsou vždy jen nosníky – kolmý i šikmý most) |
| d | statická účinná výška – posouvající síla se posuzuje v řezu ve vzdálenosti d od podpory |
| Úhel šikmosti α | 90° = kolmý most, šikmost roste směrem k 180° (teoretická mez); zadává se 90° až 165° |
| Druh šikmosti | pravá / levá |
| Tuhost podpory k_v | svislá tuhost liniové podpory [MN/m na 1 m délky podpory] (pružné uložení); prázdné nebo 0 = tuhá podpora. Výchozí 2000 MN/m/m, viz 4.2a |
| Uložení podpor | okrajové podmínky – jednou pro celý most, viz 4.2b: **kloub tvrdý** (natočení podél osy podpory zabráněno, u pružné podpory sleduje průhyb), **kloub měkký** (obě natočení volná), **vetknutí** (navíc zabráněno natočení kolem osy podpory) |
| Tuhost vetknutí k_φ | jen u vetknutí: [MNm/rad na 1 m délky podpory]; prázdné = dokonalé vetknutí |
| β_s = 0 i u pružné podpory | zjednodušená vazba (odpovídá SCIA s pružnou podporou a vetknutou rotací podél podpory) – jen pro srovnání, viz 4.2b |

### Zatížení

Typ vozidla, třída MLC, vzdálenost vozidel v koloně, výjimečná zatížitelnost Ve,
počet poloh vozidla na pole, příčná poloha MLC (posuvník, „auto střed“).

### Výpočet

Propojení nosníků (kloubové / deskové), roznos kola do střednice desky, tloušťka
vozovky, velikost prvku MKP (doporučeno 0,125 m; 0,0625 m pro V u šikmých mostů;
0,25 m pro rychlý orientační výpočet), obálky na nosnících (delší výpočet), krok poloh
pro obálky, převýšení grafů sil v půdorysu.

## 4. Jak funguje výpočet

### 4.1 1D analýza celého mostu (spojitý nosník, konstantní EI)

Vozidlo MLC (kolona) a schéma Ve se posouvají po mostě v obou směrech jízdy
s podélným roznosem plošky. Pro každý kontrolní řez se najde nejnepříznivější poloha:

- **M+** – maximum kladného momentu v každém poli,
- **M-** – záporný moment nad každou vnitřní podporou (u vetknutí i nad krajními podporami),
- **V** – posouvající síla v řezech x_k ± d u každé podpory (zatížení smí stát kdekoli,
  i v pásu d u podpory).

U šikmého mostu probíhá 1D výpočet v ose vozidla.

### 4.2 2D deskový model

MKP, prvky MITC4 – Mindlinova deska, smyková tuhost κ·G·h s κ = 5/6 (stejně jako SCIA).
Rozhodující poloha z bodu 4.1 se zadá do 2D modelu, který rozdělí zatížení napříč mostem:

- **nosníky** – každý nosník je pruh desky s náhradní tloušťkou h = (12·Iy/b)^(1/3),
  spojení kloubové nebo tuhé, volitelně spáry; každý nosník je podepřen liniově přes
  celou šířku čela (kolmo k ose); šikmý most: nosníky s kolmým čelem posunuté podle
  šikmé osy podpory, podpora v místě průsečíku osy nosníku s osou podpory. Spára vlastní
  podporu **nemá** (kolmý i šikmý most) – její okraje jsou podepřeny přes kloub
  s nosníky. U šikmých nosníků bez spáry program zobrazí upozornění.
- **deska** – kosoúhlá síť rovnoběžná s osou podpory, liniové uložení podél šikmé osy
  podpory.

Vnitřní síly se počítají vždy ve směru osy prvku. Podpory jsou liniové, ve svislém
směru tuhé nebo pružné (k_v, 4.2a), okrajové podmínky natočení podle volby uložení
(4.2b); stejné podmínky se použijí i v 1D modelu.

#### 4.2a Pružné podpory – jak nastavit k_v

**Proč:** u šikmého mostu mají sousední nosníky podpory posunuté. Tuhá (nepoddajná)
liniová podpora pak v místě, kde se nosníky o sebe opírají, vytvoří soustředěné
„parazitní“ reakce (stovky kN v jednom uzlu, s opačnými znaménky), které se se
zjemněním sítě nezmenšují – jde o singularitu modelu, ne o skutečné chování.
Skutečné ložisko (elastomer) je poddajné; pružina tuto singularitu odstraní.

**Doporučení:** k_v = tuhost skutečných ložisek přepočtená na 1 m podpory

```
k_v = n_ložisek_pod_nosníkem · K_ložiska / b_nosníku
K_ložiska = A · E_c / Σt,   E_c = 1 / ( 1/(5·G·S²) + 1/E_b )   (EN 1337-3)
G ≈ 0,9 MPa, E_b ≈ 2000 MPa, S = a·b / (2·t·(a+b)) pro vrstvu tloušťky t
```

| Elastomer | Σt | K |
|---|---|---|
| 200×300 | 24 mm | ≈ 0,6 GN/m |
| 300×400 | 40 mm | ≈ 1,2 GN/m |
| 400×500 | 44 mm | ≈ 1,7 GN/m |

→ pro nosníky I/KA se 2 ložisky: k_v ≈ 1000–3000 MN/m/m (výchozí 2000).
Uložení na betonový / maltový podklad, ocelová ložiska: k_v ≈ 10000 MN/m/m.

**Zdůvodnění** (parametrická studie, MLC80, prefabrikáty I-62/24, I-73/30, KA-61/12,
KA-67/18, KA-61/21, α = 90–135°, k = tuhá … 100 MN/m/m):

- Sednutí podpory je při k_v = 1000–3000 MN/m/m jen 0,4–1 % průhybu pole
  (ρ = 38,4·EI/(k_v·b·L³)) – globální chování mostu se nemění.
- Kolmý most: M beze změny (0,0 %), V(d) do ±2 %.
- S konzistentní vazbou β_s = ∂w/∂s je V(d) při k_v = 2000 prakticky stejné jako
  u tuhé podpory (I-62/24 se spárou: α 90° −1 %, 105° −0,4 %, 120° +0,8 %) a M+
  šikmých nosníků mírně vzroste (105°: +1,9 %, 120°: +4,8 %) – konec nosníku se na
  pružných ložiscích může natočit kolem své osy. Zjednodušená vazba β_s = 0 vytváří
  parazitní smyk κGh·∂w/∂s podél podpory, který uměle „vyhladí“ reakce a sníží V(d)
  (u 105° o ~5 %, u 120° o ~11 %).
- V u podpory šikmého mostu je citlivé na velikost prvku – pro V použijte prvek
  0,0625 m (srovnání se SCIA: 0,125 m dává V u ostrých rohů o ~8 % méně, 0,0625 m
  o ~4 % méně, M se shoduje na ±0,3 %).
- k_v pod ~300 MN/m/m nedávejte (pokud ložiska nejsou opravdu tak měkká): poddajnost
  pak začne měnit příčný roznos (M +2–6 % při 300 MN/m/m, +5–12 % při 100 MN/m/m,
  α ≥ 110°).
- Šikmé nosníky **bez spáry**: výsledky silně závisí na k_v i při realistických
  hodnotách (model je přetuhý) – program varuje; je-li mezi nosníky zálivka, zadejte
  ji jako spáru.

#### 4.2b Okrajové podmínky podpor – co znamenají a kdy je použít

s = směr osy podpory, n = normála k ní v půdorysu; β_s = natočení (sklon) podél osy
podpory, β_n = natočení kolem osy podpory (ohybové).

- **kloub tvrdý (výchozí)** – w = 0 / pružina k_v, β_s = 0. U pružné podpory
  β_s = ∂w/∂s: linie podpory se natáčí s průhybem ložisek, nevzniká parazitní smyk.
  Odpovídá podpoře s koncovým příčníkem nebo tuhou opěrou, která brání deformaci
  (zborcení) průřezu nad podporou.
- **kloub měkký** – jen w; β_s i β_n volné. Odpovídá liniové podpoře s volnými rotacemi
  (výchozí liniová podpora v SCIA). Pozor: u Mindlinovy desky vzniká u měkké podpory
  okrajová vrstva šířky ~h, V u podpor pomalu konverguje se sítí (doporučen prvek
  ≤ 0,0625 m).
- **vetknutí** – jako tvrdý kloub + β_n = 0 (dokonalé), nebo rotační pružina k_φ·ℓ na
  β_n (pružné vetknutí; ℓ = skutečná délka podpory příslušná uzlu). Platí pro všechny
  podpory včetně vnitřních (spojitá rámová konstrukce). Nad vnitřní vetknutou podporou
  je skok M; v uzlu podpory se uvádí strana s větší |M|. Přibudou řezy M- nad krajními
  podporami. Orientačně: k_φ ≈ 4·E·I_stěny / h_stěny na 1 m (opěra/stěna vetknutá
  v patě), k_φ → 0 = kloub.
- **β_s = 0 i u pružné podpory** – zjednodušená vazba; dává shodu s modelem SCIA, kde
  je u pružné liniové podpory vetknuté natočení podél podpory (např. „natočení kolem
  osy nosníku zakázané“). Jen pro srovnání.

Ve 2D modelu desky se m_x nad podporou (vnitřní podpora, vetknutí) bere lineární
extrapolací z vnitřních uzlů pole (hodnota z rohů prvků z jedné strany konverguje
pomalu – prvek 0,25 m by dal |M-| o ~3–5 % menší, 0,125 m o ~2 %). Reakce v uzlech
pružné podpory = síla v pružině k_v·w.

### 4.3 Posouzení

V každém řezu: **využití = max hodnota na nosníku (pásu 1 m) od MLC / max hodnota od Ve**.
Rozhoduje řez s největším využitím; < 100 % → PROJDE. Pro srovnání se uvádí i využití
1D (celý most bez příčného roznosu).

### 4.4 Kontrola modelu

Součet sil na všech nosnících (a spárách) se porovnává se statikou 1D nosníku
(odchylka má být ~0 %; platí i pro pružné podpory a vetknutí – u vetknutí se porovnává
mimo uzly podpor, kde je skok M). U šikmé desky se kontrola neprovádí.

## 5. Výstupy

Tabulka po kontrolních řezech: 1D a 2D hodnoty MLC a Ve, využití, rozhodující nosník /
pás. Pod ní souhrn (rozhoduje, PROJDE / NEPROJDE).

Grafy (tlačítka dole; „Řez“ vybírá kontrolní řez, „(rozhodující)“ = automaticky):

| Graf | Obsah |
|---|---|
| Zatížení – Mmax, Vmax | poloha MLC a Ve v rozhodujícím stavu (pohled, půdorys) |
| Průběhy – MLC / Ve | M a V na nosnících v půdorysu pro vybraný řez |
| Příčný roznos | hodnoty na jednotlivých nosnících / pásech v řezu |
| Obálky nosníky – MLC / Ve | obálky M a V na každém nosníku (2D pojezd) |
| Obálky 1D | obálky celého mostu, MLC vs Ve |
| Využití po řezech | přehled využití 1D a 2D |
| Síť MKP | půdorys sítě: prvky nosníků / spár / desky, podepřené uzly (tuhé / pružné), podélné klouby, počet prvků a DOF, typ uložení (lupou v okně grafu lze síť zvětšit) |

## 6. Omezení a poznámky

- Stejný průřez ve všech polích; podpory vždy liniové, svisle tuhé nebo pružné se
  stejnou tuhostí k_v a se stejnými okrajovými podmínkami natočení na všech podporách
  (uložení se volí jednou pro celý most).
- k_v se vztahuje na 1 m podpory měřený napříč mostem (průmět), k_φ na 1 m skutečné
  délky šikmé osy podpory (rozdíl 1/sin α', u 105° 3,5 %). U nosníků je podepřená
  délka jen šířka nosníků N·b (bez spár), i v 1D modelu.
- U nosníků se spárou je podepřeno (a vetknuto) jen čelo nosníků; spára vlastní
  podporu nemá – u kolmého i šikmého mostu.
- Pro každý kontrolní řez se ve 2D řeší jeden zatěžovací stav vybraný podle 1D
  kritéria (nejde o úplné prohledání všech poloh ve 2D).
- Náhradní deska nosníku má torzní tuhost plného průřezu – u šikmých mostů z nosníků
  bez spáry může být vliv šikmosti nadhodnocen.

## 7. Vnitřní síly pro posudek nosníku (g0, g − g0, q)

Samostatný výpočet průběhů vnitřních sil na každém nosníku (u desky na každém pásu
1 m) od tří zatěžovacích stavů. Průběhy nejzatíženějšího nosníku jsou vstupem modulu
**Posudek PB** (repo `PB_posudek`, posudek předpjatého nosníku) a slouží
pro parametrické studie.

### 7.1 Zatěžovací stavy

| Stav | Obsah | Model |
|---|---|---|
| **g0** | vlastní tíha nosné konstrukce | nosníky: každý nosník **samostatně, bez spolupůsobení** (1D spojitý nosník se stejným uložením), g0 = A·γ_b; deska: 2D MKP, g0 = h·γ_b |
| **g − g0** | skladba vozovky, skladba chodníků, svodidla, zábradlí, další liniová zatížení | 2D MKP (příčný roznos); tíha výplně spáry g_s se nese samostatně – každý ze sousedních nosníků polovinu |
| **q** | pojezd vozidla Ve (výjimečná zatížitelnost) v ose vozovky, × dynamický součinitel δ | 2D MKP – obálka max/min přes polohy vozidla (krok 0,25 m + polohy hrany zatížení v řezech d) |

Model konstrukce (síť, spáry, uložení, šikmost, k_v, k_φ) je totožný s porovnáním
MLC / Ve.

### 7.2 Nové vstupy

| Vstup | Jednotka | Poznámka |
|---|---|---|
| šířka chodníku vlevo / vpravo | m | chodníky leží u okrajů mostovky šířky B, vozovka mezi nimi |
| tíha skladby chodníku | kN/m² | na obou chodnících |
| tíha skladby vozovky | kN/m² | mezi chodníky |
| zábradlí | kN/m | na každé straně, pás 0,2 m u vnějšího okraje |
| svodidlo | kN/m | na každé straně, pás 0,2 m na chodníku u okraje vozovky |
| plocha nosníku A, γ_b | m², kN/m³ | g0 = A·γ_b (deska: h·γ_b); lze zadat i přímo g0 |
| tíha výplně spáry | kN/m | jen nosníky se spárou |
| dynamický součinitel δ | – | násobí zatížení Ve |
| osa vozidla y_Ve | m | prázdné = osa vozovky |

Další liniová zatížení (římsa apod.) lze zadat ve vstupním souboru (`[[stale.liniova]]`).

### 7.3 Ovládání

- **GUI:** sekce „Vnitřní síly pro posudek“ pod tlačítkem výpočtu, tlačítko
  *Vnitřní síly pro posudek*. Okno výsledků: tabulka max M a |V| všech stavů po
  nosnících, M_Ed a V_Ed (MSÚ 6.10 včetně g0), žlutě nejzatíženější nosník (kritérium
  M, M− nebo V), grafy *Průběhy sil* a *Příčné rozdělení*, export do posudku.
- **Příkazová řádka:** `python -m blc --sily priklady/sily_KA67_12.toml
  [--pb cesta/k/vstupu_posudku.toml] [--vystup složka]`.
- **Python:** `vnitrni_sily(...)` → `VysledekSil` (`tabulka(o, stav)`, `kombinace(o, druh)`,
  `souhrn()`, `rozhodujici()`), `uloz_vysledky(...)`, `zatizeni_pb_dict(...)` (sekce
  `[zatizeni]` jako slovník – parametrická studie bez souborů).

### 7.4 Výstupy a napojení na Posudek PB

| Soubor | Obsah |
|---|---|
| `vnitrni_sily.json` | metadata, souhrn, průběhy g0, g − g0, q (x, M_max, M_min, V_max, V_min) na všech výstupech |
| `souhrn.csv` | max M, \|V\| po nosnících (Excel: `;`, desetinná čárka) |
| `<nosník>_stavy.csv` | průběhy stavů posuzovaného nosníku |
| `zatizeni_PB.toml` | sekce `[zatizeni]` pro Posudek PB |
| `<vstup>_BLC.toml` | kopie vstupu posudku se zatížením z BLC (při zadání `--pb`) |
| `prubehy_sil.png`, `pricne_rozdeleni.png` | grafy |

- x v posudku = x od osy první podpory + (L − L0)/2 (L = délka nosníku, L0 = rozpětí);
  na převislých koncích se doplní nulové hodnoty.
- Vlastní tíhu nosníku počítá posudek sám z průřezu → exportuje se jen g − g0 a q
  (`obsahuje_vlastni_tihu = false`); g0 z BLC je v komentáři souboru pro kontrolu.
- Režim **kombinace** (výchozí): obálky 6.10a, 6.10b (nebo 6.10), charakteristické,
  časté a kvazistálé kombinace s plnými M_max, M_min, V_max, V_min.
  Režim **zatezovaci_stavy**: g − g0 jako stálý stav (tabulka) a q jako proměnný stav
  (M_max a V s větší absolutní hodnotou) – kombinace sestaví posudek.
- Součinitele kombinací (γ_G, γ_G,inf, ξ, γ_Q, ψ0, ψ1, ψ2) jsou vstupem; výchozí
  hodnoty odpovídají TS podle ČSN EN 1990 (tab. A2.1) – **pro Ve je nutné je ověřit**.
- Znaménka: kladný M táhne dolní vlákna, V = dM/dx (stejně jako Posudek PB).

### 7.5 Omezení

- Posudek PB řeší prostý nosník; u spojitých konstrukcí je export jen orientační
  (dvojice hodnot V nad vnitřní podporou se sloučí).
- U šikmých nosníkových mostů se x měří od osy podpory daného nosníku.
- Vozidlo Ve stojí v jedné příčné poloze (osa vozovky nebo zadaná y_Ve); další
  pohyblivá zatížení (Vn, Vr, LM1 …) zatím nejsou.
