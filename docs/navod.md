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
| **g0** | vlastní tíha nosné konstrukce | nosníky: každý nosník **samostatně, bez spolupůsobení** (1D spojitý nosník se stejným uložením), g0 = A·γ_b; + dobetonávka mezi nosníky A_dob·γ_b – nesou ji samostatně sousední nosníky ½ + ½ (krajní nosník jen ½ dobetonávky); deska: 2D MKP, g0 = h·γ_b |
| **g − g0** | skladba vozovky, skladba chodníků, svodidla, zábradlí, další liniová zatížení | 2D MKP (příčný roznos); tíha výplně spáry g_s se nese samostatně – každý ze sousedních nosníků polovinu |
| **q_ch** | zatížení chodců q [kN/m²] na chodnících – zadané, nebo podle ČSN 73 6222: s Vn a Vr **2,5 kN/m²** (tab. 7.1, 7.2 – redukovaná hodnota w_f), s Ve **0** (chodci vyloučeni, čl. 3.1.4, 5.2.8), s MLC 0 | 2D MKP – obálka: chodníky rozdělené na úseky ≈ 0,5 m (levý i pravý zvlášť), max = Σ kladných, min = Σ záporných účinků (nepříznivé části plochy vlivu) |
| **q** | zatížení dopravou × dynamický součinitel δ (zadaný, nebo podle ČSN 73 6222, kap. 8): **Vn** – schéma normální zatížitelnosti, **Vr** – jediné vozidlo výhradní zatížitelnosti (obojí u kraje vozovky u užšího chodníku, viz 7.6), **Ve** – souprava výjimečné zatížitelnosti v ose vozovky, nebo vozidlo **MLC** | 2D MKP – obálka max/min přes polohy vozidla (krok 0,25 m + polohy hrany zatížení v řezech d); u Vn nápravy v pruzích nezávisle a rovnoměrné zatížení v nepříznivých částech plochy vlivu |

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
| plocha dobetonávky A_dob | m² | plocha jedné dobetonávky mezi dvěma sousedními nosníky; přičte se ke g0 (vnitřní nosník ½ + ½, krajní ½); do posudku se předává s g − g0 |
| dynamický součinitel δ | – | násobí zatížení vozidla; prázdné = podle ČSN 73 6222, kap. 8 (viz níže) |
| zatížení chodníků q_chodnik | kN/m² | prázdné = podle ČSN 73 6222 (Vn, Vr 2,5; Ve 0); 0 = bez chodců |
| vozidlo Vn / Vr / Ve, MLC | t | jedno zvolené zatížení dopravou (viz 7.6) |
| osa vozidla y_Ve | m | jen Ve a MLC; prázdné = osa vozovky (Vn a Vr vždy u kraje vozovky) |

Další liniová zatížení (římsa apod.) lze zadat ve vstupním souboru (`[[stale.liniova]]`).

**Dynamický součinitel podle ČSN 73 6222, kap. 8** (pole prázdné, ve vstupním souboru `dyn`
vynechané): δ násobí statické účinky zatížení dopravou (čl. 8.1.1) a závisí na druhu
zatížitelnosti. Pro výjimečnou zatížitelnost Ve je **δ = 1,05** pro zatížení jedním kolem
či nápravou i celou soupravou (čl. 8.4 a, b) – nezávisí na rozpětí ani na vlastní frekvenci.
Pro normální a výhradní zatížitelnost platí součinitele **δ1, δ2, δ3** podle vlastní frekvence
f = 90,6·L_d^−0,923 (čl. 8.7.1; obr. 8.1: f ≤ 1 Hz 1,20 / 1,17 / 1,13, 2,5–4,5 Hz 1,40 / 1,30 /
1,20, f ≥ 6 Hz 1,25 / 1,20 / 1,15, mezi zlomy lineárně); náhradní délka L_d podle tab. 8.1 –
jedno pole: kolmá vzdálenost uložení (šikmý most L·sin α), spojitá konstrukce: průměr rozpětí.
**Vr**: celé vozidlo δ = δ1 (čl. 8.3.1 b). **Vn**: δ1 / δ2 / δ3 podle počtu zatížených pruhů
(čl. 8.2.1 b–d) – program zkouší zatížit pruhy 1 … k a bere nejnepříznivější δ_k·účinek.
Místní účinky jednoho kola (δ = 1,40 / 2,0) se u nosníků neuvažují. Zatížení chodníků se
nenásobí (δ = 1,00, čl. 8.5 b). Pro vozidla MLC norma δ neuvádí – uvažuje se 1,0
s upozorněním; známou hodnotu zadejte. Zadané číslo má vždy přednost (u Vn platí pro všechny
počty pruhů). Použitá hodnota a její zdroj jsou v popisu stavu q (protokol,
`vnitrni_sily.json`: `dyn`, `dyn_zdroj`).

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
  Dobetonávka mezi nosníky (část g0 BLC) průřez posudku nezahrnuje – exportuje se
  spolu s g − g0 (v kombinacích i v režimu zatěžovacích stavů).
