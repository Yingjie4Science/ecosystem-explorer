#!/bin/zsh
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"
echo "Urban Ecosystem Explorer is available at http://127.0.0.1:4173/"
echo "Keep this window open while using the dashboard. Press Control-C to stop."
python3 -m http.server 4173 --bind 127.0.0.1 --directory dist
