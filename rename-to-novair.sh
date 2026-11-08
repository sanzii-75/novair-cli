#!/usr/bin/env bash
# rename-to-novair.sh (v2) — one-shot rename nexa -> novair (v0.2.0 -> v0.3.0)
#
# v2 changes:
#   - RESUMABLE: safe to re-run; every step detects what is already done.
#     (v1 died silently at step 2 when `git grep` found no match — pipefail.)
#   - handles an UNTRACKED AGENTS.md (git grep can't see it; sed'd explicitly).
#   - verification is soft: skips pytest/ruff/banner if deps aren't installed.
#
# Usage: bash rename-to-novair.sh   (from the repo root)
set -euo pipefail

REPO_SLUG="sanzii-75/novair-cli"   # alternatives: sanzii-75/novair-code | sanzii-75/novair-harness
OLD_VER="0.2.0"
NEW_VER="0.3.0"

if [ ! -d nexa ] && [ ! -d novair ]; then
    echo "ERROR: ./nexa or ./novair not found — run this from the repo root."; exit 1
fi

echo "==> 1/7 rename files & dirs (skipped if already done)"
if [ -d nexa ]; then git mv nexa novair; fi
if [ -f nexa-env.example.sh ]; then git mv nexa-env.example.sh novair-env.example.sh; fi

echo "==> 2/7 repo URLs"
git grep -Il 'sanzii-75/nexa'           | xargs -r sed -i "s#sanzii-75/nexa#$REPO_SLUG#g" || true
git grep -Il 'github.com/nexa-cli/nexa' | xargs -r sed -i "s#github.com/nexa-cli/nexa#github.com/$REPO_SLUG#g" || true

echo "==> 3/7 mechanical rename (code, docs, tests, env vars)"
git grep -Il -i nexa | xargs -r sed -i \
  -e 's/\bNEXA_/NOVAIR_/g' \
  -e 's/\bNexa\b/Novair/g' \
  -e 's/\bnexa\b/novair/g' \
  -e 's/\bNEXA\b/NOVAIR/g' || true
# AGENTS.md may be untracked (git grep can't see it) — rename it explicitly too:
if [ -f AGENTS.md ]; then
  sed -i -e 's/\bNEXA_/NOVAIR_/g' -e 's/\bNexa\b/Novair/g' \
         -e 's/\bnexa\b/novair/g' -e 's/\bNEXA\b/NOVAIR/g' AGENTS.md
fi

echo "==> 4/7 banner letters N-O-V-A-I-R (skipped if already patched)"
python3 - <<'PY'
from pathlib import Path

p = Path("novair/ui/app.py")
src = p.read_text(encoding="utf-8")

if '"O":' in src and 'BANNER_LETTERS["O"]' in src:
    print("banner: already patched, skipping")
else:
    old_letters = '''    "E": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
    "X": ["██╗  ██╗", "╚██╗██╔╝", " ╚███╔╝ ", " ██╔██╗ ", "██╔╝╚██╗", "╚═╝  ╚═╝"],'''
    new_letters = '''    "O": [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "V": ["██╗   ██╗", "██║   ██║", "██║   ██║", "╚██╗ ██╔╝", " ╚████╔╝ ", "  ╚═══╝  "],
    "I": ["██╗", "██║", "██║", "██║", "██║", "╚═╝"],
    "R": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],'''
    old_zip = '''    "".join(parts) for parts in zip(_BANNER_LETTERS["N"], _BANNER_LETTERS["E"],
                                    _BANNER_LETTERS["X"], _BANNER_LETTERS["A"])'''
    new_zip = '''    "".join(parts) for parts in zip(_BANNER_LETTERS["N"], _BANNER_LETTERS["O"],
                                    _BANNER_LETTERS["V"], _BANNER_LETTERS["A"],
                                    _BANNER_LETTERS["I"], _BANNER_LETTERS["R"])'''
    assert old_letters in src, "banner letter block not found in novair/ui/app.py — patch manually"
    assert old_zip in src,     "banner zip block not found in novair/ui/app.py — patch manually"
    p.write_text(src.replace(old_letters, new_letters).replace(old_zip, new_zip),
                 encoding="utf-8")
    print("banner: OK -> N O V A I R")
PY