- Režim **kombinace** (výchozí): obálky 6.10a, 6.10b (nebo 6.10), charakteristické,
  časté a kvazistálé kombinace s plnými M_max, M_min, V_max, V_min.
  Režim **zatezovaci_stavy**: g − g0 jako stálý stav (tabulka) a q jako proměnný stav
  (M_max a V s větší absolutní hodnotou) – kombinace sestaví posudek.
- Součinitele kombinací (γ_G, γ_G,inf, ξ, γ_Q, ψ0, ψ1, ψ2) jsou vstupem; výchozí
  ψ0 = ψ1 = 0,75 odpovídají ČSN 73 6222, čl. 10.1.1 a 10.2.1 (zatížitelnost Vn, Vr, Ve),
  γ_Q = 1,35 (ČSN EN 1990); ψ2 = 0 (norma neuvádí, jako TS). Pro MLC je nutné je ověřit.
- Znaménka: kladný M táhne dolní vlákna, V = dM/dx (stejně jako Posudek PB).

### 7.5 Omezení

- Posudek PB řeší prostý nosník; u spojitých konstrukcí je export jen orientační
  (dvojice hodnot V nad vnitřní podporou se sloučí).
- U šikmých nosníkových mostů se x měří od osy podpory daného nosníku.
- Zatížení stojí v jedné příčné poloze: Vn a Vr u kraje vozovky u užšího chodníku, Ve a MLC
  v ose vozovky nebo v zadané y_Ve; nejnepříznivější příčná poloha se nehledá. Další
  pohyblivá zatížení (LM1 …) zatím nejsou; vodorovné síly (čl. 7.4) se neuvažují.
- Zatížení dopravou: `Vn=` / `Vr=` [t] (`schema` volitelně), `Ve=` [t] nebo MLC
  (`MLC="MLC80", typ_MLC="k"|"p"`, `dist` = kolona, bez `dist` jedno vozidlo); vždy jen
  jedno zvolené.

### 7.6 Schémata normální a výhradní zatížitelnosti (ČSN 73 6222, kap. 7)

**Zatěžovací prostor** = vozovka mezi chodníky (šířka w). **Příčná poloha**: zatížení se klade
ke kraji vozovky u **užšího chodníku** (při shodných šířkách k levému) – pruh č. 1, resp.
vnější okraj vozidla Vr leží u tohoto kraje, další pruhy směrem k druhému kraji, zbytek vozovky
je zbývající plocha. Nejnepříznivější příčná poloha se nehledá.

**Normální zatížitelnost Vn** (čl. 7.1, obr. 7.1) – rovnoměrné zatížení vn = Vn/13,33 kN/m²
(V_aw = 100·vn kN, V_nw = 4/3·V_aw, Vn = V_nw/10 t; např. vn = 2,4 → Vn = 32 t).
Pruhy (čl. 7.1.3): w < 5,4 m 1 pruh 3 m; 5,4–6 m 2 pruhy 0,5·w; jinak ⌊w/3⌋ pruhů 3 m.

| Pruh | Nápravy | Rovnoměrné |
|---|---|---|
| 1 a 2 | dvounáprava 2 × 50·vn (kolo 25·vn, nápravy 1,2 m); při Vn < 16 t náhradní jednoduchá náprava 100·vn (kolo 50·vn, čl. 7.1.6) | 2,5·vn |
| 3 a 4 | jednoduchá náprava 50·vn (kolo 25·vn) | vn |
| další pruhy, zbývající plocha | – | vn |

Kola jsou 2,0 m od sebe (0,5 m od okrajů pruhu 3 m); ploška kola 0,40 × 0,40 m jako u LM1
(norma ji neuvádí) + roznos. Nápravy každého pruhu projíždějí nezávisle (obálka pruhu = max
přes polohy, záporný účinek = náprava mimo most), rovnoměrné zatížení se klade jen do
nepříznivých úseků (≈ 0,5 m; u šikmých mostů i příčně po ≤ 1 m). Obálka:
max = max_k δ_k·(Σ_{i ≤ k} pruh_i + zbývající plocha), k = počet zatížených pruhů.
Chodníky 2,5 kN/m² (tab. 7.1, sestava n1).

**Výhradní zatížitelnost Vr** (čl. 7.2) – jediné vozidlo tíhy 10·Vr kN, δ1:

