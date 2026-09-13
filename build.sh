#!/usr/bin/env bash
# Build the add-on zip and the PCM feed.
#   GH_OWNER=you GH_REPO=adafruit-kicad-pcm ./build.sh
set -euo pipefail
exec python3 "$(dirname "${BASH_SOURCE[0]}")/tools/build.py" "$@"
