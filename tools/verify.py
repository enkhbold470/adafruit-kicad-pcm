#!/usr/bin/env python3
"""Structural + fidelity check of the converted output.

  python3 tools/verify.py tools/adafruit.lbr package/ [--kicad-cli auto|PATH|none]

Checks every .pretty and .kicad_sym under package/: strict s-expression
parsing, sane pad geometry and coordinates, unique symbol names and pin
numbers, that every Footprint link uses the PCM_ nickname the Plugin and
Content Manager registers, pad counts against the EAGLE source for the
converted library, and pad/pin number agreement between each board symbol
and its footprint. With kicad-cli available it also asks KiCad itself to
load every library, which is what caught the KiCad 10 load failures.
"""
import argparse, math, os, re, shutil, subprocess, sys, tempfile
import xml.etree.ElementTree as ET
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


def prop(tree, key):
    for p in walk(tree, "property"):
        if len(p) > 2 and p[1].strip('"') == key:
            return p[2].strip('"')
    return None


errors, warns = [], []


def check_footprint(m, src_pkg):
    tree = parse(m.read_text(), m.name)
    if tree[0] != "footprint":
        errors.append(f"{m.name}: root is {tree[0]!r}, not 'footprint'")
    link = prop(tree, "Footprint") or ""
    if not link.startswith("PCM_"):
        errors.append(f"{m.name}: Footprint link {link!r} must use the PCM_ nickname")
    pads = list(walk(tree, "pad"))
    pkg = src_pkg.get(m.stem) if src_pkg is not None else None
    if pkg is not None:
        want = (len(pkg.findall("smd")) + len(pkg.findall("pad")) + len(pkg.findall("hole")))
        if len(pads) != want:
            errors.append(f"{m.name}: {len(pads)} pads, EAGLE has {want}")
    for pad in pads:
        size = next(walk(pad, "size"), None)
        if not size:
            errors.append(f"{m.name}: pad with no size"); continue
        w, h = float(size[1]), float(size[2])
        if not (math.isfinite(w) and math.isfinite(h)) or w <= 0 or h <= 0:
            errors.append(f"{m.name}: pad size {w}x{h}")
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
    return {p[1].strip('"') for p in pads if p[1].strip('"')}


def check_board_footprint(m, tree_numbers):
    """A module footprint needs pins, an outline and a courtyard."""
    text = m.read_text()
    tree = parse(text, m.name)
    layers = {l[1].strip('"') for l in walk(tree, "layer")}
    if not tree_numbers:
        errors.append(f"{m.name}: board module has no numbered pads")
    if "F.CrtYd" not in layers:
        errors.append(f"{m.name}: no courtyard")
    if "F.Fab" not in layers or not (list(walk(tree, "fp_line")) or list(walk(tree, "fp_arc"))):
        errors.append(f"{m.name}: no outline on F.Fab")


def check_symbols(symlib):
    tree = parse(symlib.read_text(), symlib.name)
    syms = [s for s in tree if isinstance(s, list) and s and s[0] == "symbol"]
    names = [s[1].strip('"') for s in syms]
    if len(names) != len(set(names)):
        dupes = [n for n in set(names) if names.count(n) > 1]
        errors.append(f"{symlib.name}: duplicate symbol names: {dupes[:5]}")
    total_pins, numbers_of = 0, {}
    for s in syms:
        name = s[1].strip('"')
        link = prop(s, "Footprint") or ""
        if link and not link.startswith("PCM_"):
            errors.append(f"{symlib.name}:{name}: Footprint link {link!r} must use the PCM_ nickname")
        units, allnums = {}, set()
        for sub in s:
            if isinstance(sub, list) and sub and sub[0] == "symbol":
                uname = sub[1].strip('"')
                mo = re.search(r"_(\d+)_(\d+)$", uname)
                if not mo:
                    errors.append(f"{name}: malformed sub-unit name {uname!r}"); continue
                nums = [p[1].strip('"') for p in walk(sub, "number")]
                units.setdefault(mo.group(1), []).extend(nums)
                allnums.update(nums)
                total_pins += len(nums)
        for unit, nums in units.items():
            if len(nums) != len(set(nums)):
                d = [n for n in set(nums) if nums.count(n) > 1]
                errors.append(f"{name} unit {unit}: duplicate pin numbers {d[:4]}")
        if not units:
            warns.append(f"{name}: no sub-units")
        for tok in s:
            if isinstance(tok, str) and tok not in ("symbol", "pin_names", "pin_numbers", "power",
                                                    "exclude_from_sim", "in_bom", "on_board",
                                                    "extends", "embedded_fonts", "duplicate_pin_numbers_are_jumpers"):
                if tok == name or tok == f'"{name}"':
                    continue
                if tok.startswith('"'):
                    continue
                errors.append(f"{name}: unexpected top-level token {tok!r}")
        numbers_of[name] = allnums
    return syms, total_pins, numbers_of