| Vozidlo | Použití (čl. 7.2.2) | Nápravy | Plošky kol |
|---|---|---|---|
| šestinápravové (obr. 7.3) | Vr > 50 t | 6 × Vr/6 po 1,5 m; stopy 1,5 m, šířka vozidla 3,0 m | 0,15 × 1,2 m |
| třínápravové (obr. 7.4b) | 16 < Vr ≤ 50 t (lze) | ¼ + ⅜ + ⅜ Vr, nápravy 2,4 + 1,2 m | přední 0,2 × 0,2 m, zadní 0,2 × 0,4 m |
| dvounápravové (obr. 7.4a) | jinak | ¼ + ¾ Vr, rozvor 3,0 m | dtto; kola 2,0 m od sebe, šířka 2,5 m |

Vozidlo projíždí v obou směrech, chodníky 2,5 kN/m² (tab. 7.2, sestava r1). Při posouzení
pro zadanou tíhu se schéma volí podle ní (Vn ≥ 16 t dvounáprava; Vr podle tabulky).

## 8. Spojený program BLC × Posudek PB

Spuštění: `spustit_posudek.bat` (dvojklik, nebo přetažení souboru .toml), `python -m blc_posudek`
(GUI s příkladem `priklady/most_KA67_12.toml`), `python -m blc_posudek most.toml -o vystup`
(dávkově – vytvoří `protokol.html`, `vysledky.json` posudku a ve složce `most/` vnitřní síly
mostu a grafy).

Více souborů najednou: `python -m blc_posudek a.toml b.toml … -o vystup` nebo celá složka
`python -m blc_posudek modely_prefa -o vystup` (všechny `*.toml`, `*.json`). Výstup každého
souboru je v `vystup/<soubor>/`, přehled všech v `vystup/souhrn.csv` (pro Excel: oddělovač `;`,
desetinná čárka) – nosník, vozidlo, nejvyšší η MSÚ a MSP s rozhodujícím posudkem, počet
nevyhovujících posudků a upozornění, u zatížitelnosti Vn, Vr, Ve, evidence a V_aj; chyba
jednoho souboru dávku nezastaví (sloupec *chyba*). Volby:

- `--bez-protokolu` – jen výpočet a výpis / souhrn, bez HTML protokolu, grafů a vnitřních sil
  mostu (most + posudek ~1–6 s na soubor místo ~10 s s protokolem),
- `-j N` – N souběžných procesů (12 mostů z `modely_prefa/` bez protokolu: 1 proces ~31 s,
  4 procesy ~10 s, 8 procesů ~7 s).

Program počítá s numpy / OpenBLAS v jednom vlákně (malé úlohy MKP jsou tak rychlejší); jiné
nastavení lze vynutit proměnnou prostředí `OPENBLAS_NUM_THREADS`.

### 8.1 Postup

1. **Karta 0 – Most a zatížení (BLC):** rozpětí L0, délka L, beton (stejná pole jako na
   kartách 1 a 3), počet a šířka nosníků, účinná výška, spára, uložení a šikmost, vybavení
   (chodníky vlevo/vpravo, tíha skladby chodníku a vozovky, zábradlí, svodidla, další liniová),
   chodci (prázdné = podle ČSN 73 6222), **vozidlo** (Vn / Vr / Ve [t] podle ČSN 73 6222,
   MLC kolové / pásové, kolona jen u MLC), dynamický součinitel (prázdné = podle ČSN 73 6222,
   kap. 8: Vn δ1–δ3, Vr δ1, Ve δ = 1,05),
   posuzovaný nosník (auto = nejzatíženější podle M, M− nebo V), způsob předání.
   Karta ukazuje **jen pole platná pro zadání**: u desky tloušťku h (bez počtu a šířky nosníků
   a spáry), A a Iy nosníku jen bez převzetí z průřezu, parametry spáry jen se zaškrtnutou spárou,
   k_φ jen u vetknutí, u vozidla jen jeho tíhu (MLC: třída a kolona; v režimu zatížitelnosti
   referenční Vn, Vr i Ve). Skrytá pole si hodnotu ponechají. Dokud most není spočten, ukazuje
   graf vpravo **náhled příčného řezu ze zadání** (nosníky, vybavení, pruhy Vn / vozidlo Vr, Ve,
   MLC v příčné poloze, kóty) – bez výpočtu MKP, překresluje se při změně vstupů; po výpočtu je
   týž řez ve volbě grafu *Příčný řez – poloha zatížení*. Posuzovaný nosník je v tabulce
   nosníků tučně se značkou ●.
2. Karty 1–4: materiály, průřez (z něj A a Iy nosníku pro model mostu – lze vypnout
   a zadat ručně), kabely, výztuž.
