#!/usr/bin/env python3
"""Convert an EAGLE .lbr library into KiCad 8 symbols and footprints.

  python3 tools/eagle2kicad.py adafruit.lbr package/ --prefix Adafruit

Coordinates in EAGLE library XML are millimetres with Y pointing up.
.kicad_sym keeps that convention; .kicad_mod flips Y (it points down), which
also reverses arc handedness. Both are handled below.

Symbols are generated per deviceset/device rather than per EAGLE symbol,
because only the deviceset's <connect> elements carry the symbol-pin-name to
package-pad-number mapping. Converting bare symbols loses all pin numbers.
"""
import argparse, math, re, sys, xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

# EAGLE layer number -> KiCad footprint layer. Unlisted layers are dropped.
FP_LAYER = {
    "1": "F.Cu", "16": "B.Cu",
    "20": "Edge.Cuts", "46": "Edge.Cuts",
    "21": "F.SilkS", "22": "B.SilkS",
    "25": "F.SilkS", "26": "B.SilkS",
    "27": "F.Fab", "28": "B.Fab",
    "29": "F.Mask", "30": "B.Mask",
    "31": "F.Paste", "32": "B.Paste",
    "35": "F.Fab", "36": "B.Fab",
    "39": "F.CrtYd", "40": "B.CrtYd",
    "51": "F.Fab", "52": "B.Fab",
    "48": "User.Comments", "49": "User.Comments",
}
PIN_LEN = {"point": 0.0, "short": 2.54, "middle": 5.08, "long": 7.62}
ELEC = {"pas": "passive", "in": "input", "out": "output", "io": "bidirectional",
        "oc": "open_collector", "hiz": "tri_state", "pwr": "power_in",
        "sup": "power_out", "nc": "no_connect", None: "passive"}
SHAPE = {"dot": "inverted", "clk": "clock", "dotclk": "inverted_clock",
         "clkdot": "inverted_clock", None: "line"}
stats = Counter()


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def safe(name):
    """KiCad forbids these in library item names."""
    return re.sub(r'[\s/\\:"<>|?*\x00-\x1f]', "_", (name or "").strip()) or "UNNAMED"


def clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def rot_of(el):
    r = (el.get("rot") or "R0").upper().lstrip("MS")
    return num(r.lstrip("R")) % 360


def arc_mid(p1, p2, curve):
    """EAGLE curve = included angle in degrees, positive counter-clockwise."""
    (x1, y1), (x2, y2) = p1, p2
    dx, dy = x2 - x1, y2 - y1
    chord = math.hypot(dx, dy)
    half = math.radians(curve) / 2
    if chord == 0 or abs(math.sin(half)) < 1e-12:
        return ((x1 + x2) / 2, (y1 + y2) / 2)
    radius = chord / (2 * math.sin(half))
    px, py = -dy / chord, dx / chord
    off = radius * math.cos(half)
    cx, cy = (x1 + x2) / 2 + px * off, (y1 + y2) / 2 + py * off
    vx, vy = x1 - cx, y1 - cy
    c, s = math.cos(half), math.sin(half)
    return (cx + vx * c - vy * s, cy + vx * s + vy * c)


