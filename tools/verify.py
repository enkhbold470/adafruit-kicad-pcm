#!/usr/bin/env python3
"""Structural + fidelity check of converted output against the EAGLE source."""
import math, re, sys, xml.etree.ElementTree as ET
from pathlib import Path

def tokenize(s):
    return re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', s)

def parse(text, label):
    """Strict s-expression parse; raises on imbalance or trailing garbage."""
    toks = tokenize(text)
    pos = 0
    def node():
        nonlocal pos
        if toks[pos] != "(":
            raise ValueError(f"{label}: expected '(' at token {pos}")
        pos += 1
        out = []
        while True:
            if pos >= len(toks):
                raise ValueError(f"{label}: unbalanced parens (EOF)")
            t = toks[pos]
            if t == ")":
                pos += 1
                return out
            if t == "(":
                out.append(node())
            else:
                out.append(t)
                pos += 1
    tree = node()
    if pos != len(toks):
        raise ValueError(f"{label}: {len(toks) - pos} trailing tokens")
    return tree

def walk(n, tag):
    if isinstance(n, list):
        if n and n[0] == tag:
            yield n
        for c in n:
            yield from walk(c, tag)

errors, warns = [], []
lbr, out = Path(sys.argv[1]), Path(sys.argv[2])
lib = ET.parse(lbr).getroot().find(".//library")

# ---- footprints
src_pkg = {}
for p in lib.findall("packages/package"):
    src_pkg[re.sub(r'[\s/\\:"<>|?*]', "_", p.get("name").strip())] = p
mods = sorted((out / "footprints" / "Adafruit.pretty").glob("*.kicad_mod"))
print(f"checking {len(mods)} footprints ...")
bad_geom = 0
for m in mods:
    try:
        tree = parse(m.read_text(), m.name)
    except ValueError as e:
        errors.append(str(e)); continue
    if tree[0] != "footprint":
        errors.append(f"{m.name}: root is {tree[0]!r}, not 'footprint'")
    pads = list(walk(tree, "pad"))
    pkg = src_pkg.get(m.stem)
    if pkg is not None:
        want = (len(pkg.findall("smd")) + len(pkg.findall("pad"))
                + len(pkg.findall("hole")))
        if len(pads) != want:
            errors.append(f"{m.name}: {len(pads)} pads, EAGLE has {want}")
    for pad in pads:
        size = next(walk(pad, "size"), None)
        if not size:
            errors.append(f"{m.name}: pad with no size"); continue
        w, h = float(size[1]), float(size[2])
        if not (math.isfinite(w) and math.isfinite(h)) or w <= 0 or h <= 0:
            errors.append(f"{m.name}: pad size {w}x{h}"); bad_geom += 1
        if w > 60 or h > 60:
            warns.append(f"{m.name}: unusually large pad {w:.2f}x{h:.2f}mm")
        dr = next(walk(pad, "drill"), None)
        if dr and pad[2] in ("thru_hole", "np_thru_hole"):
            d = float(dr[1])
            if d <= 0 or d >= max(w, h) + 1e-6:
                warns.append(f"{m.name}: drill {d:.3f} >= pad {w:.2f}x{h:.2f}")
    for tok in ("at", "start", "end", "mid", "center", "xy"):
        for el in walk(tree, tok):
            for v in el[1:3]:
                try:
                    f = float(v)
                except ValueError:
                    continue
                if not math.isfinite(f) or abs(f) > 1000:
                    errors.append(f"{m.name}: coord {v} in ({tok} ...)")

# ---- symbols
symlib = out / "symbols" / "Adafruit.kicad_sym"
print(f"checking {symlib.name} ...")
tree = parse(symlib.read_text(), symlib.name)
syms = [s for s in tree if isinstance(s, list) and s and s[0] == "symbol"]
print(f"  {len(syms)} top-level symbols")
names = [s[1].strip('"') for s in syms]
if len(names) != len(set(names)):
    dupes = [n for n in set(names) if names.count(n) > 1]
    errors.append(f"duplicate symbol names: {dupes[:5]}")
total_pins = 0
for s in syms:
    name = s[1].strip('"')
    units = {}
    for sub in s:
        if isinstance(sub, list) and sub and sub[0] == "symbol":
            uname = sub[1].strip('"')
            mo = re.search(r"_(\d+)_(\d+)$", uname)
            if not mo:
                errors.append(f"{name}: malformed sub-unit name {uname!r}"); continue
            unit = mo.group(1)
            nums = [p[1].strip('"') for p in walk(sub, "number")]
            units.setdefault(unit, []).extend(nums)
            total_pins += len(nums)
    for unit, nums in units.items():
        if len(nums) != len(set(nums)):
            d = [n for n in set(nums) if nums.count(n) > 1]
            errors.append(f"{name} unit {unit}: duplicate pin numbers {d[:4]}")
    if not units:
        warns.append(f"{name}: no sub-units")
print(f"  {total_pins} pins")

# ---- targeted fidelity check: MAX1811/SO08 pin-name -> pad-number mapping
print("\nfidelity spot-check: MAX1811 (pin name -> pad number)")
ds = next(d for d in lib.findall("devicesets/deviceset") if d.get("name") == "MAX1811")
dev = ds.find("devices/device")
want = {c.get("pin"): c.get("pad") for c in dev.findall("connects/connect")}
sym = next(s for s in syms if s[1].strip('"').startswith("MAX1811"))
got = {}
for sub in sym:
    if isinstance(sub, list) and sub and sub[0] == "symbol":
        for pin in walk(sub, "pin"):
            nm = next(walk(pin, "name"), None)
            nu = next(walk(pin, "number"), None)
            if nm and nu:
                got[nm[1].strip('"')] = nu[1].strip('"')
for k in sorted(want):
    ok = got.get(k) == want[k]
    print(f"  {'ok ' if ok else 'BAD'} {k:>6} -> EAGLE pad {want[k]}, converted {got.get(k)}")
    if not ok:
        errors.append(f"MAX1811 pin {k}: expected pad {want[k]}, got {got.get(k)}")

print("\n" + "=" * 60)
for w in warns[:12]:
    print(f"WARN  {w}")
if len(warns) > 12:
    print(f"      ... +{len(warns) - 12} more warnings")
for e in errors[:20]:
    print(f"ERROR {e}")
if len(errors) > 20:
    print(f"      ... +{len(errors) - 20} more errors")
print(f"\n{len(errors)} errors, {len(warns)} warnings")
sys.exit(1 if errors else 0)