3. Karta 5: prostředí, časová osa a stáří, od kterého působí g − g0 / kvazistálá kombinace;
   sekce **Dílčí součinitele zatížení** – všechny součinitele na jednom místě: stálá (γ_G,sup,
   γ_G,inf, ξ), doprava q a chodci q_ch (γ_Q, ψ0, ψ1, ψ2), teplota (γ, ψ po kombinacích).
   Vnější zatížení se nezadává – zobrazí se kombinace převzaté z obálek.
   Karta 6 (nastavení posouzení) je rozdělena do skupin *Napínání a předpínací výztuž*,
   *Napětí v betonu*, *Dekomprese a trhliny*, *MSÚ, smyk a průhyb*. Karta 7 (výsledky) má nad
   tabulkou posudků filtr *Zobrazit* (všechny / jen nevyhovující / nevyhovující a η > 90 %)
   a *Fáze*. **Zbytková životnost** 50 / 15-30 / 10 let určí kategorii
   mostu podle ČSN 73 6222, tab. 12.3 (předem předpjatý B/C/D, dodatečně soudržně C/D/E)
   a z tab. 12.4 kombinaci pro dekompresi, pro šířku trhlin a w_max (přepíše ruční volby
   dekomprese, trhliny, w_max; tahové napětí v provozu je pak jen informativní). Šířka trhlin
   (7.3.4): bez trhlin při σ_ct ≤ f_ctm, jinak průřez s trhlinou; s_r,max podle (7.11) jen se
   zadaným Ø betonářské výztuže (karta 4, sloupec Ø), jinak 1,3·(h − x). Prázdné = bez kategorie.
4. **Lišta nahoře:** *Režim* **Posouzení / Zatížitelnost** (u zatížitelnosti i volba druhů
   a protokolu) a tlačítko **▶ Posouzení (F5)** / **▶ Zatížitelnost (F5)** – spočítá model mostu
   (jen pokud se změnily jeho vstupy) a posudek, resp. zatížitelnost; tlačítko
   *Jen vnitřní síly mostu* na kartě 0 spočítá jen most (tabulka nosníků, grafy). Změna dílčích
   součinitelů γ, ψ, ξ (karta 5) model mostu nepřepočítává – jen se znovu složí kombinace.
5. *HTML protokol* – protokol posudku s kapitolou „Zatížení z modelu mostu (BLC)“. Části jen
   pro protokol (polohy vozidla, referenční soupravy Vn, Vr, Ve, obrázky) se počítají až
   při jeho vytvoření, F5 je proto rychlejší.

### 8.2 Převzetí zatížení

- Posuzovaný nosník: zadaný, nebo nejzatíženější podle MSÚ 6.10 (včetně g0). V tabulce na
  kartě 0 je zvýrazněn; dvojklikem na řádek se zvolí jiný.
- Předává se g − g0 a q (g0 počítá posudek z průřezu), výchozí jako obálky kombinací
  6.10a, 6.10b (nebo 6.10 podle karty 6), charakteristické, časté a kvazistálé.
- Součinitele: γ_G, γ_G,inf, ξ (stejné pro g0 i g − g0) a γ_Q, ψ0, ψ1, ψ2 dopravy a chodců
  z karty 5, sekce Dílčí součinitele zatížení (výchozí ψ0 = ψ1 = 0,75 podle ČSN 73 6222, čl. 10;
  pro MLC ověřit); kombinace MSÚ (6.10a/b nebo 6.10) z karty 6.
- Změní-li se vstup ovlivňující model mostu (i průřez nebo rozpětí), karta 0 a 5 to
  hlásí a F5 most přepočítá; samotné součinitele γ, ψ, ξ přepočet mostu nevyžadují.

### 8.3 Grafy zatížení mostu a napětí v řezech (protokol, karta 7)

**Hlavička protokolu** – pod nadpisem most, zatížení dopravou (vozidlo, poloha, δ), chodci,
posuzovaný nosník a způsob jeho výběru (u zatížitelnosti i Vn, Vr, Ve a tíha, pro kterou jsou
posudky) a **celkový výsledek** (vyhovuje / nevyhovuje, počet nevyhovujících posudků, nejvyšší
využití, počet upozornění). V grafu „Souhrn využití“ jsou posudky jednotlivých kabelů
(napínací napětí, napětí po zakotvení) sloučeny do jednoho řádku s rozhodujícím kabelem;
všechny posudky jsou v tabulce *Všechny posudky*. Obrázky se ukládají jako PNG s paletou
(protokol vzoru ~1,4 MB). Výškové překrytí kanálků je v kap. Předpínací výztuž jedna tabulka.

