"""Podgląd minimapy lokacji z zaznaczonymi miejscami (tkinter Canvas + Pillow).

Kółko myszy przybliża (wokół kursora), przeciąganie przesuwa, kliknięcie w punkt
wybiera miejsce, najechanie pokazuje jego nazwę.
"""

import tkinter as tk

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

# rodzaj miejsca -> (kolor, etykieta w legendzie)
STYLE = {
    "Zamek": ("#e53935", "zamek"),
    "Budynek / zamek": ("#ff9800", "budynek"),
    "Budynek / sklep": ("#ff9800", "budynek"),
    "Postać": ("#d500f9", "postać"),
    "Skrzynia": ("#00e5ff", "skrzynia / znalezisko"),
    "Ołtarz / skrytka": ("#00e5ff", "skrzynia / znalezisko"),
    "Ołtarz": ("#00e5ff", "skrzynia / znalezisko"),
    "Znalezisko": ("#00e5ff", "skrzynia / znalezisko"),
    "Armia": ("#b0bec5", "armia"),
}
OTHER = ("#76ff03", "inne")
HIGHLIGHT = "#ffeb3b"
MIN_ZOOM, MAX_ZOOM = 1.0, 8.0


class MapView(tk.Canvas):
    def __init__(self, master, on_pick=None, label_fn=None, **kw):
        super().__init__(master, background="#0b1622", highlightthickness=0, **kw)
        self.on_pick, self.label_fn = on_pick, label_fn or (lambda p: p.key)
        self.src = None            # PIL.Image minimapy
        self.markers = []          # (place, u, v)
        self.highlight = set()     # klucze miejsc wyróżnionych
        self.selected = None
        self.message = ""
        self.zoom = 1.0
        self.ox = self.oy = 0.0     # pozycja lewego górnego rogu obrazka na płótnie
        self._photo = None
        self._drag = None
        self._fit_scale = 1.0
        self.bind("<Configure>", lambda e: self._refit(keep=True))
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion_drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda e: self.delete("tip"))
        self.bind("<Double-1>", lambda e: self.reset_view())

    # --- API ---

    def show(self, image, markers, highlight=(), selected=None, keep_view=False, message=""):
        new_image = image is not self.src
        self.src, self.markers = image, markers
        self.highlight, self.selected, self.message = set(highlight), selected, message
        if new_image or not keep_view:
            self.zoom = 1.0
            self._refit(keep=False)
        else:
            self.redraw()

    def reset_view(self):
        self.zoom = 1.0
        self._refit(keep=False)

    def center_on(self, key):
        """Przesuwa widok tak, by miejsce było widoczne (bez zmiany przybliżenia)."""
        for p, u, v in self.markers:
            if p.key == key and self.src:
                s = self._scale()
                x, y = self.ox + u * self.src.width * s, self.oy + v * self.src.height * s
                w, h = self.winfo_width(), self.winfo_height()
                if not (20 < x < w - 20 and 20 < y < h - 20):
                    self.ox += w / 2 - x
                    self.oy += h / 2 - y
                    self._clamp()
                break
        self.redraw()

    # --- geometria ---

    def _scale(self):
        return self._fit_scale * self.zoom

    def _refit(self, keep):
        w, h = max(self.winfo_width(), 10), max(self.winfo_height(), 10)
        if not self.src:
            self.redraw()
            return
        old = self._scale()
        self._fit_scale = min(w / self.src.width, h / self.src.height)
        if keep and old:
            # zachowaj środek widoku przy zmianie rozmiaru okna
            self.ox = w / 2 - (w / 2 - self.ox) * self._scale() / old
            self.oy = h / 2 - (h / 2 - self.oy) * self._scale() / old
            self._clamp()
        else:
            s = self._scale()
            self.ox = (w - self.src.width * s) / 2
            self.oy = (h - self.src.height * s) / 2
        self.redraw()

    def _clamp(self):
        if not self.src:
            return
        w, h = self.winfo_width(), self.winfo_height()
        s = self._scale()
        iw, ih = self.src.width * s, self.src.height * s
        self.ox = (w - iw) / 2 if iw <= w else min(0, max(w - iw, self.ox))
        self.oy = (h - ih) / 2 if ih <= h else min(0, max(h - ih, self.oy))

    def _to_canvas(self, u, v):
        s = self._scale()
        return self.ox + u * self.src.width * s, self.oy + v * self.src.height * s

    # --- rysowanie ---

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if not self.src:
            self.create_text(w / 2, h / 2, text=self.message or "Brak minimapy", fill="#9fb3c8",
                             font=("Segoe UI", 11), width=max(w - 40, 50))
            return
        s = self._scale()
        # wycinek obrazka widoczny na płótnie
        x0, y0 = max(0, -self.ox / s), max(0, -self.oy / s)
        x1, y1 = min(self.src.width, (w - self.ox) / s), min(self.src.height, (h - self.oy) / s)
        if x1 > x0 and y1 > y0:
            box = (int(x0), int(y0), int(x1) + 1, int(y1) + 1)
            size = (max(1, round((box[2] - box[0]) * s)), max(1, round((box[3] - box[1]) * s)))
            crop = self.src.crop(box).resize(size, Image.BILINEAR)
            self._photo = ImageTk.PhotoImage(crop)
            self.create_image(self.ox + box[0] * s, self.oy + box[1] * s, image=self._photo, anchor="nw")
        hl = bool(self.highlight)
        order = sorted(self.markers, key=lambda m: (m[0].key in self.highlight, m[0].key == self.selected))
        for p, u, v in order:
            x, y = self._to_canvas(u, v)
            color = STYLE.get(p.type, OTHER)[0]
            if hl and p.key not in self.highlight:
                r, outline, width = 3, "#000000", 1
            elif hl:
                r, outline, width = 7, HIGHLIGHT, 3
            else:
                r, outline, width = 5, "#000000", 1
            self.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=outline, width=width)
            if p.key == self.selected:
                self.create_oval(x - r - 6, y - r - 6, x + r + 6, y + r + 6, outline="#ffffff", width=2)
                self.create_oval(x - r - 8, y - r - 8, x + r + 8, y + r + 8, outline="#000000", width=1)
        self._legend(hl)

    def _legend(self, hl):
        seen = []
        for p, _, _ in self.markers:
            st = STYLE.get(p.type, OTHER)
            if st not in seen:
                seen.append(st)
        items = seen + ([(HIGHLIGHT, "wyróżnione")] if hl else [])
        y = 10
        for color, label in items:
            self.create_oval(10, y, 20, y + 10, fill=color, outline="#000")
            self.create_text(26, y + 5, text=label, anchor="w", fill="#ffffff", font=("Segoe UI", 9))
            y += 16
        self.create_text(10, self.winfo_height() - 8, anchor="sw", fill="#9fb3c8", font=("Segoe UI", 8),
                         text="kółko myszy – przybliżenie, przeciągnij – przesuń, dwuklik – cała mapa")

    # --- mysz ---

    def _nearest(self, ex, ey, radius=12):
        best, dist = None, radius * radius
        if not self.src:
            return None
        for p, u, v in self.markers:
            x, y = self._to_canvas(u, v)
            d = (x - ex) ** 2 + (y - ey) ** 2
            if d <= dist:
                best, dist = p, d
        return best

    def _wheel(self, e):
        if not self.src:
            return
        f = 1.25 if e.delta > 0 else 1 / 1.25
        new = min(MAX_ZOOM, max(MIN_ZOOM, self.zoom * f))
        f = new / self.zoom
        if f == 1:
            return
        self.ox = e.x - (e.x - self.ox) * f
        self.oy = e.y - (e.y - self.oy) * f
        self.zoom = new
        self._clamp()
        self.redraw()

    def _press(self, e):
        self._drag = (e.x, e.y, self.ox, self.oy, False)

    def _motion_drag(self, e):
        if not self._drag:
            return
        x, y, ox, oy, moved = self._drag
        if moved or abs(e.x - x) + abs(e.y - y) > 4:
            self._drag = (x, y, ox, oy, True)
            self.ox, self.oy = ox + e.x - x, oy + e.y - y
            self._clamp()
            self.redraw()

    def _release(self, e):
        drag, self._drag = self._drag, None
        if drag and not drag[4]:
            p = self._nearest(e.x, e.y)
            if p and self.on_pick:
                self.on_pick(p)

    def _hover(self, e):
        self.delete("tip")
        p = self._nearest(e.x, e.y)
        self.configure(cursor="hand2" if p else "")
        if not p:
            return
        t = self.create_text(e.x + 14, e.y + 12, text=self.label_fn(p), anchor="nw", fill="#ffffff",
                             font=("Segoe UI", 9), tags="tip")
        x0, y0, x1, y1 = self.bbox(t)
        w = self.winfo_width()
        if x1 > w - 4:
            self.move(t, -(x1 - x0) - 28, 0)
            x0, y0, x1, y1 = self.bbox(t)
        r = self.create_rectangle(x0 - 4, y0 - 2, x1 + 4, y1 + 2, fill="#1b2633", outline="#5c6f82", tags="tip")
        self.tag_lower(r, t)
