"""Zawartość świata z zapisu King's Bounty: Armored Princess.

Gra losuje zawartość wszystkich wysp na początku rozgrywki. Wynik losowania
leży w zapisie w dwóch miejscach:
    server/embs/els      - generatory obiektów ('embriony'); pole 'pregen' to już
                           wylosowana zawartość dla miejsc, których gra jeszcze nie
                           postawiła na mapie (nieodwiedzone wyspy, nagrody za zadania)
    session/lus/lubodies - obiekty postawione na mapach odwiedzonych wysp, ze
                           stanem bieżącym (co zostało w sklepie, skrzyni, armii)
server/embs/gd/box liczy, ile egzemplarzy każdego przedmiotu gra wylosowała.
"""

import struct
from collections import defaultdict
from dataclasses import dataclass, field

from kb_save import Node, find_player_hero, hero_report, parse_lvars, strg

# rodzaj wpisu -> etykieta
ITEM, SPELL, UNIT, RES, ARMY = "Przedmiot", "Zwój / czar", "Jednostki", "Zasób", "Armia"

TYP_OBIEKTU = {
    "building_trader": "Budynek / sklep", "building_castle": "Zamek",
    "template_item_altar": "Ołtarz / skrytka", "template_item_mb": "Skrzynia",
    "template_item_ft": "Znalezisko", "template_mana_fountain": "Źródło many",
    "template_rage_fountain": "Źródło furii", "template_with_altar": "Ołtarz",
    "army_a_template": "Armia", "army_n_template": "Armia", "NPC_template": "Postać",
    "map": "Mapa", "hero": "Bohater", "boat": "Statek",
    "castle": "Budynek / zamek", "npc": "Postać", "army": "Armia", "box": "Skrzynia",
    "!container": "Budynek / zamek", "!wrapper": "Znalezisko",
}
ROLA = {"sklep": "na sprzedaż", "werbunek": "do werbunku", "straz": "obrońcy / wrogowie",
        "skrzynia": "do zebrania", "nagroda": "nagroda", "garnizon": "garnizon zamku",
        "dolaczaja": "dołączą do armii", "bohater": "u bohatera"}
STATUS_ZADANIA = {0: "w trakcie", 2: "ukończone"}

ODWIEDZONA = "odwiedzona"
WYLOSOWANA = "nieodwiedzona (zawartość już wylosowana)"


@dataclass
class Entry:
    kind: str          # ITEM / SPELL / UNIT / RES / ARMY
    id: str            # identyfikator gry
    count: object = 1
    role: str = ""     # klucz ROLA
    note: str = ""


@dataclass
class Place:
    key: str
    map_id: str
    type: str
    name: str
    source: str        # ODWIEDZONA / WYLOSOWANA / 'zadanie' / 'bohater'
    atom: str = ""
    entries: list = field(default_factory=list)
    pos: tuple = None  # (x, z) w jednostkach świata; płaszczyzna mapy to x/z, y to wysokość

    def add(self, *a, **kw):
        self.entries.append(Entry(*a, **kw))