# --------------------------------------------------------------- footprints
def convert_package(pkg, prefix):
    name = safe(pkg.get("name"))
    out = [f'(footprint {q(name)}',
           '\t(version 20240108)',
           '\t(generator "eagle2kicad")',
           '\t(generator_version "8.0")',
           '\t(layer "F.Cu")']
    descr = clean(pkg.findtext("description"))
    if descr:
        out.append(f'\t(descr {q(descr[:800])})')

    has_smd = pkg.find("smd") is not None
    has_th = pkg.find("pad") is not None
    out.append(f'\t(attr {"through_hole" if has_th else "smd"})')

    # Reference/Value come from EAGLE's >NAME / >VALUE placeholder texts.
    ref_at, val_at, free = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), []
    for t in pkg.findall("text"):
        txt = (t.text or "").strip()
        pos = (num(t.get("x")), -num(t.get("y")), rot_of(t))
        size = max(num(t.get("size"), 1.0), 0.5)
        if txt == ">NAME":
            ref_at = pos
        elif txt == ">VALUE":
            val_at = pos
        elif txt:
            free.append((txt, pos, size, FP_LAYER.get(t.get("layer"), "F.Fab")))

    for key, val, layer, hide in (("Reference", "REF**", "F.SilkS", False),
                                  ("Value", name, "F.Fab", False),
                                  ("Footprint", f"{prefix}:{name}", "F.Fab", True),
                                  ("Datasheet", "", "F.Fab", True),
                                  ("Description", descr[:300], "F.Fab", True)):
        at = ref_at if key == "Reference" else val_at
        out.append(f'\t(property {q(key)} {q(val)}')
        out.append(f'\t\t(at {at[0]:.4f} {at[1]:.4f} {at[2]:.0f})')
        out.append(f'\t\t(layer {q(layer)})')
        if hide or key in ("Footprint", "Datasheet", "Description"):
            out.append("\t\t(hide yes)")
        out.append('\t\t(effects (font (size 1 1) (thickness 0.15)))')
        out.append("\t)")

    for txt, pos, size, layer in free:
        out.append(f'\t(fp_text user {q(txt)}')
        out.append(f'\t\t(at {pos[0]:.4f} {pos[1]:.4f} {pos[2]:.0f})')
        out.append(f'\t\t(layer {q(layer)})')
        out.append(f'\t\t(effects (font (size {size:.3f} {size:.3f}) '
                   f'(thickness {size * 0.15:.3f})))')
        out.append("\t)")

    for w in pkg.findall("wire"):
        layer = FP_LAYER.get(w.get("layer"))
        if not layer:
            stats[f"skipped wire on EAGLE layer {w.get('layer')}"] += 1
            continue
        width = max(num(w.get("width"), 0.12), 0.01)
        p1 = (num(w.get("x1")), -num(w.get("y1")))
        p2 = (num(w.get("x2")), -num(w.get("y2")))
        curve = num(w.get("curve"))
        if curve:
            # Y was negated, so the arc's sense reverses.
            mx, my = arc_mid(p1, p2, -curve)
            out.append(f'\t(fp_arc (start {p1[0]:.4f} {p1[1]:.4f}) '
                       f'(mid {mx:.4f} {my:.4f}) (end {p2[0]:.4f} {p2[1]:.4f})')
        else:
            out.append(f'\t(fp_line (start {p1[0]:.4f} {p1[1]:.4f}) '
                       f'(end {p2[0]:.4f} {p2[1]:.4f})')
        out.append(f'\t\t(stroke (width {width:.4f}) (type solid)) (layer {q(layer)})')
        out.append("\t)")

    for r in pkg.findall("rectangle"):
        layer = FP_LAYER.get(r.get("layer"))
        if not layer:
            stats[f"skipped rectangle on EAGLE layer {r.get('layer')}"] += 1
            continue
        x1, x2 = sorted((num(r.get("x1")), num(r.get("x2"))))
        y1, y2 = sorted((-num(r.get("y1")), -num(r.get("y2"))))
        out.append(f'\t(fp_rect (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f})')
        out.append(f'\t\t(stroke (width 0.05) (type solid)) (fill solid) '
                   f'(layer {q(layer)})')
        out.append("\t)")

    for c in pkg.findall("circle"):
        layer = FP_LAYER.get(c.get("layer"))
        if not layer:
            stats[f"skipped circle on EAGLE layer {c.get('layer')}"] += 1
            continue
        cx, cy, rad = num(c.get("x")), -num(c.get("y")), num(c.get("radius"))
        width = num(c.get("width"), 0.12)
        fill = "solid" if width == 0 else "none"
        if width == 0:
            rad, width = rad, 0.05
        out.append(f'\t(fp_circle (center {cx:.4f} {cy:.4f}) '
                   f'(end {cx + rad:.4f} {cy:.4f})')
        out.append(f'\t\t(stroke (width {max(width, 0.01):.4f}) (type solid)) '
                   f'(fill {fill}) (layer {q(layer)})')
        out.append("\t)")

    for p in pkg.findall("polygon"):
        layer = FP_LAYER.get(p.get("layer"))
        pts = [(num(v.get("x")), -num(v.get("y"))) for v in p.findall("vertex")]
        if not layer or len(pts) < 3:
            continue
        out.append("\t(fp_poly")
        out.append("\t\t(pts " + " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in pts) + ")")
        out.append(f'\t\t(stroke (width {max(num(p.get("width"), 0.05), 0.01):.4f}) '
                   f'(type solid)) (fill solid) (layer {q(layer)})')
        out.append("\t)")

    for s in pkg.findall("smd"):
        back = s.get("layer") == "16"
        dx, dy = num(s.get("dx"), 1), num(s.get("dy"), 1)
        roundness = num(s.get("roundness"))
        if roundness >= 100:
            shape = "oval"
            extra = ""
        elif roundness > 0:
            shape = "roundrect"
            extra = f" (roundrect_rratio {roundness / 200:.4f})"
        else:
            shape = "rect"
            extra = ""
        layers = ["B.Cu" if back else "F.Cu"]
        if s.get("cream") != "no":
            layers.append("B.Paste" if back else "F.Paste")
        if s.get("stop") != "no":
            layers.append("B.Mask" if back else "F.Mask")
        out.append(f'\t(pad {q(s.get("name") or "")} smd {shape}')
        out.append(f'\t\t(at {num(s.get("x")):.4f} {-num(s.get("y")):.4f} '
                   f'{rot_of(s):.0f})')
        out.append(f'\t\t(size {dx:.4f} {dy:.4f})')
        out.append("\t\t(layers " + " ".join(q(l) for l in layers) + ")" + extra)
        out.append("\t)")
        stats["smd pads"] += 1

    for p in pkg.findall("pad"):
        drill = num(p.get("drill"), 0.8)
        # EAGLE auto-sizes the annulus when diameter is absent.
        dia = num(p.get("diameter")) or max(drill + 0.45, drill * 1.5)
        shp = (p.get("shape") or "round").lower()
        if shp in ("long", "offset"):
            shape, size = "oval", (dia * 2, dia)
        elif shp == "square":
            shape, size = "rect", (dia, dia)
        else:  # round, octagon -> circle (KiCad has no octagon primitive)
            shape, size = "circle", (dia, dia)
            if shp == "octagon":
                stats["octagon pads mapped to circle"] += 1
        out.append(f'\t(pad {q(p.get("name") or "")} thru_hole {shape}')
        out.append(f'\t\t(at {num(p.get("x")):.4f} {-num(p.get("y")):.4f} '
                   f'{rot_of(p):.0f})')
        out.append(f'\t\t(size {size[0]:.4f} {size[1]:.4f}) (drill {drill:.4f})')
        out.append('\t\t(layers "*.Cu" "*.Mask")')
        out.append("\t)")
        stats["through-hole pads"] += 1

    for h in pkg.findall("hole"):
        drill = num(h.get("drill"), 1.0)
        out.append('\t(pad "" np_thru_hole circle')
        out.append(f'\t\t(at {num(h.get("x")):.4f} {-num(h.get("y")):.4f})')
        out.append(f'\t\t(size {drill:.4f} {drill:.4f}) (drill {drill:.4f})')
        out.append('\t\t(layers "F.Cu" "B.Cu" "F.Mask" "B.Mask")')
        out.append("\t)")

    out.append(")")
    return name, "\n".join(out) + "\n"


