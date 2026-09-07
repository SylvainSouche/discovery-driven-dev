#!/bin/sh
# Package the skill for upload to claude.ai.
# The archive must contain the skill folder at its root, and the folder name
# must match `name:` in SKILL.md.
set -e
cd "$(dirname "$0")"
NAME=$(sed -n 's/^name: //p' discovery-driven-dev/SKILL.md)
VER=$(sed -n 's/^version: //p' discovery-driven-dev/SKILL.md)
[ "$NAME" = "discovery-driven-dev" ] || { echo "folder/name mismatch: $NAME" >&2; exit 1; }
mkdir -p dist
rm -f "dist/$NAME.zip" "dist/$NAME.skill"
zip -qr "dist/$NAME.zip" discovery-driven-dev -x '*__pycache__*' '*.pyc' '.DS_Store'
cp "dist/$NAME.zip" "dist/$NAME.skill"
echo "dist/$NAME.zip  (v$VER)"
echo "dist/$NAME.skill  — identical; use whichever the upload dialog accepts"
