# LootLizard

Böngészős PUBG-társalkalmazás második monitorra. Válaszd ki kézzel a térképet,
vagy csatlakoztasd a játék ablakát az automatikus felismeréshez. A térképet és a
közösségi helyjelölőket helyben jeleníti meg. Képernyőképet nem tölt fel.

**Webes alfa · 0.9.0.** Alapnyelv angol, a magyar választható. Nincs telepítő,
fiók, API-kulcs, külön térképletöltés/import vagy globális gyorsbillentyű.

[LootLizard megnyitása](https://lootlizard.pages.dev/app/) ·
[Bemutatóoldal](https://lootlizard.pages.dev/) · [Angol dokumentáció](README.md)

## Használat

A lap **Kézi térképválasztás** módban indul. A tizenegy térképelőnézet közül válassz egyet:
megjelenik a teljes mellékelt térkép és a rendelkezésre álló pontok. Ehhez nincs
szükség képernyőmegosztásra, engedélykérésre vagy felismerőmotorra. A **Reset map /
Másik térkép** visszavisz a csempés választóhoz a következő pálya előtt.

Az **Automatikus felismerés** használatához:

1. Válaszd az **Automatic recognition / Automatikus felismerés** módot asztali
   Chrome-ban vagy Edge-ben a második monitoron. Ekkor készül elő a helyi
   felismerőmotor és a mellékelt referenciák.
2. A **Connect PUBG window** gombbal válaszd ki a PUBG ablakát vagy monitorát,
   majd kattints vissza a játékra.
3. Nyisd meg a teljes játéktérképet. A helyi felismerés automatikus; vizsgálatonként
   nem kell átkattintani. A térképnyitás játékbillentyűjét az oldal nem nyomja meg.
4. A felismert térkép játék és inventory közben megmarad. Új térképnyitáskor
   frissül, és látszik az utolsó térképfelismerés kora. Az első felismerés után
   a játék-előnézet automatikusan összecsukódik; szükség esetén újranyitható.
5. A jól látható **Reset match** törli az előző meccs térképét, de megtartja a megosztást.
   A **Stop**, a böngésző megosztásleállítása vagy az oldal bezárása mindent töröl.

Egyszerre egy mód aktív. Kézi módra váltáskor a megosztás leáll, az automatikus
eredmény törlődik. Automatikus módra váltáskor a kézi térképválasztás törlődik.
A megosztás, meccsvisszaállítás, felismerési állapot és mintavételi beállítások
csak automatikus módban látszanak; a nyelv mindkét módban választható.

Automatikus módban a főnézet csak a felismert térképet mutatja. A játék képe kis, mintavételezett
előnézetben látszik. Az alkalmazás nem rajzol régi jelölőket új játékkép fölé.

## Nagyítás és mozgatás

A kiválasztott vagy felismert térképen görgetve az egérmutató felé nagyíthatsz, **100%-tól
(teljes térkép) 800%-ig (8×)**. Húzással mozgathatod a nézetet, hogy a sűrűbb
részeket, például Destont, közelebbről megnézhesd. A **+** és **−** gomb középre
nagyít, a **Fit map / Teljes térkép** visszaállítja az egész térképet. Tabulátorral
vagy kattintással fókuszáld a térképet: a nyilak mozgatják, a **+ / −** nagyítja,
a **0** pedig visszaállítja a teljes nézetet.

Az ikonok képernyőn látható mérete nagyításkor is állandó, az apró középpontok
továbbra is a pontos koordinátát jelzik. Azonos térkép új beolvasása megtartja a
nagyítást és a nézet helyét. Másik térkép választása, **Reset map / Másik térkép**,
**Reset match / Meccs alaphelyzetbe** vagy a megosztás leállítása visszaállítja a teljes nézetet. A mozgatás és nagyítás a
megőrzött térképet rajzolja újra, nem indít külön képrögzítést vagy felismerést;
az automatikus térképellenőrzés ettől függetlenül folytatódik, ha be van kapcsolva.
A nagyítás nem ad a forráskép felbontásán túli részleteket.

## Mellékelt térképek és korlátok

A webes kiadás 11 hivatalos fejlesztői referenciaképet tartalmaz: Erangel,
Miramar, Sanhok, Vikendi, Karakin, Paramo, Haven, Taego, Deston, Rondo és Training
(Camp Jackal). Nem kell külön képeket keresni vagy importálni. A PNG-k összesen
körülbelül 14,1 MB-ot jelentenek; a dekódolt képek és a felismerési minták több
memóriát igényelnek. Az eredeti képek 2024-esek, eltérhetnek a mai játéktól.
A játékbeli elérhetőség mód- és rotációfüggő; a lista nem pontossági garancia.

Közösségi helyadat kilenc térképhez van: Erangel, Taego, Miramar, Deston, Rondo,
Vikendi, Paramo, Karakin és Haven. Térképtől függően titkos szobákat, biztonsági
szobákat, medvebarlang-bejáratokat, alagútbejáratokat vagy lehetséges raktárépületeket
jelölnek. Taego listája a forrásban szereplő 15 titkos
szobát tartalmazza. A közösségi adatokat ebben a projektben még nem ellenőriztük
önállóan a játékban; a listák hiányosak vagy elavultak lehetnek.

A föld alatti bejáratok külön zöld alagútikont kapnak. Erangel hét külön
forrásolt bunkerbejáratot tartalmaz (ebből négy a Shelternél), Miramar pedig
három bejáratot a Los Leones melletti komplexumnál a 15 titkos szoba mellett.
Karakin 22 alagútbejárata továbbra is szerepel. Több bejárat vezethet ugyanabba
a föld alatti térbe; ezek nem további kulcsos szobák. A szobák meglévő jelölőit
nem nevezzük át pontos bejáratokká. A bejáratok közösségi megfigyelések, a
jelenlegi játékban még nem ellenőriztük őket.

Paramo tájékozódási pontjai meccsenként változhatnak; ellenőrizd a helyeket az
aktuális térképen. Haven 22 jelölője egy korábbi közösségi útmutatóban megjelölt
lehetséges Pillar-raktárépületek középpontját mutatja; meccsenként csak néhány aktív,
és a listát a jelenlegi játékban ellenőrizni kell. Nem 22 garantáltan aktív szoba.
Sanhok és Training pontlistája üres, mert nincs hozzájuk
mellékelt, forrással alátámasztott helyadat; ebből nem következik, hogy ott nincs
titkos helyiség.

Ajtó-, lakat-, barlang-, alagút- és ládajel különbözteti meg a helytípusokat a térképen
és a listában. Az apró középpont mutatja a koordinátát, az eltolt ikonhoz rövid
vonal vezet. Sűrű területen az ikon szabad helyre kerülhet vagy szám nélkül
jelenhet meg; ha nincs helye, a pontos középpont marad látható.

Az automatikus felismerés térképet ismer fel és pincepontokat vetít rá.
Játékospozíció-, iránytölcsér- és körfelismerés nem fut benne. Térképváltozás,
erős zoom vagy takarás megakadályozhatja a térkép felismerését. A helyeket és a
bejáratokat a játékban ellenőrizd.

Automatikus módban az első felismert térképet az aktuális meccshez rögzíti, hogy ne hasonlítsa össze
mind a 11 mintát minden vizsgálatnál. Megerősített lobby/eredmény, **Reset match**
vagy megosztásleállítás oldja fel. Ha kimaradt a meccsváltás felismerése, a következő
meccs előtt használd a **Reset match** gombot, azonos térképnél is.

Többször megerősített angol lobby/eredmény képernyő automatikusan törölhet.
A tanult lábléc állandó része a játék folytatását erősítheti meg; változó utótagja,
eltűnése vagy a térkép hiánya önmagában nem indít törlést. Más nyelvnél és szokatlan
menünél kézi visszaállítás kellhet. Teljes monitor képéből a játék kilépése és az
átmeneti asztalra váltás nem különíthető el biztosan.

## Teljesítmény és adatkezelés

Automatikus módban a vizsgálati időköz **0,5 / 1 / 2 / 5 / 10 másodperc** lehet; alapértéke **1 másodperc**.
A nyelvet és az időközt a böngésző megjegyzi. A képrögzítési kérés ehhez igazodik:
`FPS = 1000 / időközMs`, legfeljebb 2400 képpontos oldallal és négymillió mintavett
pixellel. Egyszerre egy vizsgálat fut. A kezdések távolsága legalább a feldolgozási
idő és a választott időköz közül a hosszabb; nem külön szünet adódik a feldolgozáshoz.
Lassabb feldolgozásnál sem keletkezik képkockasor.
Az első, 11 mintás keresés több másodpercig tarthat. FPS-garanciát nem ígérünk;
a teljes, optimalizált működés játékbeli képkockaidő-terhelését külön kell mérni.

A térképek, pontadatok és programfájlok ugyanarról az oldalról érkeznek. Kézi módban
a CV- és OCR-munkafolyamatok nem indulnak el. A felismerőmotor az automatikus mód
kiválasztásakor töltődik be, az opcionális angol OCR szükség esetén indul;
mindkettő rögzített verziójú CDN-fájlokat használ, és helyben fut.
Nincs képfeltöltés, telemetria vagy AI-szolgáltatás. Képek, eredmények, OCR-szöveg
és láblécminta a memóriában marad; a beállításokat a böngésző helyben megjegyezheti.
Nincs külön referencia-import vagy pontadatfrissítő gyorsítótár.

A kód, térképek és pontadatok együtt, GitHub Release után frissülnek a Cloudflare
Pages oldalán. Nincs futás közbeni GitHub-metaadat-lekérés vagy külön publikáló ág.
Újratöltéskor érkezik az új kiadás; a már futó megosztást nem szakítja meg egy
kiadás. Újratöltés után újra ki kell választani a megosztandó forrást.

Asztali Chrome/Edge az elsődleges cél. A képernyőmegosztás böngésző- és
rendszerfüggő; más platform külön ellenőrzést igényel. A weboldal nem teszi magát
a PUBG-t elérhetővé új operációs rendszereken. Konzolos/mobilos képátvétel nincs
beépítve. Az oldal maradjon látható a második monitoron.

## Fejlesztés és jogok

Python 3.12+ kell a statikus összeállításhoz:

```sh
python scripts/build_web.py
python scripts/serve_web.py --port 8765
```

Nyisd meg a `http://127.0.0.1:8765/` címet; az alkalmazás `/app/`. A forráskód MIT
licencű, a mellékelt PUBG-képek jogai a tulajdonosaiknál maradnak. Források és
feltételek: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Privát képernyőkép,
személyes profil vagy helyi értékelési referencia nem része a kiadásnak.
