# LootLizard 0.7.0 — Magyar gyorsindító

[English documentation](README.md)

Kísérleti, nyílt forrású Windows-program a [SmartLizardOrg](https://github.com/SmartLizardOrg) alatt, amely kérésre készült PUBG-képen jelöli az ismert titkosszoba-koordinátákat a második kijelzőn. A **Ctrl+Shift+B** a kiválasztott monitorról kér képet, és a képfeldolgozás helyben, offline fut. A közösségi pontadatok frissítése GitHub HTTPS-kéréseket használ; képet nem küld el. Nem folyamatos követés; a következő képkérésig az előző állapotot látod.

A **0.7.0** saját, helyi teljes térképminták katalógusának betöltésével azonosítja a minták közt szereplő pályát, és támogatott nagyítás/mozgatás után is a helyére vetíti a pontokat. Automatikus nézésitölcsér-keresés és opcionális városnév-olvasás is elérhető. **A pincejelöléshez nem kötelező saját ikonmintát betanítani.** A csomag **15 Erangel- és 12 Taego-koordinátát** tartalmaz. Mindkét közösségi adatsor ellenőrizetlen; a Taego-lista kifejezetten hiányos. Játéktérképképet vagy személyes profilt nem mellékelünk.

A Windows-csomagok helye a [Releases](https://github.com/SmartLizardOrg/LootLizard/releases). Pontjavítást vagy új pályaadatot pull requesttel küldhetsz: [CONTRIBUTING.md](CONTRIBUTING.md).

A 0.6 új felületén a térkép kapja a főszerepet: apró, pontos borostyánsárga helyjelölők mellett kis számozott címkék, türkiz **YOU** (magyarul **TE**) sajátjelölő, szélesebb célpontlista és külön Beállítások ablak. Minden látható ismert pincét megjelöl; a kör és a távolság határozza meg a sorrendet. A számcímke mérete **Settings > General > Marker size** alatt Large vagy Medium lehet; alapértelmezés a Large. A helyet mutató apró pont mindkét méretnél változatlan.

Az opcionális ikonminta megjelenést ismer fel, nem játékosazonosságot. Más szín/sorszám, azonos kinézetű csapattárs vagy más jel téves egyezést okozhat. A saját játékos Solo/Squad helyzetek közötti megkülönböztetése nincs igazolva. Nincs hivatalos PUBG-jóváhagyás vagy kapcsolat.

## Indítás és nyelv

A teljes ZIP-et bontsd ki, majd indítsd a `LootLizard.exe` fájlt. Az `_internal` könyvtár maradjon mellette. A `start-pubg.cmd` a companion mellett Steamen keresztül a PUBG indítását is kéri. Nincs telepítő vagy kódaláíró tanúsítvány.

Forrásból Windows és Python 3.12 vagy újabb, Tkintert is tartalmazó telepítés kell. A projekt könyvtárában, PowerShellből:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m lootlizard
```

A felület alapértelmezett nyelve **English**. A **Settings > General > Language > Magyar** választással azonnal magyarra vált; a beállítást helyben megjegyzi. A nyelvváltás megőrzi a képet, beállítási lépést és eredményt. Az alábbi gombnevek az angol felület nevei. A **Settings > General > Help** a beépített útmutatót nyitja meg.

## Közösségi pontadatok automatikus frissítése

A **Settings > General > Map updates** részben az **Automatic map updates** alapértelmezetten be van kapcsolva. Indításkor, majd futás közben körülbelül 60 másodpercenként ellenőrzi a [nyilvános pontkatalógust](https://raw.githubusercontent.com/SmartLizardOrg/LootLizard/metadata/maps.json). A **Check now** kézi ellenőrzést kér, a szerver által kért várakozást ez is betartja. A jelölőnégyzet kikapcsolása az automatikus kéréseket állítja le.

GitHub workflow-várakozás, CDN-gyorsítótár vagy hálózati hiba miatt a frissítés késhet; ez nem azonnali értesítés. Az utolsó érvényes letöltés a `%LOCALAPPDATA%\LootLizard\maps-cache.json` fájlban marad. Offline a korábbi érvényes adatokkal működik; ha még nincs letöltés/gyorsítótár, a mellékelt pontokat használja. A katalógus teljes pillanatkép, így közösségi pontok törlését is átvezeti. A kézzel importált helyi JSON-ok elsőbbséget élveznek azonos pályaazonosítónál, és a program nem írja felül őket.

Új közösségi pálya pontadata **nem készít térképfelismerő mintát**: a kirajzoláshoz továbbra is kell a megfelelő saját, helyi teljes térképkép. A `main` ág `data/*.json` fájljait PR-ben lehet javítani; beolvasztás után a metadata workflow egyben ellenőrzi és publikálja a teljes pontkatalógust. Ez adatfrissítés, nem programkód- vagy képletöltés; kódváltozáshoz új alkalmazásverzió kell.

## Helyi térképkatalógus: ikon nélkül is, támogatott zoommal

1. A **Settings > General** lapon válaszd ki a játék és a companion monitorát. A segédablak teljesen a második kijelzőn legyen.
2. Készíts saját képet az adott pálya teljesen kizoomolt térképéről. Képszerkesztőben vágd ki a teljes, pontos négyzetes térképet, a környező felület nélkül. **RGB PNG vagy JPEG** legyen. A kép a teljes normalizált térképet ábrázolja, ne egy nagyított részletet. Korábbi profilod `reference.png` fájlja is használható, ha eredetileg helyes pályát és teljes térképkeretet jelöltél ki.
3. A képek mellé készíts `catalog.json` fájlt az alábbi formában. A program meglévő katalógust importál; ezt a fájlt és az új teljes térképkivágást nem készíti el helyetted.
4. Válaszd a **Settings > Advanced > Load local map catalog…** gombot, majd a JSON-fájlt. A program a katalógus elérési útját jegyzi meg; a képek a kiválasztott helyen maradnak. Következő indításhoz is maradjanak ott. Nem tölt le és nem másol be képet a programcsomagba.
5. Nyisd meg a játéktérképet támogatott nagyítással/eltolással, majd **Ctrl+Shift+B**, vagy **Open image…**. A feldolgozó azonosítja az egyértelmű térképmintát, kiválasztja a hozzá tartozó betöltött/beépített pontadatot, és kirajzolja a látható pontokat. Ehhez nem kell ikonminta vagy frissítésenként átkattintás.

Példa helyi könyvtár:

```text
my-map-references/
  catalog.json
  erangel-full.png
  taego-full.png
```

Példa `catalog.json`:

```json
{
  "schema_version": 1,
  "references": [
    {"map_id": "erangel", "file": "erangel-full.png"},
    {"map_id": "taego", "file": "taego-full.png"}
  ]
}
```

Csak a ténylegesen meglévő mintákat sorold fel. Minden `map_id` egyedi legyen, és pontosan egyezzen a pontadat azonosítójával. Beépített koordináták az `erangel` és `taego` azonosítókhoz vannak; más mintához azonos azonosítójú pont-JSON importálható az **Import JSON…** gombbal. Azonosított, de pontadat nélküli pályára nem rajzol jelölést. A katalógus betöltése nem igazolja, hogy helyesen nevezted el vagy vágtad ki a mintát.

Egy bejegyzés opcionális `sha256` mezője a mintakép 64 hexadecimális számjegyű SHA-256 értékét ellenőrzi betöltéskor. PowerShellben így kérhető le:

```powershell
(Get-FileHash .\erangel-full.png -Algorithm SHA256).Hash.ToLowerInvariant()
```

A `file` a katalógus könyvtárához viszonyított útvonal. Alkonyvtár megengedett; abszolút útvonal, szülőkönyvtárba lépés és kifelé mutató szimbolikus hivatkozás nem. A katalógus legfeljebb 128 KiB és 32 különböző térkép lehet. A mintakép RGB PNG/JPEG, legfeljebb 64 MiB, oldalanként 128–8192 képpont, összesen legfeljebb 40 millió képpont. Megközelítőleg négyzetes, a teljes térképen eloszló részleteket tartalmazó minta kell; használj pontos négyzetes kivágást.

Az illesztés eloszló SIFT-részleteket és ellenőrzött hasonlósági transzformációt használ, kis oldalarányhibára korlátozott affin korrekcióval. Nem általános PUBG-pályafelismerő: hiányzó minta, kevés vagy többértelmű egyezés, túl nagy zoom, nem támogatott forgatás/torzítás, bezárt térkép és csak minitérképes nézet ismeretlen maradhat. A kis helyi adatsorban két szélsőséges nagyítású kép már elutasítást kapott.

A 0.4.1 a térkép belsejében is eloszló egyezéseket követel. A különböző pályák szélén megjelenő azonos rácsfeliratok és felületi ikonok önmagukban akkor sem igazolják a térképet, ha pontosan illeszkednek. Egy kis ismétlődő belső részlet sem elegendő; több valóban alátámasztott minta továbbra is többértelmű elutasítást eredményez.

A **Disable map catalog** visszakapcsolja a régi, rögzített elrendezésű működést; a mentett ikonprofiljaid megmaradnak.

## Automatikus tölcsérkeresés és városnevek

Katalógusos módban az ellenőrzött térképen automatikusan keresi a tömör, színes ikont és a széles, kifelé halványuló nézési tölcsér két szélét. Nem kell előre megadnod az ikon helyét, méretét, színét vagy mintáját. Egyértelmű találatnál a **YOU** (magyarul **TE**) jelölőt, becsült pozíciót jelző leírást és becsült légvonalbeli távolságokat látsz. Az inverz térképillesztés a nagyítást és eltolást is figyelembe veszi. Több lehetséges tölcsér vagy a régi ikonprofil eltérő találata esetén nincs automatikus pozíció. Hiányzó tölcsérnél a megfelelő, egyértelmű régi ikonprofil még használható.

Visszajátszáshoz/megfigyelői képhez kapcsold be a **Settings > General > Replay / observer image** opciót: ilyenkor minden automatikus játékosbecslés kikapcsol, az ikonprofilé is. Alapértelmezés az élő játék; a program nem osztályozza automatikusan ezt a két helyzetet. Kézi ellenőrző pozíció továbbra is megadható. Új kép vagy üzemmódváltás törli a régi becslést.

A kis fejlesztési adatsoron az öt, névsor alapján azonosított élő Training-jelölőből hármat megtalált; a kurzorral takart és a zsúfolt hátterű példán nem adott találatot. Egy régi élő profilképen is megtalálta a tölcsérjelöltet: összesen **4/6 képpélda**, legfeljebb **2,7 forrásképpont** eltéréssel. A régi profilkép nem igazol önállóan játékosazonosságot. A 17 replay/katalógus/betöltés/játéknézet képen élő módot feltételezve sem adott középpontot, és a külön replay-tiltás is működött. Négy Taego-képet a detektor rögzítése után értékeltünk; független élő teszt még nincs. Ez nem általános csapattárs-/sorszám-/szín-/jelölőtű-felismerési pontosság.

Ha a geometriai illesztés sikertelen, a helyi Windows OCR legalább két különböző támogatott városnévből Erangel- vagy Taego-tippet adhat. A közös szavak — például School, Prison, Terminal, Camp — önmagukban nem azonosítanak pályát. A felület kicsinyítést kér, és a pontokat továbbra sem rajzolja ki: névből még nem ismert a nagyítás és eltolás.

Az OCR telepített angol Windows-felismerőt használ, legfeljebb nyolc másodperces kerettel, rejtett helyi PowerShell-folyamatban. Nem telepít és nem tölt le semmit, a képet nem menti vagy küldi hálózatra. Hiányzó nyelvi csomag vagy API esetén nincs tipp. A Microsoft asztali támogatása [csomagazonosságot/MSIX-et ír le](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr); a nálunk működő, csomagazonosság nélküli híd opcionális, más gépen nem garantált. A 24 mentett képből 12 Erangel/Taego-nézeten öt helyes tipp és hét kihagyás volt; hét negatív és öt Camp Jackal-képen nem adott tippet. A két korábbi extrém nagyítást, a 0013/0014 képet ez sem oldja meg.

## Korábbi profilok és opcionális ikontávolság

Katalógus nélkül a korábbi út továbbra is használható: a megfelelő pontadathoz nyiss teljesen kizoomolt térképet, kérj/importálj képet, majd **Select map bounds**, és kattints a térkép bal felső, illetve jobb alsó sarkára.

Automatikus ikonalapú távolsághoz a **Save your icon sample** után jelöld ki az ikon szoros, 7–90 forrásképpontos keretét, 2–3 képpixeles háttérszegéllyel. Ezután kattints az ikon jól látható, tömör, egyszínű pontjára a kereten belül. Sikeres, egyértelmű egyezéskor helyben megmarad a térképkivágás, bináris maszk és profiladat. Kézzel ellenőrzött pozíció a megjelenített térképre kattintva is megadható.

Ellenőrizd a maszkot és a találat helyét: a program nem tudja, hogy a saját játékosodat választottad-e. Szín/sorszám, ikon, felbontás, felületi méretarány vagy képkivágás változásakor új minta kellhet. Azonos megjelenésű csapattárs téves, akár egyértelmű találat lehet.

**A katalógusos térképillesztés nem teszi zoomfüggetlenné a régi ikonprofilt.** Az továbbra is az eredeti képméretet és közel változatlan teljes térképelrendezést várja. Nagyításnál ezért hiányozhat az ikontalálat és a távolság, miközben a térképre vetített pontok láthatók maradnak. Opcionális ikonbetanításhoz teljes térkép kell.

## Eredmények és fehér kör

A játékban térkép megnyitása → **Ctrl+Shift+B**. A billentyű nem nyitja meg helyetted a térképet. A főnézetben a térkép, célpontok, rövid állapot és a pillanatkép kora látható. A **Refresh map** gombbal a segédprogramból is kérhetsz képet. A részletes felismerési üzenetek, gyorsbillentyű-regisztráció és beérkezett kérések a **Settings > Diagnostics** lapon vannak. Fekete vagy hiányzó játékkép esetén próbálj keret nélküli/ablakos módot vagy képimportot.

A képen csak a látható területre vetülő pontokat rajzolja ki. Ellenőrzött katalógusminta és hozzá tartozó pontadat esetén a táblázat a teljes megfelelő pontadatsort tartalmazza, a képen kívülieket is. Katalógusos módban függőben lévő, ismeretlen vagy pontadat nélkül azonosított pályán **üres a táblázat, és nincs térképi jelölés**. A régi, rögzített elrendezésű mód megtartja a korábbi pontlistáját. Új kép kérése törli az előző vetítést, pozíciót, kört és távolságokat; régi feldolgozási eredmény nem állíthatja vissza őket.

Minden látható pince koordinátáját apró borostyánsárga pont és rövid célkereszt mutatja. Egy vékony szár köti össze a mellette lévő számcímkével, így a szám nem takarja el a helyet. A szám a listabeli sorrenddel egyezik; a listából, a pontra vagy címkéjére kattintva kiemelhetsz egy célpontot. Az első három távolság szerint rangsorolt célpont rövid távolságfeliratot kap. Friss, egyértelmű tölcsérbecslés, ikonminta-egyezés vagy kézzel megadott ellenőrző pozíció nélkül a távolság **—**. A kézzel megadott pozíciót a következő képkérés törli. A távolság becsült légvonalbeli érték; terepet, utat, bejáratot vagy menetidőt nem számol.

Felismert fehér körnél a belső pontok mentaszínű külső gyűrűt kapnak és előre kerülnek, azon belül távolság szerint rendezve, ha van pozíció. A kívüli pont sötét borostyánsárga rombusz; ismeretlen körnél minden pont semleges borostyánsárga kör. Háromnál kevesebb belső pont esetén az első három célpont között kívüliek is lehetnek; ellenőrizd a célpontlista körállapotát.

Katalógusos módban körfelismerés egyelőre csak akkor fut, ha a **teljes, közel tengelypárhuzamos és egyenletes méretarányú térkép belefér a képbe**. Zoom/eltolás miatti levágás, forgatás vagy torzítás esetén a kör **ismeretlen**, akkor is, ha egy részlete látszik. Így a látható kivágás koordinátáit nem keverjük össze a teljes térképével; a pontvetítés ettől még működhet.

Hiányzó, halvány, takart vagy többértelmű körnél nincs körprioritás. Pozíció esetén ilyenkor csak távolság alapján rendez. A besorolás a kör szélén hozzávetőleges; hasonló fehér gyűrű megtévesztheti. Nincs jövőbeli kör vagy útvonal számítása, és a program nem tudja, melyik szoba nyitott, kifosztott vagy elérhető. Mozgás és körváltozás után új képet kell kérni.

## Mit ellenőriztünk eddig?

A v0.4.1 privát pillanatfelvétele **24 képet**, valamint **Erangel-, Camp Jackal- és Taego-mintát** tartalmaz. A térképillesztés **17 látható térképből 15-öt helyesen azonosított**, és **mind a 7 negatív jelenetet elutasította**. A két szélsőséges nagyítás, `0013` és `0014`, elutasítást kapott. Az összesítés **3/3 betanító referenciaképet is tartalmaz**; ezeket kihagyva **12/14 külön tesztképen** sikerült az azonosítás: Erangel 6/8, Camp Jackal 4/4, Taego 2/2. Camp Jackalhoz nincs titkosszoba-adatsor, ezért helyes felismeréskor sem jelenít meg ilyen célpontokat.

A kézzel megjelölt, betanításhoz nem használt nézeteken **72/72 geometriai ellenőrzés 8 képpixelen belül volt**, **5,28 px maximális hibával**. Ezek rácspont- és POI-vetítési mérések; nem igazolják a valódi bejáratokat vagy a közösségi koordinátákat. Az elutasított képek nem kapnak sikeres pozícióbecslést. Az elsődleges méréshez a megjelölt térképkeretet adtuk meg; a külön teljesképes és GUI-próbák nem igazolják a keret vagy a takaró felületi elemek általános automatikus felismerését.

A 0.4.1 javítása előtt a Taego-minta hozzáadása olyan pályák közötti egyezéseket tárt fel, amelyeket csak közös szélső rácsfeliratok és felületi ikonok támasztottak alá; emiatt érvényes nézetek többértelmű elutasítást kaptak. Az új belső, eloszló egyezési követelmény ezt elutasítja, miközben több valóban megfelelő minta továbbra is bizonytalan marad. A célzott szintetikus esetek a javítás előtt hibáztak, utána megfeleltek; a fenti számok a javítás utáni futásból származnak.

Ez **három ismert mintából álló kis, zárt adatsor**, nem általános pályafelismerési pontosság. Több kép összefügg; a Taego betanítóképe és külön tesztnézetei **ugyanabból a replay-meccsből** származnak. További független meccsek, pályák, nagyítások/eltolások és 1–4 játékosos helyzetek szükségesek. **A térképillesztő nem becsül sajátjátékos-azonosságot vagy szövetségesikonszámot, és ezek továbbra is ellenőrizetlenek**; jelöletlen saját azonosságokat nem pontozunk. Egy korábbi élő sárgaikon-próba 0,96 sziluett-egyezést adott; ez nem a játékosazonosság valószínűsége. Valódi játékképeket, térképmintákat vagy személyes profilt nem mellékelünk.

A szintetikus egység- és GUI-tesztek ellenőrzik többek közt a transzformációt, közös szélső feliratokat/ikonokat, kis ismétlődő belső mintát, ismeretlen/többértelmű egyezést, képen kívüli pontok elrejtését, opcionális ikont, megfelelő pontadat kiválasztását, nyelvváltást, régi eredmények törlését és a fókusz megőrzését. Ezek nem igazolják általánosan a valós játékbeli pontosságot.

## Helyi adatok, indítás és licenc

A normál képkérések és eredmények memóriában maradnak, nincs képfeltöltés, telemetria, fiók vagy API-kulcs. Az adatfrissítő csak a GitHub nyilvános pontkatalógusát kéri le; képet, OCR-szöveget, profilt vagy helyi térképmintát nem küld. A kiválasztott monitor más látható tartalma is belekerülhet a képbe. Importkor az eredeti fájlt nem módosítja.

Az explicit ikonbeállítás mentett kivétele: `%LOCALAPPDATA%\LootLizard\profiles\<hashed-map-id>\` alatt a kiválasztott `reference.png`, `mask.png` és `profile.json`. A mappanév hash-elése nem anonimizálja a képet. Az új profil az adott pálya korábbi fájljait felülírja. A teljes beállítási képernyőképet ez a lépés nem menti. Katalógusimportkor a meglévő képeket olvassa, és csak a katalógus útját menti a nyelvi/kijelzőbeállítások mellé: `%LOCALAPPDATA%\LootLizard\settings.json`. A katalógus kikapcsolása nem törli a képeidet.

A `--launch-pubg` kapcsolós parancsikon a companion mellett Steamen keresztül a PUBG indítását is kéri. Nincs telepített Windows-autostart vagy háttérszolgáltatás; a külön indított játék nem indítja el a bezárt companiont.

Ha új LootLizard-beállítás még nincs, a korábbi `%LOCALAPPDATA%\BasementCompanion\settings.json` kompatibilis beállításait beolvashatja. Új profil hiányában a régi profilokat az eredeti helyükön olvassa; nem mozgatja, másolja vagy törli őket. A későbbi mentések a LootLizard mappájába kerülnek.

A 15 Erangel- és 12 Taego-pont pontos forrása, módosításai és teljes MIT licence: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Pontosságuk, teljességük és aktuális érvényességük ellenőrizetlen; a Taego-lista hiányos. A normalizált koordináták mindig a teljes térképhez tartoznak. Az 8192 forrásképpont nem 8192 méter; a mellékelt 8000 méteres méretarány becslés.

A programkód [MIT licence](LICENSE) nem ad jogot a PUBG képeihez vagy védjegyeihez. **Játékképeket, privát képes tesztadatot, helyi katalógust vagy személyes profilt nem terjesztünk a csomaggal.** A képernyőkép-alapú működés önmagában nem bizonyít hivatalos engedélyt vagy anti-cheat kompatibilitást. A program nem olvas játékfolyamat-memóriát vagy játékfájlokat, nem injektál és nem automatizál játékmenetet. A teljes leírás, pont-JSON formátum, fordítás és csomagolás az [angol README-ben](README.md) található.
