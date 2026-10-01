"""Dane z instalacji gry King's Bounty: Armored Princess - nazwy i parametry.

Gra trzyma definicje w archiwach ZIP z rozszerzeniem .kfs:
    sessions/<sesja>/ses.kfs      - items.txt, spells.txt i pliki dołączane (==plik.txt)
    sessions/<sesja>/loc_ses.kfs  - teksty w wybranym języku (<jęz>_items.lng, ...)
    data/app.ini                  - język i domyślna sesja
Bez folderu gry aplikacja działa dalej, tylko pokazuje wewnętrzne identyfikatory.
"""

import io
import os
import re
import zipfile
from pathlib import Path

GAME_DIR_NAMES = ("Kings Bounty Armored Princess", "King's Bounty Armored Princess",
                  "Kings Bounty Crossworlds", "King's Bounty Crossworlds")

SLOTY = {
    "weapon": "Broń", "armor": "Pancerz", "helmet": "Hełm", "boots": "Buty",
    "belt": "Pas", "gloves": "Rękawice", "shield": "Tarcza", "artefact": "Artefakt",
    "regalia": "Regalia", "dress": "Suknia", "map": "Mapa", "medal": "Medal",
    "hidden": "Ukryty", "setbonus": "Premia za komplet",
}
CECHY = {"rare": "rzadki", "quest": "zadaniowy", "usable": "do użycia", "moral": "ma morale",
         "container": "pojemnik", "multiuse": "wielorazowy", "dialog": "z dialogiem"}
RASY = {"human": "ludzie", "elf": "elfy", "orc": "orki", "dwarf": "krasnoludy",
        "undead": "nieumarli", "demon": "demony", "neutral": "neutralny", "lizard": "jaszczury"}
SZKOLY = {"1": "Porządek", "2": "Zniekształcenie", "3": "Chaos", "4": "Przygoda"}


def _decode(raw: bytes) -> str:
    if raw[:2] == b"\xff\xfe":
        return raw[2:].decode("utf-16le", "replace")
    return raw.decode("cp1251", "replace")


def clean_text(text: str) -> str:
    """Tekst z pliku .lng bez znaczników stylu (^...^) i formatowania (<...>)."""
    if not text:
        return ""
    text = re.sub(r"\^[^^]*\^", "", text)
    text = re.sub(r"<br>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("[s]", "• ")
    return re.sub(r"[ \t]+", " ", text).strip()


class Block:
    """Blok pliku definicji: pola 'klucz=wartość' i bloki potomne."""

    __slots__ = ("name", "fields", "children")

    def __init__(self, name):
        self.name, self.fields, self.children = name, {}, []

    def get(self, key, default=""):
        return self.fields.get(key, default)

    def child(self, name):
        return next((c for c in self.children if c.name == name), None)


def parse_blocks(text: str) -> list:
    """Bloki najwyższego poziomu z pliku w formacie 'nazwa { klucz=wartość ... }'."""
    root = Block("")
    stack = [root]
    for line in text.splitlines():
        line = line.split("//", 1)[0].strip()
        if not line:
            continue
        if line.endswith("{}"):
            stack[-1].children.append(Block(line[:-2].strip()))
        elif line.endswith("{"):
            b = Block(line[:-1].strip())
            stack[-1].children.append(b)
            stack.append(b)
        elif line == "}" or line.startswith("}"):
            if len(stack) > 1:
                stack.pop()
        elif "=" in line:
            k, _, v = line.partition("=")
            stack[-1].fields.setdefault(k.strip(), v.strip())
    return root.children


def find_game_dirs() -> list:
    """Możliwe foldery gry: biblioteki Steam (z rejestru i libraryfolders.vdf) i typowe ścieżki."""
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            roots.append(Path(winreg.QueryValueEx(k, name)[0]))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    for drive in "CDEFG":
        roots += [Path(f"{drive}:/Steam"), Path(f"{drive}:/Program Files (x86)/Steam"),
                  Path(f"{drive}:/SteamLibrary")]
    libs = []
    for r in roots:
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            try:
                libs += [Path(p.replace("\\\\", "\\")) for p in
                         re.findall(r'"path"\s+"([^"]+)"', vdf.read_text("utf-8", "replace"))]
            except OSError:
                pass
        libs.append(r)
    found, seen = [], set()
    for lib in libs:
        for name in GAME_DIR_NAMES:
            d = lib / "steamapps" / "common" / name
            key = str(d).lower()
            if key not in seen and (d / "sessions").is_dir():
                seen.add(key)
                found.append(d)
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), "C:/GOG Games"):
        for name in GAME_DIR_NAMES:
            d = Path(base or "", name)
            if base and (d / "sessions").is_dir() and str(d).lower() not in seen:
                seen.add(str(d).lower())
                found.append(d)
    return found


