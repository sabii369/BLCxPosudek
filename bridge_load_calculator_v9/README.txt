BRIDGE LOAD CALCULATOR v9
Posouzení přechodnosti vojenských vozidel MLC na mostech – porovnání s výjimečnou
zatížitelností Ve, deskový model (2D MKP), spojitý nosník o více polích, šikmé mosty,
volitelné okrajové podmínky podpor (kloub tvrdý / měkký, vetknutí, pružné vetknutí).
==================================================================================

  Změna 13. 10. 2026: u mostů z nosníků se spárou jsou podepřeny VŽDY jen nosníky,
  spára vlastní podporu nemá – nově i u kolmého mostu (dříve se u α = 90° podpíraly
  všechny pruhy včetně spár, u šikmého mostu jen nosníky). k_v a k_φ se vztahují
  na šířku nosníků N·b (i v 1D modelu). Mosty bez spáry, šikmé mosty a desky beze
  změny. Kolmé nosníky se spárou: M+ beze změny, V(d) v kontrolních řezech o 2–4 %
  menší (tvrdé uložení), max |V| u čela nosníku v obálkách vyšší, u vetknutí
  |M-| nad podporou +7 % (vetknuty jsou jen nosníky).


1) PŘED PRVNÍM SPUŠTĚNÍM
----------------------------------------------------------------------------------

1.1  Instalace Pythonu (jen jednou na počítači)

  a) Stáhněte instalátor Pythonu 3 pro Windows (doporučeno 3.11 nebo novější):
         https://www.python.org/downloads/windows/
     (přímo nejnovější verze: https://www.python.org/downloads/ → „Download Python 3.x“)
     Vyberte „Windows installer (64-bit)“.

  b) Spusťte stažený soubor python-3.x.x-amd64.exe a V PRVNÍM OKNĚ:
       [x]  zaškrtněte  „Add python.exe to PATH“      ← důležité!
       pak klikněte na „Customize installation“ a zkontrolujte, že je zaškrtnuto
       [x]  pip
       [x]  tcl/tk and IDLE                             ← potřeba pro grafické okno
     a dokončete instalaci („Next“ → „Install“).



1.2  Instalace potřebných balíčků (jen jednou)

  Ve složce programu spusťte dvojklikem   setup.bat
  Skript nainstaluje přes pip balíčky:  numpy, scipy, matplotlib, openpyxl
  (seznam je v requirements.txt), ověří jejich načtení a zkontroluje tkinter.
  Na konci má být „Hotovo“. Je potřeba připojení k internetu.

  Ruční varianta (příkazový řádek ve složce programu):
         python -m pip install -r requirements.txt


2) SPUŠTĚNÍ
----------------------------------------------------------------------------------

  • Grafické rozhraní:  dvojklik na  spustit_v9.bat
                        (nebo v příkazovém řádku:  python main.py)
  • Ukázkový výpočet v konzoli + uložení grafů do PNG:   python main.py --demo





3) OVLÁDÁNÍ – VSTUPY
----------------------------------------------------------------------------------

  Konstrukce
    Prefabrikát ........... předvyplní rozpětí, šířku b, Iy a spáru z tabulky
                            Prefabrikáty.xlsx (hledá se ve složce programu a ve
                            složce nad ní; bez souboru se použije vestavěná kopie).
                            Hodnoty lze potom libovolně přepsat.
    Typ konstrukce ........ nosníky  – mostovka z N nosníků (hodnoty na nosník)
                            deska    – jedna deska šířky b a tloušťky h
                                       (hodnoty zintegrované na pás šířky 1 m)
    Počet polí, L1 … Ln ... spojitý nosník o n polích
    N, b, Iy .............. počet nosníků, šířka nosníku, moment setrvačnosti nosníku
    h ..................... tloušťka desky (jen typ „deska“)
    Třída betonu .......... E = Ecm dle ČSN EN 1992-1-1
    Spára ................. podélná spára mezi nosníky: šířka b_s, Iy spáry,
                            beton spáry (dobetonávka); spojení se spárou kloubové;
                            spára vlastní podporu nemá (podepřeny jsou vždy jen
                            nosníky – kolmý i šikmý most)
    d ..................... statická účinná výška – posouvající síla se posuzuje
                            v řezu ve vzdálenosti d od podpory
    Úhel šikmosti α ....... 90° = kolmý most, šikmost roste směrem k 180°
                            (teoretická mez); zadává se 90° až 165°
    Druh šikmosti ......... pravá / levá
    Tuhost podpory k_v .... svislá tuhost liniové podpory [MN/m na 1 m délky podpory]
                            (pružné uložení); prázdné nebo 0 = tuhá podpora.
                            Výchozí 2000 MN/m/m, viz bod 2a.
    Uložení podpor (v9) ... okrajové podmínky – jednou pro celý most, viz bod 2b:
                              kloub tvrdý  – natočení podél osy podpory zabráněno
                                             (u pružné podpory sleduje průhyb)
                              kloub měkký  – obě natočení volná
                              vetknutí     – navíc zabráněno natočení kolem osy
                                             podpory
    Tuhost vetknutí k_φ ... jen u vetknutí: [MNm/rad na 1 m délky podpory];
                            prázdné = dokonalé vetknutí
    β_s = 0 i u pružné .... režim v8 (a SCIA s pružnou podporou a vetknutou rotací
    podpory                 podél podpory) – jen pro srovnání, viz bod 2b

  Zatížení
    Typ vozidla, třída MLC, vzdálenost vozidel v koloně, výjimečná zatížitelnost Ve,
    počet poloh vozidla na pole, příčná poloha MLC (posuvník, „auto střed“)

  Výpočet
    Propojení nosníků (kloubové / deskové), roznos kola do střednice desky,
    tloušťka vozovky, velikost prvku MKP (doporučeno 0,125 m; 0,0625 m pro V u
    šikmých mostů; 0,25 m pro rychlý orientační výpočet), obálky na nosnících (delší výpočet), krok poloh pro obálky,
    převýšení grafů sil v půdorysu.


