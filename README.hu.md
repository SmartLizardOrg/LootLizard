# LootLizard

A LootLizard böngészőben futó, második monitorra szánt PUBG-társalkalmazás.
Képernyőmegosztás után automatikusan vizsgálja a játék képét, és felismerhető
térképen megjelöli a közösség által gyűjtött titkos helyeket. A képfeldolgozás
a saját gépeden fut; a program nem tölti fel a képernyőképeket.

**Webes alfa · 0.9.0.** Az alapnyelv angol, a magyar nyelv választható.
Nem kell asztali programot telepíteni, fiókot vagy API-kulcsot létrehozni.
[LootLizard megnyitása](https://lootlizard.pages.dev/app/) ·
[Bemutatóoldal](https://lootlizard.pages.dev/) ·
[Részletes angol dokumentáció](README.md) · [Közreműködés](CONTRIBUTING.md)

## Használat

1. Nyisd meg a landing oldalt asztali Chrome-ban vagy Edge-ben, majd válaszd az
   **Open LootLizard** gombot. Helyezd az ablakot a második monitorra.
2. Várd meg a helyi felismerőmotor és a térképreferenciák betöltését. Az első
   indítás a nagy böngészős futtatókörnyezet miatt hosszabb lehet.
3. A **Start sharing** gombbal válaszd ki a PUBG ablakát vagy monitorát a
   böngésző képernyőválasztójában. Kattints vissza a játékra.
4. Nyisd meg a játéktérképet. Az alkalmazás időszakosan, helyben frissít;
   minden új vizsgálathoz nem kell átkattintanod. A térkép megnyitásához tartozó
   játékbillentyűt az alkalmazás nem nyomja meg helyetted.
5. A **Stop**, a böngésző megosztásleállító gombja vagy az oldal bezárása
   befejezi a megosztást. Az alkalmazás eldobja a későn érkező eredményeket is.

A nyilvános térképreferenciák automatikusan betöltődnek; nem kell külön
képeket keresned vagy letöltened. Saját, teljes és négyzetes referencia opcionálisan
megadható a beállításokban. Külső forrás hibája esetén az alkalmazás jelzi a
problémát, és nem talál ki térképazonosítást. A **Load demo** eredeti, szintetikus
térképen mutatja meg a működést, játék és megosztási engedély nélkül.

## Korlátok és teljesítmény

A mellékelt, még ellenőrizetlen pontadatok 15 erangeli és 12 taegói helyet
tartalmaznak; a taegói lista hiányos. Az iránytölcsérből becsült játékospozíció
kísérleti, nem garantálja a saját játékos azonosítását. Ismeretlen vagy nem
egyértelmű térkép esetén a célpontok törlődnek. Nagy zoom, takarás és eltérő
térképverzió hibát okozhat. A távolságok közelítő, légvonalbeli értékek.

Az elsődleges cél az asztali Chrome és Edge. A webes felület hordozható, de a
képernyőmegosztás böngésző- és rendszerfüggő; más rendszereken külön validálás
kell. Ez nem teszi magát a PUBG játékot elérhetővé új operációs rendszereken.
Konzolos és mobilos képátvétel nincs beépítve.

Az alapértelmezett képrögzítési kérés 1 FPS, korlátozott képmérettel, a
felismerés alapideje három másodperc. Az optimalizálások utáni játékbeli
teljesítményjavulás még nincs újramérve. Korábbi 3 FPS-es megosztásnál az átlag
kisebb mértékben romlott, de a lassú képkockáknál nagyobb eltérés látszott.
A teljes felismerés költségét is meg kell mérni; elhanyagolható terhelést nem
ígérünk. A második monitoron maradjon látható az oldal, mert a böngésző a rejtett
vagy minimalizált lapokat lassíthatja.

## Adatkezelés és frissítések

A hálózat a nyilvános programfájlok, futtatókörnyezet, térképreferenciák és
pontadatok letöltésére szolgál. Nincs képfeltöltés, telemetria vagy AI-szolgáltatás.
A megjegyzés engedélyezésekor a beállítások, pontadatok és referenciaképek a
böngésző saját tárhelyére kerülnek. Ezek törölhetők, a böngésző is eltávolíthatja
őket; másik böngésző/profil/domain külön tárhelyet jelent.

A program új verzióját GitHub Release adja ki. A publikáló munkafolyamat az
ellenőrzött `v0.9.0-web.1` jellegű kiadásból frissíti a Cloudflare Pages által
kiszolgált `web-release` ágat. A már nyitott oldal újratöltéskor veszi át az új
programot, így a megosztás nem szakad meg kiadáskor. A közösségi pontadatokat
ettől külön, induláskor és nagyjából percenként ellenőrzi az alkalmazás.

## Fejlesztés

Python 3.12 vagy újabb szükséges a statikus oldal összeállításához:

```sh
python scripts/build_web.py
python scripts/serve_web.py --port 8765
```

Nyisd meg a `http://127.0.0.1:8765/` címet; a program útvonala `/app/`.
A webes kiadásban már nincs natív GUI, telepítő vagy Windows-frissítő.
A korábbi Windows-változat a Git-előzményekben és a `v0.8.0` tagnél megmarad.

A projektkód MIT licencű. A PUBG képeire és védjegyeire ez nem ad jogot.
A [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) tartalmazza a forrásokat és
jogi megjegyzéseket. Az alkalmazás nem hivatalos PUBG-termék; a képfeldolgozás
önmagában nem jelent hivatalos jóváhagyást vagy anti-cheat kompatibilitást.
