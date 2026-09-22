#!/usr/bin/env python3
"""Turn an EAGLE .brd of an Adafruit board into a KiCad "module" footprint
and a matching schematic symbol, so the whole board can be placed as one
part on your own PCB.

  python3 tools/brd2module.py board.brd out/ --name Adafruit_Foo \
      --pid 6525 --url https://www.adafruit.com/product/6525

What the footprint carries:
  * the board outline (EAGLE layer 20/46, from <plain> and from packages)
    on F.Fab and F.SilkS, plus a courtyard 0.25 mm outside its bounding box
  * every through-hole pad of header / terminal-block style packages,
    numbered 1..N in element order, with the EAGLE net name kept as the
    pad's pin function so it shows up on hover and in the symbol
  * plated mounting holes as un-numbered pads, non-plated <hole>s as NPTH
  * the tDocu outline of connectors (JST, USB, SD ...) on F.Fab

Everything else on the board — SMD parts, traces, silkscreen art — is the
module's own business and is left out. Coordinates are re-centred on the
outline's bounding box so the footprint anchor sits mid-board.
"""
import argparse, json, math, re, sys, xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eagle2kicad import q, num, safe, arc_mid  # noqa: E402

# Packages whose through-hole pads are the board's external pins.
PIN_PKG = re.compile(
    r"^(\d+X\d+|HEADER|TERMBLOCK|PADS-\d+|PI_HAT|PI_BONNET|ARDUINO|BEAGLEBONE"
    r"|SEW|FEATHER|QTPY|ITSYBITSY|.*TERMINAL|.*CASTELL|.*SCREWTERM)", re.I)
HOLE_PKG = re.compile(r"MOUNT|HOLE", re.I)
CONN_PKG = re.compile(r"JST|USB|STEMMA|SH4|SD|UFL|U\.FL|HDMI|DCJACK|AUDIO|SWD|QWIIC", re.I)
POWER_IN = re.compile(r"^\+?(GND|AGND|DGND|VIN|VCC|VDD|V\+|VBAT|BAT|3V3?|3\.3V|5V|VUSB|USB|VBUS|VHI|VLO|VS|V)$", re.I)
OUTLINE_LAYERS = {"20", "46"}
EDGE_W, SILK_W, FAB_W, CRTYD_W, CRTYD_GAP = 0.0, 0.12, 0.10, 0.05, 0.25


def natkey(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s or "")]


def element_xform(el):
    """Map package coordinates into board coordinates (still Y-up)."""
    rot = (el.get("rot") or "R0").upper()
    mirror = rot.startswith("M")
    ang = num(rot.lstrip("MS").lstrip("R"))
    rad = math.radians(ang)
    ex, ey = num(el.get("x")), num(el.get("y"))
    c, s = math.cos(rad), math.sin(rad)

    def f(x, y):
        if mirror:
            x = -x
        return (ex + x * c - y * s, ey + x * s + y * c)
    return f, mirror, ang


def wire_geom(w, f, mirror):
    """(p1, p2, curve, width) in board coords, curve sign fixed for mirror."""
    p1 = f(num(w.get("x1")), num(w.get("y1")))
    p2 = f(num(w.get("x2")), num(w.get("y2")))
    curve = num(w.get("curve"))
    if mirror:
        curve = -curve
    return p1, p2, curve, num(w.get("width"))