4) JAK FUNGUJE VÝPOČET (stručně)
----------------------------------------------------------------------------------

  1. 1D analýza celého mostu (spojitý nosník, konstantní EI)
     Vozidlo MLC (kolona) a schéma Ve se posouvají po mostě v obou směrech jízdy
     s podélným roznosem plošky. Pro každý kontrolní řez se najde nejnepříznivější
     poloha:
        M+   maximum kladného momentu v každém poli,
        M-   záporný moment nad každou vnitřní podporou (u vetknutí i nad
             krajními podporami),
        V    posouvající síla v řezech x_k ± d u každé podpory (zatížení smí stát
             kdekoli, i v pásu d u podpory).
     U šikmého mostu probíhá 1D výpočet v ose vozidla.

  2. 2D deskový model (MKP, prvky MITC4 – Mindlinova deska, smyková tuhost
     κ·G·h s κ = 5/6 – stejně jako SCIA)
     Rozhodující poloha z bodu 1 se zadá do 2D modelu, který rozdělí zatížení
     napříč mostem:
        nosníky – každý nosník je pruh desky s náhradní tloušťkou h = (12·Iy/b)^(1/3),
                  spojení kloubové nebo tuhé, volitelně spáry;
                  každý nosník je podepřen liniově přes celou šířku čela
                  (kolmo k ose); šikmý most: nosníky s kolmým čelem posunuté
                  podle šikmé osy podpory, podpora v místě průsečíku osy
                  nosníku s osou podpory. Spára vlastní podporu NEMÁ (kolmý
                  i šikmý most) – její okraje jsou podepřeny přes kloub
                  s nosníky; (u šikmých nosníků bez spáry program zobrazí
                  upozornění),
        deska   – kosoúhlá síť rovnoběžná s osou podpory, liniové kloubové uložení
                  podél šikmé osy podpory.
     Vnitřní síly se počítají vždy ve směru osy prvku. Podpory jsou liniové,
     ve svislém směru tuhé nebo pružné (k_v, bod 2a), okrajové podmínky natočení
     podle volby uložení (bod 2b); stejné podmínky se použijí i v 1D modelu.

  2a. Pružné podpory – jak nastavit k_v
     Proč: u šikmého mostu mají sousední nosníky podpory posunuté. Tuhá (nepoddajná)
     liniová podpora pak v místě, kde se nosníky o sebe opírají, vytvoří soustředěné
     „parazitní“ reakce (stovky kN v jednom uzlu, s opačnými znaménky), které se se
     zjemněním sítě nezmenšují – jde o singularitu modelu, ne o skutečné chování.
     Skutečné ložisko (elastomer) je poddajné; pružina tuto singularitu odstraní.

     Doporučení: k_v = tuhost skutečných ložisek přepočtená na 1 m podpory
         k_v = n_ložisek_pod_nosníkem · K_ložiska / b_nosníku
         K_ložiska = A · E_c / Σt,   E_c = 1 / ( 1/(5·G·S²) + 1/E_b )   (EN 1337-3)
         G ≈ 0,9 MPa, E_b ≈ 2000 MPa, S = a·b / (2·t·(a+b)) pro vrstvu tloušťky t
     Typicky:   elastomer 200×300, Σt = 24 mm   K ≈ 0,6 GN/m
                elastomer 300×400, Σt = 40 mm   K ≈ 1,2 GN/m
                elastomer 400×500, Σt = 44 mm   K ≈ 1,7 GN/m
     → pro nosníky I/KA s 2 ložisky: k_v ≈ 1000–3000 MN/m/m (výchozí 2000).
     Uložení na betonový / maltový podklad, ocelová ložiska: k_v ≈ 10000 MN/m/m.

     Zdůvodnění (parametrická studie, MLC80, prefabrikáty I-62/24, I-73/30,
     KA-61/12, KA-67/18, KA-61/21, α = 90–135°, k = tuhá … 100 MN/m/m):
       • Sednutí podpory je při k_v = 1000–3000 MN/m/m jen 0,4–1 % průhybu pole
         (ρ = 38,4·EI/(k_v·b·L³)) – globální chování mostu se nemění.
       • Kolmý most: M beze změny (0,0 %), V(d) do ±2 %.
       • POZOR (v9): následující dva body platí pro v8, kde u pružné podpory
         zůstávalo β_s = 0. Taková vazba vytváří parazitní smyk κGh·∂w/∂s podél
         podpory, který uměle „vyhladil“ reakce a snížil V(d). Ve v9 (β_s = ∂w/∂s)
         je V(d) při k_v = 2000 prakticky stejné jako u tuhé podpory (I-62/24 se
         spárou: α 90° −1 %, 105° −0,4 %, 120° +0,8 %; v8: +1,3 / −5,5 / −11,3 %)
         a M+ šikmých nosníků vzroste víc (105°: +1,9 %, 120°: +4,8 %; v8 +0,6 /
         +1,5 %) – konec nosníku se na pružných ložiscích může natočit kolem své osy.
       • (v8) Šikmý most se spárou: M se změní o 0,3–2,5 %, špičky reakcí v uzlech
         klesnou (190 kN → 50 kN).
       • (v8) V(d) šikmého mostu proti tuhé podpoře klesne o 1–10 %. Mezi 1000
         a 3000 MN/m/m se M liší < 1,2 %, V(d) o 1,5–3 %.
         V u podpory šikmého mostu je citlivé na velikost prvku – pro V použijte
         prvek 0,0625 m (srovnání se SCIA: 0,125 m dává V u ostrých rohů o ~8 %
         méně, 0,0625 m o ~4 % méně, M se shoduje na ±0,3 %).
       • k_v pod ~300 MN/m/m nedávejte (pokud ložiska nejsou opravdu tak měkká):
         poddajnost pak začne měnit příčný roznos (M +2–6 % při 300 MN/m/m,
         +5–12 % při 100 MN/m/m, α ≥ 110°).
       • Šikmé nosníky BEZ spáry: výsledky silně závisí na k_v i při realistických
         hodnotách (model je přetuhý) – program varuje; je-li mezi nosníky zálivka,
         zadejte ji jako spáru.

  2b. Okrajové podmínky podpor (v9) – co znamenají a kdy je použít
     s = směr osy podpory, n = normála k ní v půdorysu; β_s = natočení (sklon)
     podél osy podpory, β_n = natočení kolem osy podpory (ohybové).

     kloub tvrdý (výchozí) – w = 0 / pružina k_v, β_s = 0. U pružné podpory
          β_s = ∂w/∂s: linie podpory se natáčí s průhybem ložisek, nevzniká
          parazitní smyk. Odpovídá podpoře s koncovým příčníkem nebo tuhou
          opěrou, která brání deformaci (zborcení) průřezu nad podporou.
     kloub měkký – jen w; β_s i β_n volné. Odpovídá liniové podpoře s volnými
          rotacemi (výchozí liniová podpora v SCIA). Pozor: u Mindlinovy desky
          vzniká u měkké podpory okrajová vrstva šířky ~h, V u podpor pomalu
          konverguje se sítí (doporučen prvek ≤ 0,0625 m); srovnání se SCIA:
          viz LOAD\Claude outputs\V_SCIA_analyza.
     vetknutí – jako tvrdý kloub + β_n = 0 (dokonalé), nebo rotační pružina
          k_φ·ℓ na β_n (pružné vetknutí; ℓ = skutečná délka podpory příslušná
          uzlu). Platí pro všechny podpory včetně vnitřních (spojitá rámová
          konstrukce). Nad vnitřní vetknutou podporou je skok M; v uzlu podpory
          se uvádí strana s větší |M|. Přibudou řezy M- nad krajními podporami.
          Orientačně: k_φ ≈ 4·E·I_stěny / h_stěny na 1 m (opěra/stěna vetknutá
          v patě), k_φ → 0 = kloub.
     β_s = 0 i u pružné podpory – chování v8; dává shodu s modelem SCIA, kde
          je u pružné liniové podpory vetknuté natočení podél podpory (např.
          „natočení kolem osy nosníku zakázané“). Jen pro srovnání / regresi.

     Ve 2D modelu desky se m_x nad podporou (vnitřní podpora, vetknutí) bere
     lineární extrapolací z vnitřních uzlů pole – v8 použila hodnotu z rohů
     prvků z jedné strany, která konverguje pomalu (prvek 0,25 m: |M-| nad
     vnitřní podporou o ~3–5 % menší, 0,125 m o ~2 %). M+ a V se nemění.
     Reakce v uzlech pružné podpory = síla v pružině k_v·w.

  3. Posouzení
     V každém řezu:  využití = max hodnota na nosníku (pásu 1 m) od MLC
                               / max hodnota od Ve.
     Rozhoduje řez s největším využitím; < 100 % → PROJDE. Pro srovnání se uvádí
     i využití 1D (celý most bez příčného roznosu).

  4. Kontrola modelu
     Součet sil na všech nosnících (a spárách) se porovnává se statikou 1D nosníku
     (odchylka má být ~0 %; platí i pro pružné podpory a vetknutí – u vetknutí
     se porovnává mimo uzly podpor, kde je skok M). U šikmé desky se kontrola
     neprovádí.


