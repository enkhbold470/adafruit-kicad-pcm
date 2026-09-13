# Adafruit KiCad Library — PCM add-on

Unofficial KiCad packaging of Adafruit's parts library: **666 symbols** and
**643 footprints**, mechanically converted from Adafruit's EAGLE library.
Adafruit publishes no native KiCad library and no Plugin and Content Manager
feed; their parts live in EAGLE format at `adafruit/Adafruit-Eagle-Library`.

## Install

**From the repository feed** — PCM → Manage Repositories → `+`, then add:

    https://enkhbold470.github.io/adafruit-kicad-pcm/repository.json

The package then appears under Libraries. Installing registers
`Adafruit.kicad_sym` and `Adafruit.pretty` in your library tables automatically.

**From a file** — download the zip from
[Releases](https://github.com/enkhbold470/adafruit-kicad-pcm/releases) and use
PCM → Install from File.

## Read this before you fabricate

The conversion is automated and has **not** been reviewed part by part. It is
published with PCM status `testing` for that reason. Verified mechanically:

- all 4,665 pad positions and sizes match the EAGLE source exactly
- all 643 footprints have the same pad count as their EAGLE package
- all 1,088 converted arcs are geometrically consistent
- symbol pin-name → pad-number mapping comes from EAGLE `<connect>` elements

What that does *not* cover: whether Adafruit's original land patterns suit your
process, silkscreen legibility after conversion, courtyard correctness, or 3D
models (none are included — EAGLE libraries do not carry them). Check any
footprint against the manufacturer drawing before committing a board to fab.

Known conversion limitations:

- 952 octagon pads became circles — KiCad has no octagon pad primitive
- copper keepout shapes on EAGLE layers 41/42/43 (63 items) were dropped
- 3 symbol pins had no `<connect>` entry; their pin number falls back to the
  pin name
- EAGLE pins with no explicit direction map to `passive` to keep ERC quiet

## Rebuilding

    python3 tools/eagle2kicad.py tools/adafruit.lbr package/ --prefix Adafruit
    python3 tools/verify.py tools/adafruit.lbr package/
    GH_OWNER=enkhbold470 GH_REPO=adafruit-kicad-pcm ./build.sh

`build.sh` validates `package/metadata.json` against the PCM v1 contract, writes
`dist/<slug>-<version>.zip` with `metadata.json` at the zip root (KiCad rejects
it in a subfolder), and renders the feed into both `dist/` and `docs/` with real
sha256, `download_size` and `install_size`. Never hand-edit those three fields —
a stale sha256 makes PCM refuse the download.

Overrides: `TAG`, `DOWNLOAD_URL`, `FEED_BASE`.

## Layout

    package/                    contents become the zip root
      metadata.json             the PCM manifest
      symbols/Adafruit.kicad_sym
      footprints/Adafruit.pretty/
      resources/icon.png        64x64, shown on the PCM tile
    tools/eagle2kicad.py        EAGLE .lbr -> KiCad 8
    tools/verify.py             structural + fidelity check
    tools/build.py              validate, zip, render the feed
    tools/adafruit.lbr          vendored source, for reproducibility
    docs/                       the feed, served by GitHub Pages
    dist/                       build output (gitignored)

### How the feed is shaped

`repository.json` is an index, not a package list: it holds `name`,
`maintainer`, and pointers (`url` + `sha256` + timestamps) to `packages.json`
and `resources.zip`. The package array, with each version's `download_*`
fields, lives in `packages.json`. Inlining that array into `repository.json`
does not work — KiCad expects an object with a `url` there.

## Releasing a new version

Bump `versions[0].version` in `package/metadata.json`, rebuild, then attach the
new zip to a release tagged `v<version>` and commit the regenerated `docs/`.
To keep older versions installable, append to `versions[]` instead of replacing,
and leave the old release assets in place.

## License and attribution

The library content is © Adafruit Industries, licensed
[CC-BY-SA-4.0](https://creativecommons.org/licenses/by-sa/4.0/), and is
redistributed here under the same terms — see [NOTICE](NOTICE) for the required
attribution and a statement of the modifications made. The conversion and
packaging scripts in `tools/` are MIT-licensed.

This project is not affiliated with or endorsed by Adafruit Industries.
