#!/usr/bin/env python3
"""Build the Adafruit_Boards module library from the boards manifest.

  python3 tools/build_boards.py            # fetch (cached), convert, write package/
  python3 tools/build_boards.py --table    # also print a Markdown table for the README

tools/boards.json pins every source .brd to an exact upstream commit and
sha256, so the output is reproducible without vendoring ~20 MB of EAGLE
files. Sources are cached under tools/boards-cache/ (gitignored).
"""
import argparse, hashlib, json, sys, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brd2module import SYM_HEADER, convert  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tools" / "boards.json"
CACHE = ROOT / "tools" / "boards-cache"
PKG = ROOT / "package"
PRETTY, NICK = "Adafruit_Boards", "PCM_Adafruit_Boards"


def fetch(entry):
    dest = CACHE / entry["repo"].split("/")[-1] / entry["commit"][:12] / Path(entry["path"]).name
    if not dest.exists():
        url = (f"https://raw.githubusercontent.com/{entry['repo']}/{entry['commit']}/"
               + urllib.parse.quote(entry["path"]))
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"  fetching {entry['repo'].split('/')[-1]}/{Path(entry['path']).name}")
        urllib.request.urlretrieve(url, dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        raise SystemExit(f"{dest}: sha256 {digest[:12]}… does not match the manifest "
                         f"({entry['sha256'][:12]}…); refusing to build from it")
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", action="store_true", help="print a Markdown table of the boards")
    a = ap.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    fp_dir = PKG / "footprints" / f"{PRETTY}.pretty"
    fp_dir.mkdir(parents=True, exist_ok=True)
    for stale in fp_dir.glob("*.kicad_mod"):
        stale.unlink()
    symbols, rows, failed = [], [], []
    for e in manifest["boards"]:
        brd = fetch(e)
        source = f"{e['repo']}@{e['commit'][:7]} \"{e['path']}\""
        try:
            r = convert(str(brd), e["name"], e["title"], e.get("pid"), e.get("url"),
                        source, e.get("keywords", "adafruit board module"), NICK)
        except SystemExit as exc:
            print(f"  {e['name']:48} SKIPPED: {exc}")
            failed.append(e["name"])
            continue
        (fp_dir / f"{e['name']}.kicad_mod").write_text(r["footprint"])
        symbols.append(r["symbol"])
        rep = r["report"]
        pins = rep["pins"]
        named = sum(1 for p in pins if p["name"])
        skipped = rep["stats"].get("skipped packages", [])
        rows.append((e["name"], e.get("pid"), rep["size_mm"], len(pins), named, skipped))
        print(f"  {e['name']:48} {rep['size_mm'][0]:6.2f} x {rep['size_mm'][1]:6.2f} mm  "
              f"{len(pins):3} pins ({named} named)" + (f"  skipped: {skipped}" if skipped else ""))
    (PKG / "symbols").mkdir(exist_ok=True)
    (PKG / "symbols" / f"{PRETTY}.kicad_sym").write_text(SYM_HEADER + "\n".join(symbols) + "\n)\n")
    print(f"\n{len(rows)} boards -> footprints/{PRETTY}.pretty/ and symbols/{PRETTY}.kicad_sym")
    if failed:
        print(f"{len(failed)} board(s) produced nothing: {failed}")
    if a.table:
        print("\n| Footprint | Product | Size (mm) | Pins |\n|---|---|---|---|")
        for name, pid, (w, h), n, named, _ in rows:
            link = f"[{pid}](https://www.adafruit.com/product/{pid})" if pid else "—"
            print(f"| `{name}` | {link} | {w:g} × {h:g} | {n} |")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