def is_game_dir(path) -> bool:
    return bool(path) and (Path(path) / "sessions").is_dir()


class GameData:
    """Katalog przedmiotów, czarów i nazw z plików gry."""

    def __init__(self, game_dir=None, session="addon"):
        self.game_dir = Path(game_dir) if game_dir else None
        self.items, self.spells = {}, {}
        self.texts = {}
        self.language = "eng"
        self.error = ""
        self._zips, self._lower, self._images, self._textures = {}, {}, {}, {}
        self._atlas_idx = None
        self._units = {}
        if self.game_dir:
            try:
                self._load(session.strip("/") or "addon")
            except (OSError, zipfile.BadZipFile, KeyError) as e:
                self.error = f"Nie udało się odczytać plików gry: {e}"

    @property
    def ok(self):
        return bool(self.items)

    # --- wczytanie ---

    def _load(self, session):
        app_ini = self.game_dir / "data" / "app.ini"
        if app_ini.is_file():
            ini = app_ini.read_text("cp1251", "replace")
            m = re.search(r'~language\s+"(\w+)"', ini)
            self.language = m.group(1) if m else "eng"
            if not (self.game_dir / "sessions" / session).is_dir():
                m = re.search(r'~session\s+"(\w+)"', ini)
                session = m.group(1) if m else session
        sdir = self.game_dir / "sessions" / session
        with zipfile.ZipFile(sdir / "ses.kfs") as z:
            names = set(z.namelist())

            def read(fname):
                return _decode(z.read(fname)) if fname in names else ""

            files = []
            for top in ("items.txt", "spells.txt"):
                files += [f for f in self._with_includes(read, top) if f not in files]
            for fname in files:
                for b in parse_blocks(read(fname)):
                    cat = b.get("category")
                    if cat == "o":
                        self.items.setdefault(b.name, self._item(b, fname))
                    elif cat == "s":
                        lv = b.child("levels")
                        par = b.child("params")
                        self.spells.setdefault(b.name, {
                            "id": b.name, "school": b.get("school"), "level": b.get("profit"),
                            "price": _int(b.get("price")), "file": fname,
                            "image": b.get("image"), "scroll_image": b.get("button_image"),
                            "levels": dict(lv.fields) if lv else {},
                            "params": dict(par.fields) if par else {}})
        with zipfile.ZipFile(sdir / "loc_ses.kfs") as z:
            prefix = f"{self.language}_"
            for fname in z.namelist():
                if fname.startswith(prefix) and fname.endswith(".lng") and "_chat_" not in fname:
                    for line in _decode(z.read(fname)).splitlines():
                        k, sep, v = line.partition("=")
                        if sep and not k.startswith("//"):
                            self.texts.setdefault(k.strip(), v.strip())

    @staticmethod
    def _with_includes(read, fname):
        out = [fname]
        for line in read(fname).splitlines():
            m = re.match(r"==\s*([\w.]+)", line)
            if m:
                out.append(m.group(1))
        return out

    @staticmethod
    def _item(b, fname):
        bits = [p.strip() for p in b.get("propbits").split(",") if p.strip()]
        slot = next((p for p in bits if p in SLOTY), "")
        use = b.child("use")
        return {
            "id": b.name, "label": b.get("label"), "hint": b.get("hint"),
            "info": b.get("information_label"), "price": _int(b.get("price")),
            "maxcount": _int(b.get("maxcount")), "level": b.get("level"),
            "race": b.get("race"), "slot": slot, "bits": bits, "set": b.get("setref"),
            "upgrade": use.get("upgrade") if use else "", "file": fname,
            "image": b.get("image"),
        }

    # --- nazwy ---

    def text(self, key, depth=0):
        raw = self.texts.get(key, "")
        m = re.fullmatch(r"\s*(?:\^[^^]*\^)?<label=([^>]+)>\s*", raw)
        if m and depth < 3:
            return self.text(m.group(1), depth + 1)
        return clean_text(raw)

    def item_name(self, item_id):
        it = self.items.get(item_id)
        name = self.text(it["label"]) if it and it["label"] else ""
        return name or self.text(f"itm_{item_id}_name") or item_id

    def item_description(self, item_id):
        it = self.items.get(item_id) or {}
        parts = [self.text(it.get("hint") or f"itm_{item_id}_hint"),
                 self.text(it.get("info") or f"itm_{item_id}_info")]
        return "\n\n".join(p for p in parts if p and p != "?")

    def spell_name(self, spell_id):
        return self.text(f"{spell_id}_name") or spell_id.replace("spell_", "")

    def unit_name(self, unit_id):
        return self.text(f"cpn_{unit_id}") or unit_id

    def map_name(self, map_id):
        return self.text(f"{map_id}_full") or self.text(map_id) or map_id

    def quest_name(self, quest_id):
        return self.text(f"quest_system_{quest_id}_name") or f"zadanie {quest_id}"

    def hint(self, key):
        """Nazwa obiektu z klucza podpowiedzi, np. itext_verona_22_hint."""
        return self.text(key) if key else ""

    def resource_name(self, res_id):
        return ZASOBY_PL.get(res_id, res_id)

    def spell_description(self, spell_id):
        """Opis czaru: krótki, pełny i efekty na poziomach 1-3 z kosztem many."""
        sp = self.spells.get(spell_id) or {}
        out = {"small": _placeholders(self.text(f"{spell_id}_small")),
               "desc": _placeholders(self.text(f"{spell_id}_desc")), "levels": []}
        for lvl in ("1", "2", "3"):
            effect = _placeholders(self.text(f"{spell_id}_text_{lvl}"))
            cost = sp.get("levels", {}).get(lvl, "")
            mana, _, crystals = cost.partition(",")
            if effect or cost:
                out["levels"].append((lvl, mana.strip(), crystals.strip(), effect))
        return out

    # --- jednostki ---

    def unit_info(self, unit_id):
        """Statystyki jednostki z pliku <id>.atom (sekcja arena_params) albo None."""
        if unit_id in self._units:
            return self._units[unit_id]
        info = None
        z = self._zip("data/data.kfs")
        name = self._names(z).get(f"{unit_id}.atom".lower()) if z else None
        if name:
            blocks = parse_blocks(_decode(z.read(name)))
            ap = next((b for b in blocks if b.name == "arena_params"), None)
            if ap:
                f = ap.fields
                feats = []
                for pair in f.get("features_hints", "").split(","):
                    head, _, hint = pair.partition("/")
                    title = self.text(head.strip())
                    if title:
                        feats.append((title, _placeholders(self.text(hint.strip()))))
                attacks = []
                for a in [x.strip() for x in f.get("attacks", "").split(",") if x.strip()]:
                    blk = ap.child(a)
                    if not blk or blk.get("disabled") == "1":
                        continue
                    dmg = blk.child("damage")
                    head = blk.get("hinthead")
                    title = self.text(head.replace("_head", "_name")) if head.endswith("_head") else ""
                    title = title or self.text(head)
                    hint = _placeholders(self.text(blk.get("hint")))
                    if not title or title.startswith("["):
                        title = ATAKI.get(a, "")
                    if not title and not hint:
                        continue                     # atak pomocniczy bez opisu w grze
                    attacks.append({
                        "name": title or a, "hint": hint,
                        "damage": ", ".join(f"{OBRAZENIA.get(k, k)} {v.replace(',', '-')}"
                                            for k, v in (dmg.fields.items() if dmg else []))})
                res = ap.child("resistances")
                info = {k: f.get(k, "") for k in ("race", "level", "leadership", "cost", "attack", "defense",
                                                  "hitpoint", "speed", "initiative", "krit")}
                info.update(features=feats, attacks=attacks,
                            features_label=self.text(f.get("features_label", "")),
                            resistances={OBRAZENIA.get(k, k): v for k, v in (res.fields.items() if res else [])
                                         if v not in ("", "0")})
        self._units[unit_id] = info
        return info

    # --- obrazki (wymagają Pillow) ---

    def _zip(self, rel):
        if rel not in self._zips:
            p = self.game_dir / rel if self.game_dir else None
            try:
                self._zips[rel] = zipfile.ZipFile(p) if p and p.is_file() else None
            except (OSError, zipfile.BadZipFile):
                self._zips[rel] = None
        return self._zips[rel]

    def _names(self, z):
        key = id(z)
        if key not in self._lower:
            self._lower[key] = {n.lower(): n for n in z.namelist()}
        return self._lower[key]

    def _atlas(self):
        """Indeks atlasów interfejsu: nazwa pliku -> (tekstura, x, y, szer., wys.)."""
        if self._atlas_idx is None:
            self._atlas_idx = {}
            z = self._zip("data/data.kfs")
            name = self._names(z).get("itextures.dat") if z else None
            if name:
                text = z.read(name).decode("cp1251", "replace")
                for m in re.finditer(r"(\w+) \{(.*?)\n\}", text, re.S):
                    for b in re.finditer(r"filename=(\S+)\s+in_tex_pos=(\d+),(\d+)\s+in_tex_size=(\d+),(\d+)",
                                         m.group(2)):
                        self._atlas_idx[b.group(1).lower()] = (m.group(1).lower(), *map(int, b.groups()[1:]))
        return self._atlas_idx

    def image(self, filename):
        """Obrazek interfejsu gry jako PIL.Image (RGBA) albo None."""
        if not filename:
            return None
        key = filename.lower()
        if key in self._images:
            return self._images[key]
        img = None
        try:
            from PIL import Image
        except ImportError:
            Image = None
        if Image:
            try:
                pos = self._atlas().get(key)
                if pos:
                    tex, x, y, w, h = pos
                    if tex not in self._textures:
                        z = self._zip("data/data.kfs")
                        name = self._names(z).get(f"{tex}.dds")
                        self._textures[tex] = Image.open(io.BytesIO(z.read(name))).convert("RGBA") if name else None
                    if self._textures[tex]:
                        img = self._textures[tex].crop((x, y, x + w, y + h))
                else:
                    z = self._zip("data/interface_textures.kfs")
                    name = self._names(z).get(key) if z else None
                    if name:
                        img = Image.open(io.BytesIO(z.read(name))).convert("RGBA")
            except (OSError, ValueError, KeyError):
                img = None
        self._images[key] = img
        return img

    def item_image(self, item_id):
        return self.image((self.items.get(item_id) or {}).get("image"))

    def spell_image(self, spell_id, scroll=False):
        sp = self.spells.get(spell_id) or {}
        return self.image(sp.get("scroll_image" if scroll else "image"))

    def unit_image(self, unit_id):
        return self.image(f"{unit_id}.png")


OBRAZENIA = {"physical": "fizyczne", "poison": "trucizna", "magic": "magia", "fire": "ogień",
             "astral": "astralne", "cold": "zimno"}
ATAKI = {"moveattack": "Atak wręcz", "throw1": "Strzał", "throw2": "Strzał specjalny",
         "throw3": "Strzał specjalny", "krugom": "Atak dookoła", "dragonslayer": "Atak na smoki"}


def _placeholders(text):
    """Znaczniki liczb wstawianych przez grę ([CS04_DamageE], [fdamage]) -> '…'."""
    return re.sub(r"\[[A-Za-z0-9_]+\]", "…", text or "").strip()


ZASOBY_PL = {
    "money": "Złoto", "crystals": "Kryształy", "leadership": "Przywództwo",
    "experience": "Doświadczenie", "rune_might": "Runa siły", "rune_mind": "Runa umysłu",
    "rune_magic": "Runa magii", "mana": "Mana", "rage": "Furia", "attack": "Atak",
    "defense": "Obrona", "intellect": "Intelekt",
}


def _int(v):
    try:
        return int(str(v).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None