**Kapitola zatížení** („Zatížení z modelu mostu (BLC)“) – půdorys mostu se zatížením
(nosníky, spáry, osy podpor, posuzovaný nosník oranžově, řezy „střed“ a „podpora“ červeně;
osa y nahoru jako u půdorysu vnitřních sil a sítě MKP):

- vlastní tíha g0 | ostatní stálé g − g0 (chodníky, vozovka, zábradlí, svodidla),
- vozidlo v poloze pro max M ve středu rozpětí | pro max V u podpory (řez d od osy ložiska);
  poloha se hledá mezi stejnými polohami jako obálka q. U schématu Vn jsou zakresleny
  nápravy pruhů v rozhodujících polohách a rovnoměrné zatížení (světle) v úsecích s nepříznivým
  účinkem; v nadpisu je počet zatížených pruhů a δ,
- **příčný řez s příčnou polohou zatížení dopravou**: nosníky (posuzovaný oranžově), chodníky,
  vozovka, zábradlí a svodidla; u Vn zatěžovací pruhy a zbývající plocha s tíhami náprav
  a rovnoměrným zatížením (hodnoty pro dané vn), u Vr / Ve / MLC obrys vozidla s tíhami náprav;
  stopy kol, svislice kraje vozovky u užšího chodníku (Vn, Vr) nebo osy vozidla (Ve, MLC)
  a řetězec kót [m] (pruhy, okraje vozidla, osy stop). Stejný řez je v grafu „Příčné rozdělení“
  na kartě 0.

**Kapitola napětí v betonu** – pod každý graf „Napětí v krajních vláknech po délce – fáze“
je doplněn graf „Napětí v řezech“: napětí po výšce průřezu v řezu posudku ve středu
rozpětí a v řezu u podpory (nejblíže vzdálenosti d od ložiska) pro tutéž fázi, se stejnými
kombinacemi (stálá, resp. charakteristická, častá, kvazistálá) a obálkou P_sup/P_inf ×
M_max/M_min jako graf po délce, meze tlaku a tahu shodné. Hodnoty v krajních vláknech
souhlasí s grafem po délce (napětí je po výšce lineární, obálka variant je lomená).
Grafy jsou i v seznamu grafů na kartě 7 (za grafem napětí příslušné fáze).

### 8.4 Součinitele a kombinace (kapitola zatížení protokolu)

**Grafy vnitřních sil** (graf sil na nosnících v protokolu, grafy *Průběhy sil*, *Vnitřní síly
na nosnících* a *Příčné rozdělení* na kartě 0, `prubehy_sil.png`, `pricne_rozdeleni.png`)
jsou v **charakteristických hodnotách bez kombinačních, dílčích a dynamických součinitelů**
– pro kontrolu s jinými statickými výpočty. Posudky, kombinace a tabulky kombinací
součinitele obsahují (γ, ψ, ξ, δ).

Kapitola „Zatížení z modelu mostu (BLC)“ obsahuje postupně: popis stavů, zatížení na mostě,
**tabulku dílčích součinitelů γ a součinitelů kombinace ψ** pro skupiny g0 + (g − g0),
q – chodci a q – doprava (char., častá, kvazistálá a MSÚ podle karty 6 – 6.10a a 6.10b,
nebo 6.10; u stálých v 6.10b ψ = ξ), **graf vnitřních sil M, V na nosnících** od jednotlivých stavů ve formátu obálek BLC
(půdorys, průběh vynesen od osy každého nosníku, řádek = zatěžovací stav, vlevo M, vpravo V,
posuzovaný nosník zvýrazněn, u proměnných max červeně / min modře; zatížení dopravou
se kreslí **bez dynamického součinitele δ** – u Vn přepočtené s δ = 1 pro
všechny počty pruhů), tabulku maxim po nosnících od stavů g0, g − g0 (a chodců), kde je místo
zadaného zatížení dopravou max M a max |V| od **referenčních souprav Vn 32 t, Vr 60 t a Ve 80 t**
(nezávisle na zvoleném vozidle; charakteristické hodnoty bez δ, schéma podle tíhy, poloha jako
v kap. 7 – Vn, Vr u kraje vozovky u užšího chodníku, Ve v ose vozovky),
a **dvě tabulky kombinací po nosnících** – max M a max |V|, sloupce = kombinace (v popisku
poloha max M posuzovaného nosníku a nejmenší M všech nosníků a kombinací).

Účinek kombinace = Σ γ·ψ·E (proměnná zatížení chodci a doprava působí současně);
příznivé stálé γ_G,inf. Kombinace v tabulkách obsahují g0 z modelu mostu. γ_G, ξ i γ a ψ
chodců a dopravy (výchozí 1,35 / 0,75 / 0,75 / 0) jsou na kartě 5 v sekci Dílčí součinitele zatížení.
Do posudku se předávají g − g0, q_ch a q (g0 si posudek počítá sám).

