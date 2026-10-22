# LootLizard

Böngészős PUBG-társalkalmazás második monitorra. A megnyitott játéktérképet
helyben felismeri, és a rendelkezésre álló közösségi pincepontokkal együtt
megtartja. Képernyőképet nem tölt fel.

**Webes alfa · 0.9.0.** Alapnyelv angol, a magyar választható. Nincs telepítő,
fiók, API-kulcs, külön térképletöltés/import vagy globális gyorsbillentyű.

[LootLizard megnyitása](https://lootlizard.pages.dev/app/) ·
[Bemutatóoldal](https://lootlizard.pages.dev/) · [Angol dokumentáció](README.md)

## Használat

1. Nyisd meg asztali Chrome-ban vagy Edge-ben a második monitoron. Várd meg a
   felismerőmotor és a mellékelt térképek betöltését.
2. A **Connect PUBG window** gombbal válaszd ki a PUBG ablakát vagy monitorát,
   majd kattints vissza a játékra.
3. Nyisd meg a teljes játéktérképet. A helyi felismerés automatikus; vizsgálatonként
   nem kell átkattintani. A térképnyitás játékbillentyűjét az oldal nem nyomja meg.
4. A felismert térkép játék és inventory közben megmarad. Új térképnyitáskor
   frissül, és látszik az utolsó térképfelismerés kora. Az első felismerés után
   a játék-előnézet automatikusan összecsukódik; szükség esetén újranyitható.
5. A jól látható **Reset match** törli az előző meccs térképét, de megtartja a megosztást.
   A **Stop**, a böngésző megosztásleállítása vagy az oldal bezárása mindent töröl.

A főnézet csak a felismert térképet mutatja. A játék képe kis, mintavételezett
előnézetben látszik. Az alkalmazás nem rajzol régi jelölőket új játékkép fölé.

## Mellékelt térképek és korlátok

A webes kiadás 11 hivatalos fejlesztői referenciaképet tartalmaz: Erangel,
Miramar, Sanhok, Vikendi, Karakin, Paramo, Haven, Taego, Deston, Rondo és Training
(Camp Jackal). Nem kell külön képeket keresni vagy importálni. A PNG-k összesen
körülbelül 14,1 MB-ot jelentenek; a dekódolt képek és a felismerési minták több
memóriát igényelnek. Az eredeti képek 2024-esek, eltérhetnek a mai játéktól.
A játékbeli elérhetőség mód- és rotációfüggő; a lista nem pontossági garancia.

Közösségi pinceadat 15 erangeli és 12 taegói ponthoz van. Még ellenőrizetlenek,
a taegói lista hiányos. A többi térkép pontlistája szándékosan üres; ebből nem
következik, hogy ott nincs titkos helyiség. Kitalált pontok nem kerültek be.

A játékosoknak szánt felület térképet ismer fel és pincepontokat vetít rá.
Játékospozíció-, iránytölcsér- és körfelismerés nem fut benne. Térképváltozás,
erős zoom vagy takarás megakadályozhatja a térkép felismerését. A helyeket és a
bejáratokat a játékban ellenőrizd.

Az első felismert térképet az aktuális meccshez rögzíti, hogy ne hasonlítsa össze
mind a 11 mintát minden vizsgálatnál. Megerősített lobby/eredmény, **Reset match**
vagy megosztásleállítás oldja fel. Ha kimaradt a meccsváltás felismerése, a következő
meccs előtt használd a **Reset match** gombot, azonos térképnél is.

Többször megerősített angol lobby/eredmény képernyő automatikusan törölhet.
A tanult lábléc állandó része a játék folytatását erősítheti meg; változó utótagja,
eltűnése vagy a térkép hiánya önmagában nem indít törlést. Más nyelvnél és szokatlan
menünél kézi visszaállítás kellhet. Teljes monitor képéből a játék kilépése és az
átmeneti asztalra váltás nem különíthető el biztosan.

## Teljesítmény és adatkezelés

A vizsgálati időköz **0,5 / 1 / 2 / 5 / 10 másodperc** lehet; alapértéke **1 másodperc**.
A nyelvet és az időközt a böngésző megjegyzi. A képrögzítési kérés ehhez igazodik:
`FPS = 1000 / időközMs`, legfeljebb 2400 képpontos oldallal és négymillió mintavett
pixellel. Egyszerre egy vizsgálat fut. A kezdések távolsága legalább a feldolgozási
idő és a választott időköz közül a hosszabb; nem külön szünet adódik a feldolgozáshoz.
Lassabb feldolgozásnál sem keletkezik képkockasor.
Az első, 11 mintás keresés több másodpercig tarthat. FPS-garanciát nem ígérünk;
a teljes, optimalizált működés játékbeli képkockaidő-terhelését külön kell mérni.

A térképek, pontadatok és programfájlok ugyanarról az oldalról érkeznek. A helyi
futtatókörnyezet és az opcionális angol OCR rögzített verziójú CDN-fájlokat tölt le.
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
