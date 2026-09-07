#!/bin/sh
# Package the skill for upload to claude.ai.
# The repo root IS the skill (SKILL.md at top level, per the Agent Skills
# spec). The uploaded archive still needs the skill folder at ITS root, so
# this stages SKILL.md/references/scripts into a folder named after `name:`
# before zipping — the folder name must match `name:` in SKILL.md.
set -e
cd "$(dirname "$0")"
NAME=$(sed -n 's/^name: //p' SKILL.md)
VER=$(sed -n 's/^version: //p' SKILL.md)
[ "$NAME" = "discovery-driven-dev" ] || { echo "repo/name mismatch: $NAME" >&2; exit 1; }
mkdir -p dist
rm -rf "dist/stage" "dist/$NAME.zip" "dist/$NAME.skill"
mkdir -p "dist/stage/$NAME"
cp SKILL.md "dist/stage/$NAME/"
cp -R references "dist/stage/$NAME/"
cp -R scripts "dist/stage/$NAME/"
find "dist/stage/$NAME" -name '__pycache__' -type d -exec rm -rf {} +
find "dist/stage/$NAME" -name '*.pyc' -delete
find "dist/stage/$NAME" -name '.DS_Store' -delete
(cd dist/stage && zip -qr "../$NAME.zip" "$NAME")
rm -rf dist/stage
cp "dist/$NAME.zip" "dist/$NAME.skill"
echo "dist/$NAME.zip  (v$VER)"
echo "dist/$NAME.skill  — identical; use whichever the upload dialog accepts"