### 8.5 Výpočet zatížitelnosti (ČSN 73 6222)

Režim **Zatížitelnost** v liště nahoře a volba *druhy* (*Vn, Vr i Ve* / *jen
zvolené vozidlo*) (v souboru `[blc] zatizitelnost = true`, `zatizitelnost_druhy = "vse" |
"vozidlo" | ["Vn", "Ve"]`; v dávce `--zatizitelnost [--druhy Vn,Vr,Ve]`): místo posouzení při
zadaném zatížení se pro každý posudek (mezní stav × fáze × kombinace) hledá **tíha vozidla,
při které je využití 100 %** – pro **normální Vn, výhradní Vr a výjimečnou Ve** zatížitelnost.
Zvolené vozidlo musí být Vn, Vr nebo Ve – pro ně se počítá protokol.

- Pro každé schéma se stav q spočte jednou s referenční tíhou (zadané Vn, Vr, Ve – výchozí
  32, 60, 80 t) na stejném modelu MKP; účinky jsou v tíze lineární, pro jinou tíhu se
  přeškálují. Posudek se pro zkoušenou tíhu počítá celý (nelineární MSÚ, ztráty předpětí …),
  tíha se hledá metodou regula falsi (Illinois) s přesností |η − 1| ≤ 0,1 %.
- **Volba schématu** (pro každý posudek): Vn – dvounáprava; vyjde-li pod 16 t, spočte se
  i náhradní náprava a Vn = min(V_náhradní, 16 t) (čl. 7.1.6). Vr – šestinápravové vozidlo;
  vyjde-li ≤ 50 t, spočte se dvounápravové, a vyjde-li nad 16 t, i třínápravové:
  Vr = max(V_2, V_3) ≤ 50 t (čl. 7.2.2).
- Chodci podle normy: s Vn a Vr 2,5 kN/m², s Ve 0 (lze zadat jinak). g0, g − g0 se nemění.
- **Nosníky**: každý posudek se hledá na **všech nosnících (pásech)** a platí nosník s nejnižší
  zatížitelností (v tabulkách sloupec *Nosník*). Zbytečné nosníky se nepočítají: nosníky se řadí
  od nejzatíženějšího a nosník se vynechá, má-li již spočtený nosník při tíhách vozidla, které
  mu vyšly (nejmenší a největší konečná zatížitelnost), v každém bodě aspoň stejné účinky
  kombinací (g − g0 vč. dobetonávky, chodci, q; MSÚ, char, častá, kvazistálá; tolerance 0,2 %) –
  jeho využití při zatížitelnosti toho nosníku je pak nejvýše 100 %. U Vn a Vr se test dělá pro
  všechna spočtená schémata. Je-li nosník zadán (*Posuzovaný výstup* ≠ auto), počítá se jen on.
  Počet počítaných nosníků je v kapitole zatížitelnosti a v hlavičce protokolu. Protokol
  druhu (posudky při zatížitelnosti) je pro rozhodující nosník.
  (Při posouzení pro zvolené vozidlo se nosník vybírá podle MSÚ 6.10 včetně g0.)
- Výsledkem posudku je tíha [t]; dále „nezávisí na zatížení dopravou – vyhovuje /
  NEVYHOVUJE“ (napínání, minimální výztuž …), „neomezuje“ (η do zkoušené tíhy nedosáhne
  100 %), „η klesá se zatížením“ (např. křehký lom – nevyhovuje jen bez vozidla).
- **Zatížitelnost = nejmenší hodnota přes posudky** (čl. 4.1); do evidence se zaokrouhluje na
  celé tuny dolů (čl. 13.2). Program uvádí i **zatížitelnost na jednu nápravu V_aj** (čl. 5.1.7:
  největší z 3/8 Vn, resp. 3/4 Vn pod 16 t, a 1/6, 3/8, 3/4 Vr podle vozidla) a upozorní,
  je-li nutné zatížitelnost vyznačit (Vn < 26 t, Vr < 48 t, V_aj < 11,5 t; čl. 14.1).
- Karta 7: karty MSÚ, MSP a celkem s hodnotami všech druhů, ve sloupci posudků
  „Vn / Vr / Ve [t]“ (∞ = neomezuje / nezávisí, ✗ = nevyhovuje nezávisle na zatížení).
