# Adafruit KiCad Library — PCM add-on

Unofficial KiCad packaging of Adafruit's parts, in two libraries:

- **Adafruit** — 666 symbols and 643 footprints, mechanically converted from
  Adafruit's EAGLE library (`adafruit/Adafruit-Eagle-Library`).
- **Adafruit_Boards** — 22 *module* footprints and symbols for Adafruit boards
  released in 2026, each generated from the EAGLE board file Adafruit
  publishes for that product. Drop a STEMMA QT breakout, the Terminal Block
  BFF or a Matrix Portal S3 onto your own PCB as one part: outline, mounting
  holes and header pins, with every pin carrying its net name.

Adafruit publishes no native KiCad library and no Plugin and Content Manager
feed; all their sources are EAGLE format.

## Install

**From the repository feed** — PCM → Manage Repositories → `+`, then add:

    https://enkhbold470.github.io/adafruit-kicad-pcm/repository.json

The package then appears under Libraries. Installing registers the libraries
as `PCM_Adafruit` and `PCM_Adafruit_Boards` in your global symbol and
footprint tables (the PCM prefixes every library it installs with `PCM_`; the
symbols' footprint links already use those names).

**From a file** — download the zip from
[Releases](https://github.com/enkhbold470/adafruit-kicad-pcm/releases) and use
PCM → Install from File.

## Board modules (Adafruit_Boards)

Each entry is one Adafruit product as a placeable footprint plus a matching
schematic symbol. What is in the footprint:

- the board outline (EAGLE Dimension layer) on `F.Fab` and `F.SilkS`, and a
  courtyard 0.25 mm outside its bounding box; the anchor is the outline's
  centre
- every through-hole pad of the board's header / terminal-block packages,
  numbered **1..N in EAGLE element order, then pad order** (a single 1×6
  header is simply 1–6). The net name from the board file is stored as the
  pad's *pin function*, so it shows on hover in the PCB editor and becomes
  the pin name in the symbol
- plated mounting holes as un-numbered pads, non-plated holes as NPTH, and
  the tDocu outline of connectors (JST, USB) on `F.Fab`

SMD parts, traces and silkscreen art are the module's own business and are
left out. The symbol is a box with power pins on top, ground at the bottom
and signals down the sides; power pins are `power_in`, everything else
`passive`.

| Footprint / symbol | Product | Board (mm) | Pins | STEP model |
|---|---|---|---|---|
| `Adafruit_TCS3448_Light_Color_Sensor` | [6525](https://www.adafruit.com/product/6525) | 25.4 × 17.78 | 6 | [yes](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/6525%20TCS3448%20Light%20Color%20Sensor) |
| `Adafruit_TSL2585_UVA_Light_Sensor` | [6524](https://www.adafruit.com/product/6524) | 25.4 × 17.78 | 6 | [yes](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/6524%20TSL2585%20UVA%20Ambient%20Light%20Sensor) |
| `Adafruit_TMF8801_ToF_Distance_Sensor` | [6522](https://www.adafruit.com/product/6522) | 25.4 × 17.78 | 8 | [yes](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/6522%20TMF8801%20ToF%20Sensor) |
| `Adafruit_GP8403_I2C_DAC` | [6516](https://www.adafruit.com/product/6516) | 25.4 × 22.86 | 10 | [yes](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/6516%20GP8403%20I2C%20DAC) |
| `Adafruit_SCD43_CO2_Sensor` | [6512](https://www.adafruit.com/product/6512) | 25.4 × 22.86 | 5 | — |
| `Adafruit_SCD41_CO2_Sensor` | [5190](https://www.adafruit.com/product/5190) | 25.4 × 22.86 | 5 | — |
| `Adafruit_TMF8806_ToF_Distance_Sensor` | [6501](https://www.adafruit.com/product/6501) | 25.4 × 17.78 | 8 | [yes](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/6501%20TMF8806%20ToF%20Sensor) |
| `Adafruit_MAX44009_Lux_Sensor` | [6498](https://www.adafruit.com/product/6498) | 25.4 × 17.78 | 6 | [yes](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/6498%20MAX44009%20Light%20Sensor) |
| `Adafruit_Terminal_Block_BFF` | [6495](https://www.adafruit.com/product/6495) | 43.18 × 30.48 | 14 | [yes](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/6495%20Terminal%20Block%20BFF) |
| `Adafruit_ADS7128_ADC_GPIO_Expander` | [6494](https://www.adafruit.com/product/6494) | 30.48 × 17.78 | 16 | [yes](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/6494%20ADS7128%20ADC%20GPIO%20Expander) |
| `Adafruit_VCNL4030_Proximity_Lux_Sensor` | [6491](https://www.adafruit.com/product/6491) | 25.4 × 17.78 | 6 | — |
| `Adafruit_TMAG5273A2_Hall_Magnetometer` | [6490](https://www.adafruit.com/product/6490) | 25.4 × 17.78 | 6 | — |
| `Adafruit_TMAG5273A1_Hall_Magnetometer` | [6489](https://www.adafruit.com/product/6489) | 25.4 × 17.78 | 6 | — |
| `Adafruit_TMP119_Temperature_Sensor` | [6482](https://www.adafruit.com/product/6482) | 25.4 × 17.78 | 6 | — |
| `Adafruit_TCS3430_Tri-Stimulus_Color_Sensor` | [6479](https://www.adafruit.com/product/6479) | 25.4 × 17.78 | 6 | — |
| `Adafruit_STCC4_SHT41_CO2_Sensor` | [6478](https://www.adafruit.com/product/6478) | 25.4 × 17.78 | 6 | — |
| `Adafruit_AS7343_Light_Color_Sensor` | [6477](https://www.adafruit.com/product/6477) | 25.4 × 17.78 | 6 | — |
| `Adafruit_AS7331_UV_Sensor` | [6476](https://www.adafruit.com/product/6476) | 25.4 × 17.78 | 6 | — |
| `Adafruit_MatrixPortal_S3` | [5778](https://www.adafruit.com/product/5778) | 63.5 × 44.45 | 11 | [yes](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/5778%20Matrix%20Portal%20S3) |
| `Adafruit_APDS9999_Proximity_Light_Color_Sensor` | [6461](https://www.adafruit.com/product/6461) | 25.4 × 17.78 | 6 | — |
| `Adafruit_SGP41_Gas_Sensor` | [6455](https://www.adafruit.com/product/6455) | 25.4 × 17.78 | 5 | — |
| `Adafruit_ADS122C04_24-Bit_ADC` | [6432](https://www.adafruit.com/product/6432) | 25.4 × 17.78 | 12 | — |

*STEP model* links to Adafruit's [Adafruit_CAD_Parts](https://github.com/adafruit/Adafruit_CAD_Parts)
(MIT) where a model of the whole product exists. They are not bundled here —
at 1–8 MB each they would multiply the package size, and their origin does
not coincide with the footprint anchor, so attach one via the footprint's
3D-model settings and align it by eye.

The product IDs above are the ones the scan of adafruit.com's new-products
feed turned up between March and September 2026. Of the 37 boards released in
that window, 22 have published EAGLE sources (all Adafruit-designed ones; the
Pimoroni, Raspberry Pi and ScoutMakes products do not), so those are the 22
here. The MatrixPortal S3 file is the original 5778 design; 6475 is the same
board with a u.FL antenna connector.

## Read this before you fabricate

The conversion is automated and has **not** been reviewed part by part. It is
published with PCM status `testing` for that reason. Verified mechanically:

- all 4,665 pad positions and sizes in **Adafruit** match the EAGLE source
  exactly; all 643 footprints have the same pad count as their EAGLE package
- all 1,088 converted arcs are geometrically consistent
- symbol pin-name → pad-number mapping comes from EAGLE `<connect>` elements
- every **Adafruit_Boards** symbol's pin numbers equal its footprint's pad
  numbers, and every board has an outline, a courtyard and at least one pin
- **KiCad itself loads every library** (`kicad-cli fp upgrade` / `sym upgrade`
  on KiCad 10.0.5). Version 1.0.0 failed this for 28 multi-unit symbols and one
  footprint — see the changelog below.

What that does *not* cover: whether Adafruit's original land patterns suit your
process, silkscreen legibility after conversion, courtyard correctness, or 3D
models (none are included). For the board modules, the header pad drills and
annuli are whatever Adafruit used on the board itself; check them against
the header you intend to solder. Check any footprint against the manufacturer
drawing before committing a board to fab.

Known conversion limitations:

- 952 octagon pads became circles — KiCad has no octagon pad primitive
- copper keepout shapes on EAGLE layers 41/42/43 (63 items) were dropped
- 3 symbol pins had no `<connect>` entry; their pin number falls back to the
  pin name
- EAGLE pins with no explicit direction map to `passive` to keep ERC quiet
- board modules include the through-hole anchors of on-board USB-C shells and
  the pegs of JST / box headers as un-numbered holes, because they physically
  protrude through the module; SMD-only connectors leave no trace

## Rebuilding

    python3 tools/eagle2kicad.py tools/adafruit.lbr package/ --prefix Adafruit
    python3 tools/build_boards.py --table
    python3 tools/verify.py tools/adafruit.lbr package/
    GH_OWNER=enkhbold470 GH_REPO=adafruit-kicad-pcm ./build.sh

`build_boards.py` reads `tools/boards.json`, which pins every board file to an
upstream commit and sha256, downloads it into `tools/boards-cache/` (gitignored)
and refuses to build from a file whose hash has drifted. To add a board: find
its `adafruit/Adafruit-…-PCB` repo, add an entry with the `.brd` path, commit
and sha256, a name, product ID and keywords, then rebuild. One board can also
be converted directly:

    python3 tools/brd2module.py board.brd out/ --name Adafruit_Foo --pid 1234

`verify.py` runs the structural checks and, when it can find `kicad-cli`,
asks KiCad to load every library. `build.sh` validates `package/metadata.json`
against the PCM v1 contract, writes `dist/<slug>-<version>.zip` with
`metadata.json` at the zip root (KiCad rejects it in a subfolder), and renders
the feed into both `dist/` and `docs/` with real sha256, `download_size` and
`install_size`. Never hand-edit those three fields — a stale sha256 makes PCM
refuse the download.

Overrides: `TAG`, `DOWNLOAD_URL`, `FEED_BASE`.

CI (`.github/workflows/build.yml`) regenerates both libraries on every push,
fails if the committed `package/` differs from what the tools produce, runs
`verify.py`, builds the zip, and loads every library with `kicad-cli`.

## Layout

    package/                    contents become the zip root
      metadata.json             the PCM manifest
      symbols/Adafruit.kicad_sym
      symbols/Adafruit_Boards.kicad_sym
      footprints/Adafruit.pretty/
      footprints/Adafruit_Boards.pretty/
      resources/icon.png        64x64, shown on the PCM tile
    tools/eagle2kicad.py        EAGLE .lbr -> KiCad 8 symbols + footprints
    tools/brd2module.py         EAGLE .brd -> one module footprint + symbol
    tools/build_boards.py       runs brd2module over tools/boards.json
    tools/boards.json           pinned board sources (repo, path, commit, sha256)
    tools/verify.py             structural + fidelity + KiCad load check
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

Prepend the new version to `versions[]` in `package/metadata.json`, rebuild,
attach the new zip to a release tagged `v<version>`, and commit the
regenerated `docs/`. Push `docs/` only after the release asset exists, since
the feed points at it. Older versions listed in `versions[]` stay in the feed
with the download details carried over from the previously published
`docs/packages.json`, as long as their release assets remain in place. The
feed's sha256 must come from the very zip you upload: zip bytes can differ
between machines, so build and upload from the same checkout.

## Changelog

**1.1.1**

- Generated output is now byte-identical across platforms: the converters
  fold negative zero (`-0.0000`, which libm noise or an EAGLE `0` mirrored in
  Y can produce) to `0.0000`. Library content is unchanged; this only makes
  CI's "committed output matches the tools" check reproducible on Linux.

**1.1.0**

- New `Adafruit_Boards` library: 22 module footprints and symbols for the
  2026 boards listed above, with `brd2module.py`, a pinned manifest and a
  build script to regenerate or extend them.
- Fixed: 28 multi-unit symbols (74x125/245, 4093, quad op-amps, DPDT, FPC
  connectors, TLC5947/59711 ...) did not load in KiCad — the converter wrote a
  `unit_name_hidden` token that is not part of the format.
- Fixed: `TFT_CTP28` did not load — a raw newline inside a quoted string.
- Fixed: every symbol's footprint link pointed at `Adafruit:…`, which does not
  resolve after a PCM install; they now use `PCM_Adafruit:…`.
- `verify.py` now checks every library, the PCM link names, symbol/footprint
  pin agreement for the boards, and loads everything with `kicad-cli`.
- The feed keeps older versions installable; CI added.

**1.0.0** — initial conversion of the EAGLE library.

## License and attribution

The library content is © Adafruit Industries and is redistributed under
[CC-BY-SA-4.0](https://creativecommons.org/licenses/by-sa/4.0/) — see
[NOTICE](NOTICE) for the provenance of each source, the required attribution
and a statement of the modifications made. The conversion and packaging
scripts in `tools/` are MIT-licensed.

This project is not affiliated with or endorsed by Adafruit Industries.
