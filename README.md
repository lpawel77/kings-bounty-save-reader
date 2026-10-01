# King's Bounty – czytnik zapisu

Okienkowa przeglądarka zapisów **King's Bounty: Armored Princess** (`.sav`). Pokazuje, co gra wylosowała
w każdym budynku, zamku, skrzyni i armii na wszystkich mapach (także tych, na których jeszcze nie byłeś),
oraz czy dany przedmiot w ogóle pojawi się w tej rozgrywce.

## Uruchomienie

Dwuklik na `KB czytnik zapisu.bat` (albo `python kb_app.py [plik.sav]`). Potrzebny Python 3 – okno jest
w tkinterze, który jest w standardowej instalacji. Obrazki wymagają `Pillow` (`pip install pillow`; bez niej
aplikacja działa, tylko bez obrazków), eksport do `.xlsx` – `openpyxl` (bez niego można zapisać `.csv`).

### Wersja .exe

`build_exe.bat` buduje `dist\KB czytnik zapisu.exe` (PyInstaller, jeden plik ok. 13 MB, bez okna konsoli) –
działa na komputerze bez Pythona. Plików gry exe nie zawiera: nazwy, obrazki i mapy czyta z zainstalowanej gry
(wykrywanej w Steam albo wskazanej przyciskiem **Folder gry…**). Przed przebudową zamknij uruchomiony exe.

Przycisk **Otwórz zapis…** startuje w folderze zapisów gry (`Dokumenty\My Games\Kings Bounty Princess\$save`).
Ostatni plik i folder gry są zapamiętywane w `%APPDATA%\kb_save_reader.json`.

## Zakładki

- **Mapy i budynki** – drzewo: mapa → zamki, budynki/sklepy, postacie, skrzynie, ołtarze, armie. Po prawej
  **minimapa lokacji** z zaznaczonymi miejscami (kolor wg rodzaju) i pod nią zawartość wybranego miejsca:
  przedmioty i zwoje na sprzedaż, jednostki do werbunku, obrońcy, łupy. Kliknięcie punktu na mapie wybiera
  miejsce, najechanie pokazuje nazwę i zawartość, kółko myszy przybliża, przeciąganie przesuwa, dwuklik
  wraca do całej mapy. Listą „Mapa:” można przełączyć lokację.
  Filtry: szukaj (po nazwie miejsca lub zawartości), mapy odwiedzone/nieodwiedzone, rodzaje zawartości.
  Osobna gałąź *Zadania i dialogi* – nagrody za zadania i rozmowy, wylosowane z góry.
- **Przedmioty** – wszystkie przedmioty gry z typem (broń, pancerz, hełm, regalia, artefakt...), poziomem,
  rasą, ceną, limitem i licznikiem „Wylosowano”, oraz odpowiedzią **„Czy pojawi się w grze?”**:
  *Masz go*, *Do zdobycia (N miejsc)*, *Tylko przez ulepszenie*, *Był, ale już go nie ma*,
  *Tylko z zadań / wydarzeń*, *Nie pojawi się*. Pod listą karta przedmiotu (ikona, premie, opis z gry,
  ulepszenia) i lista miejsc.
  Kolumna **Premie** i filtr **Premia** (np. *Intelekt*, *Atak*, *Mana (maks.)*, *Morale wojsk*, *Odporność wojsk:
  ogień*, *dowolna premia dla bohatera / dla wojsk*) – przy filtrze najmocniejsze przedmioty są na górze.
  Premie są z sekcji `mods` (bohater) i `fight` (wojska w bitwie, gwiazdka = tylko niektóre jednostki) definicji
  przedmiotu. „Szukaj też w opisie” przeszukuje dodatkowo opisy z gry (po angielsku, np. *intellect*).
- **Czary** – czary z poziomem i szkołą, czy są w księdze, ile masz zwojów i gdzie są w świecie. Karta czaru:
  obrazek z księgi i zwoju, opis, efekty i koszt many/kryształów na poziomach 1–3, surowe parametry z pliku gry
  (liczby w opisach gra wylicza w trakcie, m.in. z intelektu bohatera, więc w opisie są „…”).