- **Protokol** (volba *Protokol a výsledky zatížitelnosti* na kartě 0, `[blc]
  protokol_zatizitelnosti`, v dávce `--protokol`):
  - *souhrn* (výchozí) – kapitola 1 „Zatížitelnost podle ČSN 73 6222“ se všemi spočtenými druhy
    (souhrnná tabulka, V_aj, popis a tabulka po mezních stavech pro každý druh); zbytek
    protokolu a grafy jsou spočteny pro zvolené vozidlo při jeho zatížitelnosti,
  - v kapitole 2.4 „Zatížení z modelu mostu (BLC)“ jsou navíc pro spočtené druhy **schémata
    zatížení** při referenční tíze (Vn = 32 t, Vr = 60 t, Ve = 80 t podle `[blc]`) – půdorys
    v poloze pro max M a max V a příčný řez s polohou zatížení; v grafu „Vnitřní síly na
    nosnících“ je místo řádku zatížení dopravou q po řádku **obálka M a V od každé referenční
    soupravy** (zvýrazněn nosník posuzovaný pro daný druh),
  - *jen Vn / jen Vr / jen Ve* – kapitola „Zatížitelnost Vr – výhradní (ČSN 73 6222)“ jen
    s tímto druhem a **posudky celého protokolu při zatížitelnosti tohoto druhu** (jeho
    rozhodující posudek má využití 100 %, schéma, nosník a chodci odpovídají druhu);
    karta 7 ukazuje výsledky téhož druhu. Po výpočtu lze volbu *protokol* v liště přepnout
    bez nového hledání
    (posudek druhu se spočte jen poprvé, ≈ 3 s); nespočtený druh se při F5 dopočítá,
  - v dávce `--protokol vse`: souhrn do `DIR/protokol.html` a protokol každého druhu do
    `DIR/<druh>/protokol.html`.
- Grafy zatížení jednotlivých druhů jsou i v seznamu grafů na kartě 7 („Zatížitelnost Vn –
  zatížení na mostě“, „… – příčný řez“).
- Trvání: desítky výpočtů posudku na každé schéma (příklad KA-67/12, všechny tři druhy
  ≈ 40 s; dávka se souhrnným protokolem ≈ 70 s, s `--protokol vse` ≈ 85 s).

### 8.6 Aktuální stáří a oslabení výztuže korozí

- **Aktuální stáří** [dny] (karta 5, časová osa; `[casova_osa] t_akt`): další posuzovaná fáze
  „Aktuální stáří“ mezi uvedením do provozu a koncem životnosti – ztráty předpětí, MSP i MSÚ
  jako v ostatních provozních fázích (zahrnuje ji i výpočet zatížitelnosti).
- **Oslabení výztuže korozí** [%] (karta 4; `[degradace] oslabeni_predpinaci`,
  `oslabeni_betonarske`, `oslabeni_smykove`) – zmenšení plochy výztuže ve fázích od
  aktuálního stáří (bez něj jen na konci životnosti):
  předpínací výztuž → předpínací síla P = σ_p·A_p·(1 − ρ_p) (napětí ve zbylé výztuži se nemění)
  a A_p v MSÚ; betonářská výztuž → A_s v ohybu a smyku MSÚ; smyková výztuž → A_sw ve smyku
  a v minimální smykové výztuži. Ztráty předpětí a průřezové charakteristiky se počítají
  pro neoslabenou výztuž.
- **Tažnost předpínací výztuže** (karta 1; `[predpinaci_vyztuz]`) má dvě pole:
  `taznost` = neoslabená ε_uk [‰] (určuje sklon stoupající větve diagramu do k·f_pd při ε_uk)
  a `taznost_oslabena` = ε_uk,red [‰] oslabená korozí (prázdné = bez oslabení). Oslabená
  tažnost diagram jen zkrátí na ε_ud,red = 0,9·ε_uk,red při stejném sklonu zpevnění – výztuž
  nedosáhne pevnosti a klesne M_Rd, pokud rozhoduje přetvoření výztuže. Uplatní se v MSÚ
  ve stejných fázích jako oslabení plochy. Pouhé snížení `taznost` naopak modeluje jinou
  (méně tažnou) výztuž se strmějším zpevněním – M_Rd tím roste, pro korozi se nehodí.
- Úprava je v balíčku posudku (`pb_posudek`, repo Posudek PB, větev `aktualni-stari-koroze`).

### 8.7 Nerovnoměrná složka teploty (ČSN EN 1991-1-5, příloha B)

Karta 5 → rámeček „Nerovnoměrná složka teploty“ (`[teplota]` ve vstupu; sekce chybí nebo
není zaškrtnuto „Uvažovat“ = teplota se neuvažuje):

