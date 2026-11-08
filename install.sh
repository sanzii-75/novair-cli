#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  novair installer — best on Arch Linux, works anywhere Python 3.9+ lives.
#
#  Usage (from a clone of this repo):
#      ./install.sh
#      ./install.sh --uninstall
#
#  Remote one-liner (after you push the repo, adjust the URL):
#      curl -fsSL https://raw.githubusercontent.com/<you>/novair/main/install.sh \
#        | NOVAIR_INSTALL_FROM="git+https://github.com/<you>/novair.git" bash
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP="novair"
NOVAIR_HOME="${NOVAIR_HOME:-$HOME/.local/share/novair}"
VENV_DIR="$NOVAIR_HOME/venv"
BIN_DIR="${NOVAIR_BIN_DIR:-$HOME/.local/bin}"
C_RESET='\033[0m'; C_BOLD='\033[1m'; C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_RED='\033[31m'; C_DIM='\033[2m'; C_YELLOW='\033[33m'

say()  { printf "${C_BOLD}${C_CYAN}▸${C_RESET} %s\n" "$*"; }
ok()   { printf "${C_GREEN}✔${C_RESET} %s\n" "$*"; }
die()  { printf "${C_RED}✖ %s${C_RESET}\n" "$*" >&2; exit 1; }

# ── uninstall ────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--uninstall" ]]; then
    say "removing $APP …"
    rm -rf "$VENV_DIR"
    rm -f  "$BIN_DIR/$APP"
    ok "uninstalled. session data remains in ~/.local/share/novair/sessions (delete manually if you want)"
    exit 0
fi

# ── banner ───────────────────────────────────────────────────────────────────
printf "${C_BOLD}${C_CYAN}"
cat <<'EOF'
███╗   ██╗███████╗██╗  ██╗ █████╗
████╗  ██║██╔════╝██║  ██║██╔══██╗
██╔██╗ ██║█████╗  ███████║███████║
██║╚██╗██║██╔══╝  ██╔══██║██╔══██║
██║ ╚████║███████╗██║  ██║██║  ██║
╚═╝  ╚═╝╚══════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
EOF
printf "${C_RESET}${C_DIM}   terminal AI agent · any OpenAI-compatible provider${C_RESET}\n\n"

# ── 1. python ────────────────────────────────────────────────────────────────
PY="$(command -v python3 || command -v python || true)"
if [[ -z "$PY" ]]; then
    if command -v pacman >/dev/null 2>&1; then
        say "installing python via pacman …"
        sudo pacman -S --needed --noconfirm python
        PY="$(command -v python3 || command -v python)"
    else
        die "python 3.9+ not found. Install python first (on Arch: sudo pacman -S python)."
    fi
fi
if ! "$PY" -c 'import sys; assert sys.version_info >= (3, 9)' 2>/dev/null; then
    die "python >= 3.9 required, found: $($PY -V 2>&1)"
fi
ok "python: $($PY -V 2>&1)"

# ── 2. venv ──────────────────────────────────────────────────────────────────
say "creating virtualenv at $VENV_DIR …"
mkdir -p "$NOVAIR_HOME"
if ! "$PY" -m venv "$VENV_DIR" 2>/dev/null; then
    if command -v pacman >/dev/null 2>&1; then
        say "venv module missing — installing python package via pacman …"
        sudo pacman -S --needed --noconfirm python
        "$PY" -m venv "$VENV_DIR"
    else
        die "python venv unavailable. On Debian/Ubuntu: sudo apt install python3-venv"
    fi
fi
ok "virtualenv ready"

# ── 3. deps ──────────────────────────────────────────────────────────────────
PIP="$VENV_DIR/bin/pip"
say "upgrading pip …"
"$PIP" install --quiet --upgrade pip wheel

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ -n "$SRC" && -f "$SRC/pyproject.toml" ]]; then
    say "installing $APP from $SRC …"
    "$PIP" install --quiet "$SRC"
elif [[ -n "${NOVAIR_INSTALL_FROM:-}" ]]; then
    say "installing $APP from $NOVAIR_INSTALL_FROM …"
    "$PIP" install --quiet "$NOVAIR_INSTALL_FROM"
else
    die "run this script from the novair project folder, or set NOVAIR_INSTALL_FROM=<pip url>"
fi
"$VENV_DIR/bin/$APP" --version >/dev/null 2>&1 || die "installation verification failed"
ok "$APP installed into the venv"

# ── 4. symlink on PATH ───────────────────────────────────────────────────────
mkdir -p "$BIN_DIR"
ln -sf "$VENV_DIR/bin/$APP" "$BIN_DIR/$APP"
ok "launcher: $BIN_DIR/$APP"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        printf "${C_YELLOW}⚠${C_RESET} $BIN_DIR is not on your PATH. Add it:\n"
        printf "    ${C_BOLD}echo 'export PATH=\"%s:\$PATH\"' >> ~/.bashrc  # or ~/.zshrc${C_RESET}\n\n" "$BIN_DIR"
        ;;
esac

# ── done ─────────────────────────────────────────────────────────────────────
printf "${C_GREEN}${C_BOLD}"
cat <<'EOF'
┌─────────────────────────────────────────────────────────────┐
│  ✔ novair is ready                                            │
└─────────────────────────────────────────────────────────────┘
EOF
printf "${C_RESET}
${C_BOLD}Next steps${C_RESET}
  1. export your key:
       ${C_CYAN}export NOVAIR_OPENROUTER_API_KEY=\"sk-or-v1-…\"${C_RESET}      # OpenRouter
     or any OpenAI-compatible endpoint:
       ${C_CYAN}export NOVAIR_BASE_URL=http://localhost:11434/v1${C_RESET}    # Ollama etc.
       ${C_CYAN}export NOVAIR_MODEL=llama3.1${C_RESET}
  2. launch:
       ${C_CYAN}novair chat${C_RESET}          # full TUI
       ${C_CYAN}novair run \"hi\"${C_RESET}      # one-shot

${C_DIM}Zero-key demo: python examples/mock_server.py & novair --base-url http://localhost:8931/v1 --model mock-small chat${C_RESET}
"
