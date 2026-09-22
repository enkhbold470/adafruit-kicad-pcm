#!/usr/bin/env python3
"""Build a KiCad PCM add-on zip plus a self-hosted PCM repository feed.

Outputs (all in dist/):
  <slug>-<version>.zip  the add-on, metadata.json at the zip root
  packages.json         the package list, with download_* fields filled in
  repository.json       the URL users paste into Manage Repositories
  resources.zip         per-identifier icons, served alongside the feed
"""
import hashlib, json, os, re, sys, time, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG, DIST = ROOT / "package", ROOT / "dist"
SKIP = {".DS_Store", ".gitkeep", "Thumbs.db"}

TYPES = {"library", "plugin", "colortheme"}
STATUSES = {"stable", "testing", "development", "deprecated", "invalid"}
IDENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# Where the released zip will live. Override either piece from the environment.
OWNER = os.environ.get("GH_OWNER", "CHANGE_ME")
REPO = os.environ.get("GH_REPO", "adafruit-kicad-pcm")
PAGES = os.environ.get("FEED_BASE", f"https://{OWNER}.github.io/{REPO}")


def fail(msg):
    print(f"  ERROR  {msg}")
    fail.n += 1
fail.n = 0


def warn(msg):
    print(f"  WARN   {msg}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def payload(root):
    """Files that belong in the package, sorted for reproducible archives."""
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name not in SKIP:
            out.append(p)
    return out


def validate(meta):
    print("Validating metadata.json against the PCM v1 contract")
    for key in ("$schema", "name", "description", "description_full",
                "identifier", "type", "license", "versions"):
        if not meta.get(key):
            fail(f"missing required key: {key}")

    if len(meta.get("description", "")) > 150:
        warn(f"description is {len(meta['description'])} chars; PCM shows ~150")
    if meta.get("type") not in TYPES:
        fail(f"type must be one of {sorted(TYPES)}")
    ident = meta.get("identifier", "")
    if not IDENT_RE.match(ident):
        fail(f"identifier {ident!r} must be lowercase reverse-DNS "
             "([a-z0-9._-], e.g. com.github.you.thing)")
    for holder in ("author", "maintainer"):
        name = (meta.get(holder) or {}).get("name", "")
        if "CHANGE" in name.upper():
            warn(f"{holder}.name is still a placeholder: {name!r}")

    versions = meta.get("versions") or []
    for v in versions:
        for key in ("version", "status", "kicad_version"):
            if not v.get(key):
                fail(f"versions[] entry missing {key}")
        if v.get("status") not in STATUSES:
            fail(f"status {v.get('status')!r} must be one of {sorted(STATUSES)}")
        for key in ("download_url", "download_sha256", "download_size", "install_size"):
            if key in v:
                fail(f"remove {key} from package/metadata.json — it belongs "
                     "only in the repository feed, and this script computes it")
    if meta.get("type") == "library":
        if not any((PKG / d).is_dir() and payload(PKG / d)
                   for d in ("symbols", "footprints", "3dmodels")):
            warn("no assets under symbols/, footprints/ or 3dmodels/ — "
                 "KiCad will install this package but register nothing")
    return versions[0] if versions else {}


def build_zip(meta, version):
    slug = f"{meta['identifier'].rsplit('.', 1)[-1]}-{version['version']}"
    out = DIST / f"{slug}.zip"
    files = payload(PKG)
    if not (PKG / "metadata.json").exists():
        fail("package/metadata.json not found")
    install_size = sum(f.stat().st_size for f in files)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            # arcname is relative to package/ so metadata.json lands at the
            # zip root — KiCad rejects the archive if it sits in a subfolder.
            info = zipfile.ZipInfo(str(f.relative_to(PKG)), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, f.read_bytes())
    names = zipfile.ZipFile(out).namelist()
    if "metadata.json" not in names:
        fail("metadata.json is not at the zip root")
    print(f"\nPackaged {len(files)} files -> dist/{out.name}")
    return out, install_size


def build_resources(meta):
    icon = PKG / "resources" / "icon.png"
    if not icon.exists():
        warn("package/resources/icon.png missing; PCM will show a blank tile")
        return None
    out = DIST / "resources.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo(f"{meta['identifier']}/icon.png", (1980, 1, 1, 0, 0, 0))
        z.writestr(info, icon.read_bytes())
    return out


def stamp(path):
    return {"sha256": sha256(path), "update_timestamp": int(NOW),
            "update_time_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(NOW))}


NOW = time.time()


def older_versions(meta):
    """Keep earlier releases installable: their download_* fields are only
    known from the feed we published last time, so carry them over from
    docs/packages.json rather than recomputing (the old zip is untouched)."""
    prior = {}
    feed = ROOT / "docs" / "packages.json"
    if feed.exists():
        for p in json.loads(feed.read_text()).get("packages", []):
            if p.get("identifier") == meta.get("identifier"):
                prior = {v["version"]: v for v in p.get("versions", []) if "download_sha256" in v}
    kept = []
    for v in meta["versions"][1:]:
        if v["version"] in prior:
            kept.append(prior[v["version"]])
        else:
            warn(f"version {v['version']} has no published download info; dropped from the feed")
    return kept


def main():
    DIST.mkdir(exist_ok=True)
    # Clear stale zips: the archive name derives from the identifier and
    # version, so editing either leaves an orphan behind that is easy to
    # publish by mistake.
    for old in DIST.glob("*.zip"):
        old.unlink()
    meta = json.loads((PKG / "metadata.json").read_text())
    version = validate(meta)
    if fail.n:
        print(f"\n{fail.n} error(s); nothing built.")
        return 1

    zip_path, install_size = build_zip(meta, version)
    tag = os.environ.get("TAG", f"v{version['version']}")
    url = os.environ.get(
        "DOWNLOAD_URL",
        f"https://github.com/{OWNER}/{REPO}/releases/download/{tag}/{zip_path.name}")

    entry = dict(version)
    entry.update(download_url=url, download_sha256=sha256(zip_path),
                 download_size=zip_path.stat().st_size, install_size=install_size)
    pkg = {k: v for k, v in meta.items() if k != "$schema"}
    pkg["versions"] = [entry] + older_versions(meta)

    packages = DIST / "packages.json"
    packages.write_text(json.dumps(
        {"$schema": "https://go.kicad.org/pcm/schemas/v1", "packages": [pkg]},
        indent=2) + "\n")

    # repository.json points AT packages.json — it never inlines the package
    # list. KiCad reads repository.json, then fetches the URLs it names.
    repo = {"$schema": "https://go.kicad.org/pcm/schemas/v1",
            "name": "Adafruit KiCad Library (community)",
            "maintainer": meta.get("maintainer", meta.get("author")),
            "packages": {"url": f"{PAGES}/packages.json", **stamp(packages)}}
    res = build_resources(meta)
    if res:
        repo["resources"] = {"url": f"{PAGES}/resources.zip", **stamp(res)}
    (DIST / "repository.json").write_text(json.dumps(repo, indent=2) + "\n")

    # Mirror the feed into docs/ so GitHub Pages can serve it from main.
    feed = ROOT / "docs"
    feed.mkdir(exist_ok=True)
    for f in ("packages.json", "repository.json", "resources.zip"):
        (feed / f).write_bytes((DIST / f).read_bytes())
    (feed / ".nojekyll").write_text("")

    print(f"  download_sha256  {entry['download_sha256']}")
    print(f"  download_size    {entry['download_size']:,} bytes")
    print(f"  install_size     {entry['install_size']:,} bytes")
    print(f"  download_url     {url}")
    print(f"\nFeed written. Add this URL in PCM -> Manage Repositories:\n"
          f"  {PAGES}/repository.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