echo "==> 5/7 version bump $OLD_VER -> $NEW_VER"
sed -i "s/^version = \"$OLD_VER\"/version = \"$NEW_VER\"/" pyproject.toml
sed -i "s/^pkgver=.*/pkgver=$NEW_VER/" packaging/PKGBUILD
sed -i "s/__version__ = \"$OLD_VER\"/__version__ = \"$NEW_VER\"/" novair/__init__.py

echo "==> 5b/7 sneak-case leftovers + PKGBUILD + hygiene"
sed -i 's/nexa providers/novair providers/' novair/cli.py
sed -i 's/is_nexa_api_key/is_novair_api_key/' tests/test_config.py
sed -i "s#url=\"https://github.com/<YOUR_USERNAME>/novair\"#url=\"https://github.com/$REPO_SLUG\"#" packaging/PKGBUILD
if ! grep -q '_reponame=' packaging/PKGBUILD; then
  sed -i 's/^pkgname=novair-cli$/_reponame="novair-cli"   # GitHub repo name (tarball extracts as ${_reponame}-${pkgver})\npkgname=novair-cli/' packaging/PKGBUILD
fi
sed -i 's/cd "novair-$pkgver"/cd "${_reponame}-$pkgver"/' packaging/PKGBUILD
sed -i "s/v$OLD_VER/v$NEW_VER/g" packaging/PKGBUILD
chmod -x novair/*.py novair/ui/*.py tests/*.py examples/*.py 2>/dev/null || true
chmod +x install.sh

echo "==> 6/7 AGENTS.md: keep the historical warning email + note the rename"
if [ -f AGENTS.md ]; then
  sed -i 's/novair <novair@users\.noreply\.github\.com>/nexa <nexa@users.noreply.github.com>/' AGENTS.md
  sed -i 's/username `novair`/username `nexa`/' AGENTS.md
  sed -i 's/## Where things stand (v0\.2\.0)/## Where things stand (v0.3.0)/' AGENTS.md
  python3 - <<'PY'
from pathlib import Path
p = Path("AGENTS.md")
src = p.read_text(encoding="utf-8")
note = ("**v0.3.0 rename note:** this project was previously named **nexa**. Everything is now "
        "`novair` (command, package, env prefix `NOVAIR_`, data dir `~/.local/share/novair`). "
        "Old local data dirs can be migrated with `mv ~/.local/share/nexa ~/.local/share/novair`.\n\n")
if "v0.3.0 rename note" not in src:
    src = src.replace("Shipped: ", note + "Shipped: ", 1)
    p.write_text(src, encoding="utf-8")
    print("AGENTS.md: rename note added")
else:
    print("AGENTS.md: note already present")
PY
fi

echo "==> 7/7 verify (soft — skipped when deps are missing)"
if python3 -c 'import rich, httpx' 2>/dev/null; then
  python3 -m pytest -q 2>/dev/null || echo "⚠ pytest gagal/terpasang sebagian — cek manual: pip install pytest && python -m pytest -q"
  command -v ruff >/dev/null 2>&1 && ruff check novair tests || echo "ℹ ruff not installed — skip lint (pip install ruff)"
  python3 - <<'PY' 2>/dev/null || echo "ℹ banner preview skipped (import failed)"
from novair.ui.app import BANNER_ROWS
print("banner width:", max(len(r) for r in BANNER_ROWS), "cols")
print("\n".join(BANNER_ROWS))
PY
else
  echo "⚠ rich/httpx tidak ada di python system — verify dilewati."
  echo "  Verify manual nanti: pip install rich httpx pytest ruff && python -m pytest -q && ruff check novair tests"
fi

echo
echo "Remaining 'nexa' mentions in TRACKED files (expect ONLY AGENTS.md historical lines):"
git grep -n -i nexa || true
if [ -f AGENTS.md ]; then
  echo "AGENTS.md historical lines kept on purpose (warning email + rename note)."
fi

cat <<'EOF'

=== Manual follow-ups (do these yourself) ===
  git remote set-url origin git@github.com:sanzii-75/novair-cli.git
  # GitHub: Settings -> General -> rename repo to novair-cli
  git add -A && git commit -m 'feat!: rename project nexa -> novair, release v0.3.0'
  git tag -a v0.3.0 -m 'novair v0.3.0'
  git push origin main --tags
  ./install.sh        # reinstall as `novair`
EOF