class World:
    def __init__(self, info, data, game):
        self.info, self.data, self.g = info, data, game
        self.hero_id, _ = find_player_hero(data)
        self.hero = hero_report(info, data)
        self.visited = [m for m, n in data.path("session", "sesd", "maps") or []
                        if isinstance(n, Node)]
        self.box = {k: v for k, v in data.path("server", "embs", "gd", "box") or []
                    if isinstance(v, int)}
        self.quest_status = {str(q.get("uid")): q.get("sta")
                             for _, q in data.path("server", "quest") or [] if isinstance(q, Node)}
        self.places = []
        self._atoms = {}
        for _, el in data.path("server", "embs", "els") or []:
            m = (el.get("n") or "").split(".")[0]
            for k, ii in el:
                if k.startswith("ii") and isinstance(ii, Node):
                    self._atoms[(m, ii.get("u"))] = el.get("aa") or ""
        self._world_bodies()
        self._pregen()
        self._hero_place()
        self.by_id = self._index()
        self.upgraded_from = defaultdict(list)
        for iid, it in game.items.items():
            if it.get("upgrade"):
                self.upgraded_from[it["upgrade"]].append(iid)

    # --- obiekty postawione na odwiedzonych mapach --------------------------

    def _world_bodies(self):
        for key, body in self.data.path("session", "lus", "lubodies") or []:
            if not isinstance(body, Node) or not body.get("lt") or key == self.hero_id:
                continue
            v = body.get("vars") or Node(2, [])
            typ = key.split("@")[0]
            hint = strg(v, "hint")
            label = strg(v, "name")
            name = ""
            if isinstance(label, str) and label.startswith("<label="):
                name = self.g.text(label[7:-1])
            if isinstance(hint, str):
                name = name or self.g.hint(hint)
            map_id = body.get("lt")
            src = ODWIEDZONA if map_id in self.visited else WYLOSOWANA
            p = Place(key, map_id, TYP_OBIEKTU.get(typ, typ), name, src,
                      atom=self._atoms.get((map_id, body.get("auid")), ""), pos=_xz(body.get("pos")))
            shop = typ in ("building_trader", "building_castle")

            for item_id, item in strg(v, ".items") or []:
                if not isinstance(item, Node):
                    continue
                if item.get("count") is not None:
                    p.add(RES if item_id in RESOURCES else ITEM, item_id, item.get("count"),
                          "sklep" if shop else "skrzynia")
                else:
                    _, _, cnt = (item.get("slruck") or "").partition(",")
                    lv = parse_lvars(item.get("lvars", ""))
                    lv.pop("rndid", None)
                    p.add(ITEM, item_id, int(cnt or 1), "sklep" if shop else "skrzynia",
                          ", ".join(f"{a}={b}" for a, b in lv.items()))
            if typ.startswith("template_") and not p.entries:
                obj, cnt = strg(v, "object") or strg(v, "ctaken"), strg(v, "count")
                if isinstance(obj, str) and obj and cnt not in (None, "", "0"):
                    p.add(RES if obj in RESOURCES else ITEM, obj, _num(cnt), "skrzynia")
            for unit, cnt in _pairs(strg(v, ".shopunits"), "/"):
                p.add(UNIT, unit, _num(cnt), "werbunek")
            for unit, a, b in _groups(strg(v, ".castleunits"), "/", 3):
                p.add(UNIT, unit, _num(a), "garnizon", f"druga liczba w zapisie: {b}")
            spells = strg(v, ".spells")
            if isinstance(spells, Node):
                for kind in ("s", "m"):
                    for sp, cnt in spells.get(kind) or []:
                        p.add(SPELL, sp, cnt, "sklep" if shop else "skrzynia",
                              "zwój" if kind == "s" else "czar")
            army = strg(v, ".army")
            for unit, cnt in _pairs(army.get("stack") if isinstance(army, Node) else "", "|"):
                if _num(cnt):
                    p.add(ARMY, unit, _num(cnt), "straz")
            if p.entries:
                self.places.append(p)

    # --- zawartość wylosowana z góry (generatory) ---------------------------

    def _pregen(self):
        for _, el in self.data.path("server", "embs", "els") or []:
            pg = el.get("pregen")
            if not isinstance(pg, Node):
                continue
            n = el.get("n") or ""
            e = el.get("e") or Node(2, [])
            if n.startswith("_"):
                qid = n.strip("_").split("_")[0]
                if qid.startswith("a") and qid[1:].isdigit():
                    name = self.g.text(f"actor_system_{qid[1:]}_name") or f"postać {qid[1:]}"
                    p = Place(f"actor:{qid}", "", "Nagroda od postaci", name, "zadanie")
                else:
                    st = self.quest_status.get(qid)
                    p = Place(f"quest:{qid}", "", "Nagroda za zadanie",
                              self.g.quest_name(qid), "zadanie",
                              atom=STATUS_ZADANIA.get(st, "nie rozpoczęte" if st is None else str(st)))
                existing = next((x for x in self.places if x.key == p.key), None)
                p = existing or p
                self._walk(pg, p, "nagroda")
                if not existing and p.entries:
                    self.places.append(p)
                continue
            map_id = n.split(".")[0]
            ii0 = el.get("ii0") or Node(2, [])
            hint = (ii0.path("vp", "hint") or Node(2, [])).get("strg")
            cls = e.get("class") or ""
            atom = el.get("aa") or ""
            lu = pg.get("lu") or ((pg.get("pg") or Node(2, [])).get("lu") if pg.get("sn") == "cnt" else "")
            typ = TYP_OBIEKTU.get(lu) or TYP_OBIEKTU.get(cls, cls)
            if cls in ("castle", "!container") and (atom.startswith("castle") or "castle" in (hint or "")):
                typ = "Zamek"
            name = self.g.hint(hint) if hint else ""
            src = ODWIEDZONA if map_id in self.visited else WYLOSOWANA
            p = Place(f"emb:{n}", map_id, typ, name, src, atom=atom, pos=_xz(ii0.get("p")))
            self._walk(pg, p, "sklep" if cls in ("castle", "npc", "!container") else "skrzynia")
            if p.entries:
                self.places.append(p)

    def _walk(self, pg, p, role):
        if not isinstance(pg, Node):
            return
        sn = pg.get("sn")
        if sn == "bi":
            p.add(ITEM, pg.get("ib"), pg.get("ko") or 1, role)
        elif sn == "bs":
            p.add(SPELL, pg.get("ib"), pg.get("ko") or 1, role, "zwój")
        elif sn == "bp":
            p.add(RES, pg.get("ib"), pg.get("va"), role)
        elif sn == "bu":
            unit, _, cnt = (pg.get("uni") or "").partition("/")
            if unit:
                p.add(UNIT, unit, _num(cnt), "dolaczaja")
        elif sn == "arm":
            for _, s in pg.get("stack") or []:
                if isinstance(s, Node) and s.get("a"):
                    p.add(ARMY, s.get("a"), s.get("c"), "straz")
        elif sn == "za":
            self._walk(pg.get("army"), p, "straz")
            for _, a in pg.get("asso") or []:
                if not isinstance(a, Node):
                    continue
                for _, it in a.get("itms") or []:
                    self._walk(it, p, "sklep" if role != "nagroda" else role)
                for unit, cnt in _pairs(a.get("units"), "/"):
                    p.add(UNIT, unit, _num(cnt), "werbunek")
        elif sn == "cnt":
            self._walk(pg.get("pg"), p, role)

    # --- bohater -------------------------------------------------------------

    def _hero_place(self):
        h = self.hero
        p = Place("hero", "", "Bohater", h["bohater"]["imie"] or "Bohater", "bohater")
        for e in h["zalozone"]:
            p.add(ITEM, e["przedmiot"], 1, "bohater", f"założony (slot {e['slot']})")
        for e in h["plecak"]:
            p.add(ITEM, e["przedmiot"], e["ilosc"], "bohater", "w plecaku")
        for e in h["towarzysz_i_ukryte"]:
            p.add(ITEM, e["przedmiot"], 1, "bohater", e.get("slot", ""))
        for sp, lvl in h["czary_w_ksiedze"].items():
            p.add(SPELL, sp, lvl, "bohater", f"w księdze, poziom {lvl}")
        for sp, cnt in h["zwoje"].items():
            p.add(SPELL, sp, cnt, "bohater", "zwój")
        for a in h["armia"]:
            p.add(ARMY, a["jednostka"], a["ilosc"], "bohater")
        self.places.append(p)

    # --- indeks i podsumowania -----------------------------------------------

    def _index(self):
        idx = defaultdict(list)
        for p in self.places:
            for e in p.entries:
                idx[(e.kind, e.id)].append((p, e))
        return idx

    def maps(self):
        """Mapy w kolejności: odwiedzone, potem pozostałe; z liczbą miejsc."""
        out = defaultdict(list)
        for p in self.places:
            if p.map_id:
                out[p.map_id].append(p)
        order = sorted(out, key=lambda m: (m not in self.visited, self.g.map_name(m).lower()))
        return [(m, out[m]) for m in order]

    def item_status(self, item_id, _depth=0):
        found = self.by_id.get((ITEM, item_id), [])
        mine = [x for x in found if x[0].source == "bohater"]
        other = [x for x in found if x[0].source != "bohater"]
        box = self.box.get(item_id, 0)
        it = self.g.items.get(item_id) or {}
        if mine:
            return "masz", "Masz go" + (f" (+{len(other)} w świecie)" if other else "")
        if other:
            return "jest", f"Do zdobycia ({len(other)} {_miejsc(len(other))})"
        if box:
            return "byl", "Był wylosowany, ale już go nie ma (sprzedany, zużyty lub stracony)"
        if _depth < 4:
            for src in self.upgraded_from.get(item_id, []):
                if self.item_status(src, _depth + 1)[0] in ("masz", "jest", "ulepszenie"):
                    return "ulepszenie", f"Tylko przez ulepszenie: {self.g.item_name(src)}"
        if {"quest", "wife"} & set(it.get("bits", [])) or it.get("slot") in ("medal", "hidden", "setbonus"):
            return "skrypt", "Brak w zapisie - może go dać tylko zadanie lub wydarzenie"
        if it.get("maxcount") == 0:
            return "skrypt", "Gra go nie losuje (limit 0) - może go dać tylko zadanie lub wydarzenie"
        return "brak", "Nie pojawi się w tej grze (nie został wylosowany)"