# ------------------------------------------------------------------ symbols
def symbol_body(sym_el, unit, pad_of, sym_name):
    """Graphics + pins for one EAGLE gate, as a KiCad sub-unit."""
    g, p = [], []
    for w in sym_el.findall("wire"):
        x1, y1 = num(w.get("x1")), num(w.get("y1"))
        x2, y2 = num(w.get("x2")), num(w.get("y2"))
        width = num(w.get("width"), 0.254)
        curve = num(w.get("curve"))
        if curve:
            mx, my = arc_mid((x1, y1), (x2, y2), curve)
            g.append(f'\t\t(arc (start {x1:.4f} {y1:.4f}) (mid {mx:.4f} {my:.4f}) '
                     f'(end {x2:.4f} {y2:.4f})\n'
                     f'\t\t\t(stroke (width {width:.4f}) (type default)) '
                     f'(fill (type none))\n\t\t)')
        else:
            g.append(f'\t\t(polyline\n\t\t\t(pts (xy {x1:.4f} {y1:.4f}) '
                     f'(xy {x2:.4f} {y2:.4f}))\n'
                     f'\t\t\t(stroke (width {width:.4f}) (type default)) '
                     f'(fill (type none))\n\t\t)')
    for r in sym_el.findall("rectangle"):
        x1, x2 = sorted((num(r.get("x1")), num(r.get("x2"))))
        y1, y2 = sorted((num(r.get("y1")), num(r.get("y2"))))
        g.append(f'\t\t(rectangle (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f})\n'
                 f'\t\t\t(stroke (width 0.254) (type default)) '
                 f'(fill (type background))\n\t\t)')
    for c in sym_el.findall("circle"):
        width = num(c.get("width"), 0.254)
        g.append(f'\t\t(circle (center {num(c.get("x")):.4f} {num(c.get("y")):.4f}) '
                 f'(radius {num(c.get("radius")):.4f})\n'
                 f'\t\t\t(stroke (width {max(width, 0.01):.4f}) (type default)) '
                 f'(fill (type {"background" if width == 0 else "none"}))\n\t\t)')
    for poly in sym_el.findall("polygon"):
        pts = [(num(v.get("x")), num(v.get("y"))) for v in poly.findall("vertex")]
        if len(pts) >= 3:
            g.append("\t\t(polyline\n\t\t\t(pts " +
                     " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in pts) + ")\n"
                     '\t\t\t(stroke (width 0.254) (type default)) '
                     "(fill (type background))\n\t\t)")
    for t in sym_el.findall("text"):
        txt = (t.text or "").strip()
        if txt in (">NAME", ">VALUE", ""):
            continue
        size = max(num(t.get("size"), 1.27), 0.5)
        g.append(f'\t\t(text {q(txt)} (at {num(t.get("x")):.4f} '
                 f'{num(t.get("y")):.4f} 0)\n'
                 f'\t\t\t(effects (font (size {size:.3f} {size:.3f})))\n\t\t)')

    seen = Counter()
    for pin in sym_el.findall("pin"):
        pname = pin.get("name") or "~"
        number = pad_of.get(pname)
        if number is None:
            number = pname
            stats["pins with no <connect> mapping"] += 1
        # KiCad requires unique pin numbers within a unit.
        seen[number] += 1
        if seen[number] > 1:
            stats["duplicate pin numbers disambiguated"] += 1
            number = f"{number}_{seen[number]}"
        vis = pin.get("visible")
        hide_name = "\n\t\t\t\t(hide yes)" if vis in ("off", "pad") else ""
        hide_num = "\n\t\t\t\t(hide yes)" if vis in ("off", "pin") else ""
        p.append(
            f'\t\t(pin {ELEC.get(pin.get("direction"), "passive")} '
            f'{SHAPE.get(pin.get("function"), "line")}\n'
            f'\t\t\t(at {num(pin.get("x")):.4f} {num(pin.get("y")):.4f} '
            f'{rot_of(pin):.0f})\n'
            f'\t\t\t(length {PIN_LEN.get(pin.get("length"), 2.54):.4f})\n'
            f'\t\t\t(name {q(pname)}\n\t\t\t\t(effects (font (size 1.27 1.27))'
            f'{hide_name})\n\t\t\t)\n'
            f'\t\t\t(number {q(number)}\n\t\t\t\t(effects (font (size 1.27 1.27))'
            f'{hide_num})\n\t\t\t)\n\t\t)')
        stats["pins"] += 1

    blocks = []
    if g:
        blocks.append(f'\t(symbol {q(f"{sym_name}_{unit}_1")}\n' + "\n".join(g) + "\n\t)")
    if p:
        blocks.append(f'\t(symbol {q(f"{sym_name}_{unit}_0")}\n' + "\n".join(p) + "\n\t)")
    return blocks