def kicad_cli_check(exe, pkg):
    """Ask KiCad to load every library; it is the only judge that matters."""
    if exe == "auto":
        cands = ["kicad-cli", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
                 r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"]
        exe = next((c for c in cands if shutil.which(c) or os.path.exists(c)), None)
        if not exe:
            print("kicad-cli not found; skipping the KiCad load check")
            return
    print(f"asking {exe} to load every library ...")
    with tempfile.TemporaryDirectory() as tmp:
        for pretty in sorted((pkg / "footprints").glob("*.pretty")):
            dst = Path(tmp) / pretty.name
            shutil.copytree(pretty, dst)
            r = subprocess.run([exe, "fp", "upgrade", "--force", str(dst)], capture_output=True, text=True)
            out = (r.stdout + r.stderr).strip()
            if r.returncode or "Unable" in out or "rror" in out:
                errors.append(f"kicad-cli cannot load {pretty.name}: {out[:200]}")
            else:
                print(f"  ok  {pretty.name}")
        for sym in sorted((pkg / "symbols").glob("*.kicad_sym")):
            dst = Path(tmp) / sym.name
            shutil.copy(sym, dst)
            r = subprocess.run([exe, "sym", "upgrade", "--force", str(dst)], capture_output=True, text=True)
            out = (r.stdout + r.stderr).strip()
            if r.returncode or "Unable" in out or "rror" in out:
                errors.append(f"kicad-cli cannot load {sym.name}: {out[:200]}")
            else:
                print(f"  ok  {sym.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lbr")
    ap.add_argument("out")
    ap.add_argument("--kicad-cli", default="auto", help="'auto' (default), 'none', or a path")
    a = ap.parse_args()
    out = Path(a.out)
    lib = ET.parse(a.lbr).getroot().find(".//library")
    src_pkg = {re.sub(r'[\s/\\:"<>|?*]', "_", p.get("name").strip()): p
               for p in lib.findall("packages/package")}

    fp_numbers = {}
    for pretty in sorted((out / "footprints").glob("*.pretty")):
        mods = sorted(pretty.glob("*.kicad_mod"))
        print(f"checking {pretty.name}: {len(mods)} footprints ...")
        converted = pretty.name == "Adafruit.pretty"
        for m in mods:
            try:
                nums = check_footprint(m, src_pkg if converted else None)
            except ValueError as e:
                errors.append(str(e)); continue
            fp_numbers[f"{pretty.stem}:{m.stem}"] = nums
            if not converted:
                check_board_footprint(m, nums)
    if converted_missing := [n for n in src_pkg if not (out / "footprints" / "Adafruit.pretty" / f"{n}.kicad_mod").exists()]:
        warns.append(f"{len(converted_missing)} EAGLE packages have no footprint: {converted_missing[:5]}")

    sym_numbers = {}
    for symlib in sorted((out / "symbols").glob("*.kicad_sym")):
        print(f"checking {symlib.name} ...")
        try:
            syms, total, numbers_of = check_symbols(symlib)
        except ValueError as e:
            errors.append(str(e)); continue
        print(f"  {len(syms)} top-level symbols, {total} pins")
        sym_numbers[symlib.stem] = (syms, numbers_of)

    # ---- board symbols must agree with their footprints, pad for pin
    if "Adafruit_Boards" in sym_numbers:
        for name, nums in sym_numbers["Adafruit_Boards"][1].items():
            pads = fp_numbers.get(f"Adafruit_Boards:{name}")
            if pads is None:
                errors.append(f"board symbol {name} has no footprint")
            elif pads != nums:
                errors.append(f"board {name}: symbol pins {sorted(nums)[:6]}… != footprint pads {sorted(pads)[:6]}…")

    # ---- targeted fidelity check: MAX1811/SO08 pin-name -> pad-number mapping
    if "Adafruit" in sym_numbers:
        print("\nfidelity spot-check: MAX1811 (pin name -> pad number)")
        ds = next(d for d in lib.findall("devicesets/deviceset") if d.get("name") == "MAX1811")
        want = {c.get("pin"): c.get("pad") for c in ds.find("devices/device").findall("connects/connect")}
        sym = next(s for s in sym_numbers["Adafruit"][0] if s[1].strip('"').startswith("MAX1811"))
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

    if a.kicad_cli != "none":
        print()
        kicad_cli_check(a.kicad_cli, out)

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
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