BUDYNKI = [
    ("building_witch", "Chata wiedźmy"), ("sawmill", "Tartak"), ("building_mushroom", "Grzybowa chata"),
    ("town_house", "Dom w mieście"), ("port_house", "Dom w porcie"), ("lighthouse", "Latarnia morska"),
    ("piratehouse", "Dom piratów"), ("building_robberhouse", "Kryjówka rabusiów"),
    ("building_knighttent", "Namiot rycerski"), ("vikingtent", "Namiot wikingów"),
    ("building_vikingship", "Statek wikingów"), ("building_viking", "Osada wikingów"),
    ("building_dragonfly_farm", "Farma ważek"), ("building_tomb", "Grobowiec"),
    ("building_barbarian", "Chata barbarzyńców"), ("building_dwarflab", "Laboratorium krasnoludów"),
    ("building_dwarffactory", "Fabryka krasnoludów"), ("dwarfhouse", "Dom krasnoludów"),
    ("building_petshop", "Sklep ze zwierzakami"), ("building_waterlily", "Lilia wodna"),
    ("building_flower", "Kwiat"), ("building_bones", "Kościana chata"), ("building_demon", "Budynek demonów"),
    ("building_orc", "Siedziba orków"), ("building_elf", "Dom elfów"), ("building_human", "Dom ludzi"),
    ("castle", "Zamek"), ("village", "Wioska"), ("building", "Budynek"),
]


def pretty_atom(atom):
    """Czytelna nazwa obiektu gry, np. 'building_witch02' -> 'Chata wiedźmy'."""
    a = (atom or "").lower()
    for prefix, name in BUDYNKI:
        if a.startswith(prefix):
            return name
    words = [w for w in a.replace("-", "_").split("_") if w and not w.isdigit()]
    return " ".join(words).strip().capitalize()


RESOURCES = {"money", "crystals", "leadership", "experience", "rune_might", "rune_mind",
             "rune_magic", "mana", "rage", "attack", "defense", "intellect"}


def _miejsc(n):
    return "miejsce" if n == 1 else ("miejsca" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "miejsc")


def _xz(raw):
    """Pozycja obiektu (4 x float32: x, y, z, w) -> (x, z) albo None."""
    if isinstance(raw, bytes) and len(raw) >= 12:
        x, _, z = struct.unpack_from("<3f", raw)
        return x, z
    return None


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def _groups(text, sep, step):
    parts = text.split(sep) if isinstance(text, str) and text else []
    for i in range(0, len(parts) - step + 1, step):
        if parts[i]:
            yield parts[i:i + step]


def _pairs(text, sep):
    return _groups(text, sep, 2)