def convert_deviceset(ds, symbols, prefix, used):
    gates = ds.findall("gates/gate")
    devices = ds.findall("devices/device")
    if not gates:
        stats["devicesets skipped (no gates)"] += 1
        return []
    descr = clean(ds.findtext("description"))
    out = []
    for dev in devices:
        base = safe(ds.get("name"))
        # A deviceset with several package variants becomes several symbols;
        # KiCad has no single-symbol equivalent of EAGLE device variants.
        dname = safe(dev.get("name") or "")
        name = base if len(devices) == 1 else f"{base}{'' if dname.startswith('_') else '_'}{dname}"
        name = re.sub(r"_+$", "", name) or base
        while name in used:
            stats["duplicate symbol names disambiguated"] += 1
            name += "_alt"
        used.add(name)

        pkg_name = safe(dev.get("package")) if dev.get("package") else ""
        # connect: gate name + symbol pin name -> package pad number
        pad_of = {}
        for con in dev.findall("connects/connect"):
            pad_of[(con.get("gate"), con.get("pin"))] = con.get("pad")

        body, unit = [], 0
        for gate in gates:
            sym_el = symbols.get(gate.get("symbol"))
            if sym_el is None:
                stats["gates skipped (symbol missing)"] += 1
                continue
            unit += 1
            gname = gate.get("name")
            mapping = {pin: pad for (g, pin), pad in pad_of.items() if g == gname}
            body += symbol_body(sym_el, unit, mapping, name)
        if not body:
            continue

        head = [f'(symbol {q(name)}',
                f'\t(pin_names (offset 0.254))',
                f'\t(exclude_from_sim no)',
                f'\t(in_bom yes)',
                f'\t(on_board yes)']
        if unit > 1:
            head.insert(1, "\t(unit_name_hidden no)")
        props = [("Reference", ds.get("prefix") or "U", False),
                 ("Value", name, False),
                 ("Footprint", f"{prefix}:{pkg_name}" if pkg_name else "", True),
                 ("Datasheet", "https://github.com/adafruit/Adafruit-Eagle-Library", True),
                 ("Description", descr[:500], True)]
        for i, (key, val, hide) in enumerate(props):
            head.append(f'\t(property {q(key)} {q(val)}')
            head.append(f'\t\t(at 0 {(len(props) - i) * 2.54:.2f} 0)')
            head.append('\t\t(effects (font (size 1.27 1.27))' +
                        (" (hide yes)" if hide else "") + ")")
            head.append("\t)")
        if pkg_name:
            head.append(f'\t(property "ki_fp_filters" {q(pkg_name)}\n'
                        '\t\t(at 0 0 0)\n'
                        '\t\t(effects (font (size 1.27 1.27)) (hide yes))\n\t)')
        out.append("\n".join(head) + "\n" + "\n".join(body) + "\n)")
        stats["symbols"] += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lbr")
    ap.add_argument("outdir")
    ap.add_argument("--prefix", default="Adafruit")
    a = ap.parse_args()

    lib = ET.parse(a.lbr).getroot().find(".//library")
    out = Path(a.outdir)
    fp_dir = out / "footprints" / f"{a.prefix}.pretty"
    fp_dir.mkdir(parents=True, exist_ok=True)
    (out / "symbols").mkdir(parents=True, exist_ok=True)

    seen = set()
    for pkg in lib.findall("packages/package"):
        name, text = convert_package(pkg, a.prefix)
        if name in seen:
            stats["duplicate footprint names skipped"] += 1
            continue
        seen.add(name)
        (fp_dir / f"{name}.kicad_mod").write_text(text)
        stats["footprints"] += 1

    symbols = {s.get("name"): s for s in lib.findall("symbols/symbol")}
    used, blocks = set(), []
    for ds in lib.findall("devicesets/deviceset"):
        blocks += convert_deviceset(ds, symbols, a.prefix, used)

    lib_text = ("(kicad_symbol_lib\n\t(version 20231120)\n"
                '\t(generator "eagle2kicad")\n\t(generator_version "8.0")\n'
                + "\n".join(blocks) + "\n)\n")
    (out / "symbols" / f"{a.prefix}.kicad_sym").write_text(lib_text)

    print(f"footprints -> {fp_dir.relative_to(out.parent)}/  ({stats['footprints']})")
    print(f"symbols    -> symbols/{a.prefix}.kicad_sym  ({stats['symbols']})")
    print("\nconversion notes:")
    for k, v in sorted(stats.items(), key=lambda kv: -kv[1]):
        if k not in ("footprints", "symbols"):
            print(f"  {v:>6}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