- **Rozdělení teploty** po výšce průřezu h = výška nosníku z karty 2 podle obr. 6.2c a tab. B.3
  (betonová mostovka) pro **oteplení** (ΔT1, ΔT2, ΔT3) i **ochlazení** (ΔT1 … ΔT4) – podle
  svršku: `svrsek = "bez"`, `"izolace"` (vodotěsná izolace) nebo tloušťka svršku [m]
  (např. 0.18); mezi řádky tabulky lineární interpolace (h i tloušťka svršku), stejně jako
  tabulkový výpočet teploty (Excel). Výšky h1, h2, h3 (h4) podle obr. 6.2c, u oteplení
  h3 ≤ 0,1 m + tloušťka svršku. Rozdíly lze zadat i ručně: `otepleni = [ΔT1, ΔT2, ΔT3]`,
  `ochlazeni = [ΔT1, ΔT2, ΔT3, ΔT4]` (jen v souboru).
- **Primární (vlastní) napětí** – nosník je staticky určitý, takže nelineární rozdělení vyvolá
  jen napětí v rovnováze v průřezu: σ(z) = E·α·(ε̄ + κ̄·(z − z_t) − ΔT(z)), ε̄ = ∫ΔT·b dz / A,
  κ̄ = ∫ΔT·(z − z_t)·b dz / I; E = E_cm betonu (lze zadat `E`), α = 1·10⁻⁵ 1/K (`alfa`).
  Integruje se přesně po výšce skutečného betonového průřezu. Excel místo toho násobí
  průměrné přetvoření oblasti její plochou a těžiště bere z teplotního obrazce bez vlivu
  šířky – u obdélníku je to shodné, u průřezu s pásnicemi (KA) se napětí liší o ≈ 0,1 MPa
  (KA-73/15: horní vlákna při oteplení −1,05 místo −1,19 MPa).
- **Dílčí součinitele** γ, ψ pro kombinace (karta 5, sekce Dílčí součinitele zatížení; výchozí):
  charakteristická 1,0 / 0,6, častá
  1,0 / 0,6, kvazistálá 1,0 / 0,5, MSÚ 6.10a, 6.10b, 6.10 1,5 / 0,6
  (`soucinitele = { char = [1.0, 0.6], … }`). Primární napětí × γ·ψ se v **provozních
  fázích** přičte k napětí v betonu **jen nepříznivě** (rozhoduje oteplení, ochlazení, nebo
  teplota nepůsobí): tlak a tah (charakteristická), mez lineárního dotvarování (kvazistálá),
  dekomprese (častá / kvazistálá) a hlavní napětí (charakteristická). Šířka trhlin a MSÚ se
  nemění (vlastní napětí neovlivní únosnost průřezu) – součinitele MSÚ jsou jen v tabulce.
- Protokol: kapitola „Nerovnoměrná složka teploty“ (ΔT, body rozdělení, N_T, M_T, napětí
  v horních / dolních vláknech a v těžišti, součinitele) s grafem; u posudku napětí poznámka
  „teplota: oteplení / ochlazení“, rozhoduje-li teplota; graf napětí v řezech má nelineární
  průběh. Platí i pro výpočet zatížitelnosti (teplota působí stále, q se škáluje).
- Úprava je v balíčku posudku (`pb_posudek/teplota.py`, repo Posudek PB).

### 8.8 Upozornění (mez lineárního dotvarování)

Tlak v betonu vůči mezi lineárního dotvarování k2·f_ck(t) (k2 = 0,45; ČSN EN 1992-1-1, 7.2(3))
**není mezní stav** – nevstupuje do využití, výsledku VYHOVUJE / NEVYHOVUJE ani do zatížitelnosti.
Kontroluje se ve fázích po vnesení předpětí (stálá kombinace, v provozu kvazistálá); v protokolu je
krok výpočtu s poměrem |σc|/(k2·f_ck(t)). Při překročení program zobrazí **upozornění**, že je
třeba uvažovat nelineární dotvarování: v souhrnu protokolu a u příslušné fáze, na kartě 7 (pruh pod
souhrnnými kartami, počet ve stavovém řádku) a ve výpisu dávky (`! Upozornění: …`). Ztráty předpětí
a průhyb se počítají s lineárním dotvarováním (nelineární jen od předpětí při vnesení, k_σ > 0,45).

### 8.9 Soubor

Vstup Posudku PB rozšířený o sekci `[blc]` (popis klíčů v `blc_posudek/vypocet.py`). Neznámý
klíč v `[blc]` (překlep) výpočet zastaví s chybou a návrhem správného názvu – jinak by se tiše
použila výchozí hodnota.
Uložený soubor obsahuje i sekci `[zatizeni]` z posledního výpočtu mostu, takže jde otevřít
i v samostatném Posudku PB.