class Board:
    def __init__(self, path):
        root = ET.parse(path).getroot()
        self.eagle_version = root.get("version", "?")
        b = root.find(".//board")
        if b is None:
            raise SystemExit(f"{path}: not an EAGLE board file")
        self.board = b
        self.pkgs = {}
        for lib in b.findall("libraries/library"):
            for p in lib.findall("packages/package"):
                self.pkgs[(lib.get("name"), p.get("name"))] = p
        self.nets = {}
        for sig in b.findall("signals/signal"):
            for c in sig.findall("contactref"):
                self.nets[(c.get("element"), c.get("pad"))] = sig.get("name")
        self.elements = b.findall("elements/element")
        self.stats = {}

    def bump(self, k, n=1):
        self.stats[k] = self.stats.get(k, 0) + n

    # ---- geometry, all in EAGLE board coordinates (Y up)
    def outline(self):
        """Wires / circles on the dimension and milling layers."""
        wires, circles = [], []
        plain = self.board.find("plain")
        ident = lambda x, y: (x, y)
        for w in plain.findall("wire"):
            if w.get("layer") in OUTLINE_LAYERS:
                wires.append(wire_geom(w, ident, False))
        for c in plain.findall("circle"):
            if c.get("layer") in OUTLINE_LAYERS:
                circles.append((num(c.get("x")), num(c.get("y")), num(c.get("radius"))))
        for el in self.elements:
            pkg = self.pkgs.get((el.get("library"), el.get("package")))
            if pkg is None:
                continue
            f, mirror, _ = element_xform(el)
            for w in pkg.findall("wire"):
                if w.get("layer") in OUTLINE_LAYERS:
                    wires.append(wire_geom(w, f, mirror))
            for c in pkg.findall("circle"):
                if c.get("layer") in OUTLINE_LAYERS:
                    x, y = f(num(c.get("x")), num(c.get("y")))
                    circles.append((x, y, num(c.get("radius"))))
        return wires, circles

    def connector_docu(self):
        """tDocu / tPlace outline of connector packages, for F.Fab."""
        wires, rects = [], []
        for el in self.elements:
            if not CONN_PKG.search(el.get("package") or ""):
                continue
            pkg = self.pkgs.get((el.get("library"), el.get("package")))
            if pkg is None or (el.get("rot") or "").upper().startswith("M"):
                continue  # bottom-side connectors don't show on the top view
            f, mirror, _ = element_xform(el)
            layer_pref = "51" if any(w.get("layer") == "51" for w in pkg.findall("wire")) else "21"
            for w in pkg.findall("wire"):
                if w.get("layer") == layer_pref:
                    wires.append(wire_geom(w, f, mirror))
            for r in pkg.findall("rectangle"):
                if r.get("layer") == layer_pref:
                    pts = [f(num(r.get(a)), num(r.get(b)))
                           for a, b in (("x1", "y1"), ("x2", "y1"), ("x2", "y2"), ("x1", "y2"))]
                    rects.append(pts)
        return wires, rects

    def pads(self):
        """External pins, mounting holes and NPTH holes."""
        pins, mounts, npth = [], [], []
        seen_pkgs = {}
        for el in sorted(self.elements, key=lambda e: natkey(e.get("name"))):
            pkg = self.pkgs.get((el.get("library"), el.get("package")))
            if pkg is None:
                self.bump("elements with missing package")
                continue
            pname = el.get("package") or ""
            f, mirror, ang = element_xform(el)
            for h in pkg.findall("hole"):
                x, y = f(num(h.get("x")), num(h.get("y")))
                npth.append((x, y, num(h.get("drill"), 1.0)))
            th = pkg.findall("pad")
            if not th:
                continue
            is_pin = bool(PIN_PKG.match(pname))
            is_hole = bool(HOLE_PKG.search(pname))
            seen_pkgs.setdefault("pins" if is_pin else "holes" if is_hole else "skipped", set()).add(pname)
            for p in sorted(th, key=lambda p: natkey(p.get("name"))):
                x, y = f(num(p.get("x")), num(p.get("y")))
                drill = num(p.get("drill"), 0.8)
                dia = num(p.get("diameter")) or max(drill + 0.45, drill * 1.5)
                shp = (p.get("shape") or "round").lower()
                prot = num((p.get("rot") or "R0").upper().lstrip("MS").lstrip("R"))
                rot = ((180 - prot) if mirror else prot) + ang
                if shp in ("long", "offset"):
                    shape, size = "oval", (dia * 2, dia)
                elif shp == "square":
                    shape, size = "rect", (dia, dia)
                else:
                    shape, size = "circle", (dia, dia)
                net = self.nets.get((el.get("name"), p.get("name")))
                rec = dict(x=x, y=y, rot=rot % 360, shape=shape, size=size, drill=drill,
                           net=net, element=el.get("name"), pad=p.get("name"), package=pname)
                if is_pin:
                    pins.append(rec)
                elif is_hole or net is None:
                    mounts.append(rec)
                    self.bump("through-hole pads kept as un-numbered holes")
                else:
                    self.bump("through-hole pads of on-board components skipped")
        # A plated mounting hole shares nothing with the host board; but a
        # header pad on an internal net (N$…) is still a physical pin.
        for k, v in seen_pkgs.items():
            self.stats[f"{k} packages"] = sorted(v)
        return pins, mounts, npth


def fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) > 1e-9 else "0"


def line_or_arc(p1, p2, curve, layer, width):
    """KiCad primitive from board-coord endpoints already re-centred; Y flipped here."""
    (x1, y1), (x2, y2) = (p1[0], -p1[1]), (p2[0], -p2[1])
    if curve:
        mx, my = arc_mid((x1, y1), (x2, y2), -curve)  # Y flip reverses the sense
        head = f"\t(fp_arc (start {fmt(x1)} {fmt(y1)}) (mid {fmt(mx)} {fmt(my)}) (end {fmt(x2)} {fmt(y2)})"
    else:
        head = f"\t(fp_line (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)})"
    return f"{head}\n\t\t(stroke (width {width}) (type solid)) (layer {q(layer)})\n\t)"


def bbox_of(wires, circles):
    xs, ys = [], []
    for p1, p2, curve, _ in wires:
        for x, y in (p1, p2):
            xs.append(x); ys.append(y)
        if curve:
            mx, my = arc_mid(p1, p2, curve)
            xs.append(mx); ys.append(my)
    for x, y, r in circles:
        xs += [x - r, x + r]; ys += [y - r, y + r]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def footprint(board, name, lib, descr, tags, url):
    wires, circles = board.outline()
    bb = bbox_of(wires, circles)
    pins, mounts, npth = board.pads()
    if bb is None:
        raise SystemExit("no board outline on EAGLE layer 20/46")
    if not pins:
        raise SystemExit("no header/terminal pads found; nothing to expose as pins")
    cx, cy = round((bb[0] + bb[2]) / 2, 2), round((bb[1] + bb[3]) / 2, 2)
    shift = lambda p: (p[0] - cx, p[1] - cy)
    w, h = bb[2] - bb[0], bb[3] - bb[1]

    out = [f"(footprint {q(name)}", "\t(version 20240108)", '\t(generator "brd2module")',
           '\t(generator_version "8.0")', '\t(layer "F.Cu")', f"\t(descr {q(descr)})",
           f"\t(tags {q(tags)})", "\t(attr through_hole)"]
    props = [("Reference", "REF**", "F.SilkS", (0, -h / 2 + 1.5), False),
             ("Value", name, "F.Fab", (0, 0), False),
             ("Footprint", f"{lib}:{name}", "F.Fab", (0, 0), True),
             ("Datasheet", url or "", "F.Fab", (0, 0), True),
             ("Description", descr, "F.Fab", (0, 0), True)]
    for key, val, layer, (px, py), hide in props:
        out.append(f"\t(property {q(key)} {q(val)}\n\t\t(at {fmt(px)} {fmt(py)} 0)\n"
                   f"\t\t(layer {q(layer)})" + ("\n\t\t(hide yes)" if hide else "") +
                   "\n\t\t(effects (font (size 1 1) (thickness 0.15)))\n\t)")

    for layer, width in (("F.Fab", FAB_W), ("F.SilkS", SILK_W)):
        for p1, p2, curve, _ in wires:
            out.append(line_or_arc(shift(p1), shift(p2), curve, layer, width))
        for x, y, r in circles:
            x, y = shift((x, y))
            out.append(f"\t(fp_circle (center {fmt(x)} {fmt(-y)}) (end {fmt(x + r)} {fmt(-y)})\n"
                       f"\t\t(stroke (width {width}) (type solid)) (fill none) (layer {q(layer)})\n\t)")
    dwires, drects = board.connector_docu()
    for p1, p2, curve, _ in dwires:
        out.append(line_or_arc(shift(p1), shift(p2), curve, "F.Fab", FAB_W))
    for pts in drects:
        pts = [shift(p) for p in pts]
        out.append("\t(fp_poly\n\t\t(pts " + " ".join(f"(xy {fmt(x)} {fmt(-y)})" for x, y in pts) +
                   f")\n\t\t(stroke (width {FAB_W}) (type solid)) (fill none) (layer \"F.Fab\")\n\t)")
    # Courtyard: outline bounding box plus the KLC clearance.
    x0, y0 = -w / 2 - CRTYD_GAP, -h / 2 - CRTYD_GAP
    x1, y1 = w / 2 + CRTYD_GAP, h / 2 + CRTYD_GAP
    out.append(f"\t(fp_rect (start {fmt(x0)} {fmt(y0)}) (end {fmt(x1)} {fmt(y1)})\n"
               f"\t\t(stroke (width {CRTYD_W}) (type solid)) (fill none) (layer \"F.CrtYd\")\n\t)")

    def emit_pad(number, r, pinfunction=None):
        x, y = shift((r["x"], r["y"]))
        extra = f"\n\t\t(pinfunction {q(pinfunction)})" if pinfunction else ""
        out.append(f"\t(pad {q(number)} thru_hole {r['shape']}\n"
                   f"\t\t(at {fmt(x)} {fmt(-y)} {r['rot']:.0f})\n"
                   f"\t\t(size {fmt(r['size'][0])} {fmt(r['size'][1])}) (drill {fmt(r['drill'])})\n"
                   f"\t\t(layers \"*.Cu\" \"*.Mask\"){extra}\n\t)")

    pinmap = []
    for i, r in enumerate(pins, 1):
        net = r["net"]
        func = None if (net is None or net.startswith("N$")) else net
        emit_pad(str(i), r, func)
        pinmap.append({"number": i, "name": func, "element": r["element"], "pad": r["pad"]})
    for r in mounts:
        emit_pad("", r)
    for x, y, d in npth:
        x, y = shift((x, y))
        out.append(f'\t(pad "" np_thru_hole circle\n\t\t(at {fmt(x)} {fmt(-y)})\n'
                   f"\t\t(size {fmt(d)} {fmt(d)}) (drill {fmt(d)})\n"
                   '\t\t(layers "F.Cu" "B.Cu" "F.Mask" "B.Mask")\n\t)')
    out.append(")")
    return "\n".join(out) + "\n", pinmap, (round(w, 2), round(h, 2))