- **Jednostki** – gdzie można werbować daną jednostkę i ile sztuk, kto dołączy, w ilu armiach wroga występuje.
  Karta jednostki: portret, rasa, poziom, przywództwo, koszt, atak, obrona, zdrowie, szybkość, inicjatywa,
  trafienie krytyczne, odporności, cechy i ataki specjalne z obrażeniami.
- **Bohater** – statystyki, armia, umiejętności, czary, ekwipunek (to samo co raport `kb_save.py`).

Przycisk **Pokaż na mapie** w kartach przedmiotu, czaru i jednostki wyróżnia na żółto wszystkie miejsca, gdzie
można go zdobyć (lub gdzie stoją armie z daną jednostką), i otwiera mapę z największą ich liczbą; mapy z wyróżnieniami
są na początku listy „Mapa:” z liczbą ★. Nagrody za zadania i ekwipunek bohatera nie mają pozycji na mapie.

Listy i zawartość miejsc mają ikony z gry. Podwójne kliknięcie na miejsce w dolnej liście przenosi do niego w zakładce *Mapy i budynki*, a podwójne
kliknięcie na przedmiot/czar/jednostkę w zawartości miejsca – do jego karty.

## Skąd są dane

- Zapis (`.sav`) to ZIP; część `savedata` to drzewo opisane w `kb_save.py`.
- Gra losuje zawartość wszystkich wysp na początku rozgrywki. Dla miejsc jeszcze niepostawionych na mapie
  (nieodwiedzone wyspy, nagrody za zadania) wynik leży w generatorach `server/embs/els` (pole `pregen`).
  Odwiedzone mapy są w `session/lus/lubodies` i pokazują **stan bieżący** – to, co zabrałeś, już tam nie widać.
- `server/embs/gd/box` to licznik gry: ile egzemplarzy przedmiotu wylosowano. Przedmiot z zerem, bez miejsca
  w świecie i bez przedmiotu, z którego można go ulepszyć, już się nie pojawi – chyba że da go zadanie lub wydarzenie
  (takie przedmioty mają osobny status).
- Nazwy, typy, poziomy, ceny i opisy są z plików gry (`sessions\<sesja>\ses.kfs` i `loc_ses.kfs`, w języku
  ustawionym w `data\app.ini`). Folder gry jest wykrywany w bibliotekach Steam; można go wskazać przyciskiem
  **Folder gry…**. Bez niego aplikacja działa, ale pokazuje identyfikatory.
- Obrazki: ikony przedmiotów i czarów są wycinane z atlasów interfejsu (`data\data.kfs`: `tex1.dds`–`tex6.dds`,
  położenia w `itextures.dat`), portrety jednostek to pliki PNG z `data\interface_textures.kfs`, a statystyki
  jednostek – sekcja `arena_params` plików `<jednostka>.atom` z `data\data.kfs`.
- Mapy: minimapy to `radar_<mapa>.png` z `data\interface_textures.kfs`. Pozycje obiektów są w zapisie
  (x, y, z – płaszczyzną mapy jest x/z). Minimapa obejmuje kwadrat 256 × 256 jednostek z mapą pośrodku;
  rozmiar mapy to liczba kafli z `<mapa>.land.loc` × 16 (zależność ustalona porównaniem z zamkami na minimapach).
  Armie wędrujące mogą być już w innym miejscu niż ich pozycja startowa.

Format zapisu ustalono na podstawie analizy plików, a nie dokumentacji – znaczenie części pól jest domysłem
(np. druga liczba przy jednostkach zamku).

## Pliki

| Plik | Zawartość |
|---|---|
| `kb_app.py` | okno aplikacji |
| `kb_world.py` | zawartość świata z zapisu: miejsca, ich pozycje i zawartość, status przedmiotów |
| `kb_mapview.py` | podgląd minimapy z punktami (przybliżanie, przesuwanie, wybór miejsca) |
| `kb_gamedata.py` | odczyt definicji i tekstów z plików gry |
| `build_exe.bat`, `kb_icon.ico` | budowanie pliku .exe i jego ikona |
| `kb_save.py` | parser zapisu i raport w konsoli (`python kb_save.py plik.sav --lista lista.xlsx`) |