5) VÝSTUPY
----------------------------------------------------------------------------------

  Tabulka po kontrolních řezech: 1D a 2D hodnoty MLC a Ve, využití, rozhodující
  nosník / pás. Pod ní souhrn (rozhoduje, PROJDE / NEPROJDE).

  Grafy (tlačítka dole; „Řez“ vybírá kontrolní řez, „(rozhodující)“ = automaticky):
    Zatížení – Mmax, Vmax .... poloha MLC a Ve v rozhodujícím stavu (pohled, půdorys)
    Průběhy – MLC / Ve ....... M a V na nosnících v půdorysu pro vybraný řez
    Příčný roznos ............ hodnoty na jednotlivých nosnících / pásech v řezu
    Obálky nosníky – MLC / Ve  obálky M a V na každém nosníku (2D pojezd)
    Obálky 1D ................ obálky celého mostu, MLC vs Ve
    Využití po řezech ........ přehled využití 1D a 2D
    Síť MKP .................. půdorys sítě: prvky nosníků / spár / desky, podepřené
                               uzly (tuhé / pružné), podélné klouby, počet prvků
                               a DOF, typ uložení (lupou v okně grafu lze síť
                               zvětšit)


6) OMEZENÍ A POZNÁMKY
----------------------------------------------------------------------------------

  • Stejný průřez ve všech polích; podpory vždy liniové, svisle tuhé nebo pružné
    se stejnou tuhostí k_v a se stejnými okrajovými podmínkami natočení na všech
    podporách (uložení se volí jednou pro celý most).
  • k_v se vztahuje na 1 m podpory měřený napříč mostem (průmět), k_φ na 1 m
    skutečné délky šikmé osy podpory (rozdíl 1/sin α', u 105° 3,5 %). U nosníků
    je podepřená délka jen šířka nosníků N·b (bez spár), i v 1D modelu.
  • U nosníků se spárou je podepřeno (a vetknuto) jen čelo nosníků; spára
    vlastní podporu nemá – u kolmého i šikmého mostu (od 13. 10. 2026).
  • Pro každý kontrolní řez se ve 2D řeší jeden zatěžovací stav vybraný podle 1D
    kritéria (nejde o úplné prohledání všech poloh ve 2D).
  • Náhradní deska nosníku má torzní tuhost plného průřezu – u šikmých mostů
    z nosníků bez spáry může být vliv šikmosti nadhodnocen.


7) SOUBORY
----------------------------------------------------------------------------------

  setup.bat ........ instalace balíčků (před prvním spuštěním)
  spustit_v9.bat ... spuštění programu
  requirements.txt . seznam potřebných balíčků
  main.py .......... spouštěcí skript (GUI / --demo)
  gui.py ........... grafické rozhraní
  comparison.py .... řízení výpočtu, porovnání MLC vs Ve
  beam_1d.py ....... 1D analýza spojitého nosníku, pojezd vozidel
  plate_fem.py ..... 2D MKP model nosníků (pruhy, spáry, šikmost)
  slab_fem.py ...... 2D MKP model desky (kosoúhlá síť)
  geometry.py ...... geometrie, kontrolní řezy, třídy betonu
  vehicles.py ...... parametry vozidel MLC
  prefabrikaty.py .. načtení tabulky prefabrikátů
  plotting.py ...... grafy
  test_v9.py ....... ověřovací testy (pro regresi proti v8 musí být složka
                     bridge_load_calculator_v8 vedle složky v9)