def symbol(name, lib, descr, url, keywords, pinmap):
    """A rectangle with power pins top/bottom and everything else left/right."""
    seen = {}
    for p in pinmap:
        base = p["name"] or f"P{p['number']}"
        seen[base] = seen.get(base, 0) + 1
        p["label"] = base if seen[base] == 1 else f"{base}_{seen[base]}"
    is_gnd = lambda p: bool(p["name"]) and p["name"].upper().endswith("GND")
    top = [p for p in pinmap if p["name"] and POWER_IN.match(p["name"]) and not is_gnd(p)]
    bottom = [p for p in pinmap if is_gnd(p)]
    rest = [p for p in pinmap if p not in top and p not in bottom]
    left, right = rest[:(len(rest) + 1) // 2], rest[(len(rest) + 1) // 2:]
    if len(rest) <= 10:
        left, right = rest, []
    rows = max(len(left), len(right), 1)
    longest = max((len(p["label"]) for p in pinmap), default=4)
    half_w = max(7.62, math.ceil((longest * 1.27 * 2 + 5.08) / 2.54) * 2.54 / 2)
    half_h = max(5.08, (rows + 1) * 2.54 / 2 + 1.27)
    half_h = math.ceil(half_h / 1.27) * 1.27
    half_w = math.ceil(half_w / 1.27) * 1.27
    pin_len = 2.54

    def pin(p, x, y, rot):
        etype = "power_in" if p in top or p in bottom else "passive"
        return (f"\t\t(pin {etype} line\n\t\t\t(at {fmt(x)} {fmt(y)} {rot})\n"
                f"\t\t\t(length {fmt(pin_len)})\n"
                f"\t\t\t(name {q(p['label'])}\n\t\t\t\t(effects (font (size 1.27 1.27)))\n\t\t\t)\n"
                f"\t\t\t(number {q(str(p['number']))}\n\t\t\t\t(effects (font (size 1.27 1.27)))\n\t\t\t)\n\t\t)")

    body = [f"\t(symbol {q(name + '_0_1')}",
            f"\t\t(rectangle (start {fmt(-half_w)} {fmt(half_h)}) (end {fmt(half_w)} {fmt(-half_h)})\n"
            "\t\t\t(stroke (width 0.254) (type default)) (fill (type background))\n\t\t)", "\t)",
            f"\t(symbol {q(name + '_1_1')}"]
    y = half_h - 2.54
    for p in left:
        body.append(pin(p, -half_w - pin_len, y, 0)); y -= 2.54
    y = half_h - 2.54
    for p in right:
        body.append(pin(p, half_w + pin_len, y, 180)); y -= 2.54
    def spread(n):
        return [(i - (n - 1) / 2) * 2.54 for i in range(n)]
    for p, x in zip(top, spread(len(top))):
        body.append(pin(p, x, half_h + pin_len, 270))
    for p, x in zip(bottom, spread(len(bottom))):
        body.append(pin(p, x, -half_h - pin_len, 90))
    body.append("\t)")

    head = [f"(symbol {q(name)}", "\t(pin_names (offset 0.254))", "\t(exclude_from_sim no)",
            "\t(in_bom yes)", "\t(on_board yes)"]
    # Keep the reference and value clear of the top/bottom power pins.
    ref_y = half_h + (pin_len if top else 0) + 1.27
    val_y = -half_h - (pin_len if bottom else 0) - 1.27
    props = [("Reference", "A", (-half_w, ref_y), False),
             ("Value", name, (-half_w, val_y), False),
             ("Footprint", f"{lib}:{name}", (0, 0), True),
             ("Datasheet", url or "", (0, 0), True),
             ("Description", descr, (0, 0), True),
             ("ki_keywords", keywords, (0, 0), True),
             ("ki_fp_filters", name, (0, 0), True)]
    for key, val, (px, py), hide in props:
        head.append(f"\t(property {q(key)} {q(val)}\n\t\t(at {fmt(px)} {fmt(py)} 0)\n"
                    "\t\t(effects (font (size 1.27 1.27)) (justify left)" +
                    (" (hide yes)" if hide else "") + ")\n\t)")
    return "\n".join(head + body) + "\n)"


def convert(brd, name, title=None, pid=None, url=None, source=None,
            keywords="adafruit breakout board module", lib="PCM_Adafruit_Boards"):
    """Return {'footprint': text, 'symbol': text, 'report': dict}."""
    board = Board(brd)
    title = title or safe(Path(brd).stem)
    descr = title
    if pid:
        descr += f" (Adafruit product {pid})"
    descr += " as a placeable module: board outline, mounting holes and header pins"
    if source:
        descr += f". Generated from {source}"
    fp_text, pinmap, size = footprint(board, name, lib, descr, keywords, url)
    sym_text = symbol(name, lib, descr, url, keywords, pinmap)
    report = {"name": name, "pid": pid, "source": source, "size_mm": size,
              "pins": pinmap, "stats": board.stats, "eagle_version": board.eagle_version}
    return {"footprint": fp_text, "symbol": sym_text, "report": report}


SYM_HEADER = ('(kicad_symbol_lib\n\t(version 20231120)\n\t(generator "brd2module")\n'
              '\t(generator_version "8.0")\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("brd")
    ap.add_argument("outdir")
    ap.add_argument("--name", required=True, help="footprint / symbol name")
    ap.add_argument("--lib", default="PCM_Adafruit_Boards", help="library nickname used in Footprint links")
    ap.add_argument("--pretty", default="Adafruit_Boards", help="basename of the .pretty / .kicad_sym")
    ap.add_argument("--pid", type=int)
    ap.add_argument("--url")
    ap.add_argument("--title", help="product title for the description")
    ap.add_argument("--source", help="where the .brd came from, for the description")
    ap.add_argument("--keywords", default="adafruit breakout board module")
    a = ap.parse_args()

    r = convert(a.brd, a.name, a.title, a.pid, a.url, a.source, a.keywords, a.lib)
    out = Path(a.outdir)
    fp_dir = out / "footprints" / f"{a.pretty}.pretty"
    fp_dir.mkdir(parents=True, exist_ok=True)
    (fp_dir / f"{a.name}.kicad_mod").write_text(r["footprint"])
    (out / "symbols").mkdir(parents=True, exist_ok=True)
    (out / "symbols" / f"{a.pretty}.kicad_sym").write_text(SYM_HEADER + r["symbol"] + "\n)\n")
    print(json.dumps(r["report"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
