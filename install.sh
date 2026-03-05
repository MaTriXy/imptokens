#!/usr/bin/env bash
# imptokens installer
# Builds the binary, installs helpers, and optionally wires up Claude Code hooks.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
SETTINGS="${HOME}/.claude/settings.json"
BINARY="imptokens"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
die()  { echo -e "${RED}✗${RESET} $*" >&2; exit 1; }

# ── 1. Check Rust ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}imptokens installer${RESET}\n"

if ! command -v cargo &>/dev/null; then
  if [[ -f "$HOME/.cargo/env" ]]; then
    # shellcheck source=/dev/null
    source "$HOME/.cargo/env"
  fi
fi

if ! command -v cargo &>/dev/null; then
  die "Rust not found. Install from https://rustup.rs/ then re-run this script."
fi
ok "Rust $(rustc --version | cut -d' ' -f2)"

# ── 2. Detect GPU backend ─────────────────────────────────────────────────────
detect_feature() {
  if [[ "$(uname)" == "Darwin" ]]; then
    echo "metal"
  elif command -v nvcc &>/dev/null || [[ -d /usr/local/cuda ]]; then
    echo "cuda"
  elif command -v vulkaninfo &>/dev/null; then
    echo "vulkan"
  else
    echo ""
  fi
}

GPU_FEATURE="$(detect_feature)"
if [[ -n "$GPU_FEATURE" ]]; then
  FEATURE_FLAG="--features $GPU_FEATURE"
  ok "GPU backend selected: $GPU_FEATURE"
else
  FEATURE_FLAG=""
  warn "No GPU backend detected — building CPU-only (slower inference)."
  warn "To enable CUDA: install the CUDA toolkit and re-run this script."
  warn "To enable Vulkan: install Vulkan drivers and re-run this script."
fi

# ── 3. Build ──────────────────────────────────────────────────────────────────
echo "Building release binary (this takes ~2 min on first run)…"
cd "$SCRIPT_DIR"
# shellcheck disable=SC2086
cargo build --release --quiet $FEATURE_FLAG
ok "Binary built → ${SCRIPT_DIR}/target/release/${BINARY}"

# ── 4. Install binary ─────────────────────────────────────────────────────────
mkdir -p "$BIN_DIR"
cp "target/release/${BINARY}" "${BIN_DIR}/${BINARY}"
ok "Installed → ${BIN_DIR}/${BINARY}"

# ── 5. Install helpers ────────────────────────────────────────────────────────

# compress-if-large: transparent compression filter for piped commands
cat > "${BIN_DIR}/compress-if-large" << 'SCRIPT'
#!/usr/bin/env bash
# Compress stdin if it exceeds MIN_CHARS. Falls back to raw output on error.
BINARY="$HOME/.local/bin/imptokens"
MIN_CHARS="${COMPRESS_MIN_CHARS:-4000}"
RATIO="${COMPRESS_RATIO:-0.6}"
content=$(cat)
if [ ${#content} -le "$MIN_CHARS" ] || [ ! -x "$BINARY" ]; then
  printf '%s' "$content"; exit 0
fi
compressed=$("$BINARY" --keep-ratio "$RATIO" 2>/dev/null <<< "$content")
if [ -n "$compressed" ]; then printf '%s' "$compressed"
else printf '%s' "$content"; fi
SCRIPT
chmod +x "${BIN_DIR}/compress-if-large"
ok "Installed → ${BIN_DIR}/compress-if-large"

# compress-paste: compress clipboard and put it back
cat > "${BIN_DIR}/compress-paste" << 'SCRIPT'
#!/usr/bin/env bash
# Compress clipboard content and replace it, ready to paste.
# Usage: compress-paste [keep-ratio]   (default: 0.5)
BINARY="$HOME/.local/bin/imptokens"
RATIO="${1:-0.5}"
if [[ ! -x "$BINARY" ]]; then echo "Error: $BINARY not found." >&2; exit 1; fi
ORIGINAL=$(pbpaste)
EST_TOKENS=$(( ${#ORIGINAL} / 4 ))
if [[ $EST_TOKENS -lt 100 ]]; then
  echo "Text too short (~${EST_TOKENS} tokens), skipping." >&2; exit 0
fi
COMPRESSED=$(echo "$ORIGINAL" | "$BINARY" --keep-ratio "$RATIO" 2>/dev/null)
SAVED=$(( EST_TOKENS - ${#COMPRESSED} / 4 ))
PCT=$(( SAVED * 100 / EST_TOKENS ))
echo "$COMPRESSED" | pbcopy
echo "✓ Compressed ~${EST_TOKENS} → ~$(( ${#COMPRESSED} / 4 )) tokens (saved ~${PCT}%). Ready to paste." >&2
SCRIPT
chmod +x "${BIN_DIR}/compress-paste"
ok "Installed → ${BIN_DIR}/compress-paste"

# ── 6. PATH check ─────────────────────────────────────────────────────────────
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
  warn "${BIN_DIR} is not in PATH. Add to ~/.zshrc:"
  echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── 7. Claude Code integration (optional) ─────────────────────────────────────
echo ""
read -r -p "Set up Claude Code bash-output compression hook? [y/N] " ans_hook
if [[ "$ans_hook" =~ ^[Yy]$ ]]; then
  RTK_HOOK="${HOME}/.claude/hooks/rtk-rewrite.sh"

  if [[ ! -f "$RTK_HOOK" ]]; then
    warn "RTK hook not found at ${RTK_HOOK}. Skipping hook integration."
    warn "If you install RTK later, re-run install.sh to add compression."
  else
    # Add compress-if-large to RTK hook if not already present
    if grep -q "compress-if-large" "$RTK_HOOK" 2>/dev/null; then
      ok "RTK hook already has compress-if-large — nothing to change."
    else
      # Insert before "# If no rewrite needed, approve as-is"
      PATCH='
# Pipe large-output commands through semantic compression.
if command -v compress-if-large &>/dev/null; then
  case "$REWRITTEN" in
    *"rtk git diff"*|*"rtk git log"*|*"rtk git show"*|\
    *"rtk read"*|*"rtk curl"*|*"rtk grep"*|*"rtk find"*)
      REWRITTEN="$REWRITTEN | compress-if-large"
      ;;
  esac
fi'
      # Use awk to insert before the "If no rewrite" comment
      awk -v patch="$PATCH" '
        /^# If no rewrite needed/ { print patch }
        { print }
      ' "$RTK_HOOK" > "${RTK_HOOK}.tmp" && mv "${RTK_HOOK}.tmp" "$RTK_HOOK"
      chmod +x "$RTK_HOOK"
      ok "RTK hook patched — large outputs will be semantically compressed."
    fi
  fi
fi

echo ""
read -r -p "Add /compress-paste slash command for Claude Code? [y/N] " ans_slash
if [[ "$ans_slash" =~ ^[Yy]$ ]]; then
  mkdir -p "${HOME}/.claude/commands"
  cat > "${HOME}/.claude/commands/compress-paste.md" << 'CMD'
Run `compress-paste $ARGUMENTS` to compress the current clipboard content and
replace it with the compressed version, then report the result.
If no argument is provided, use the default ratio of 0.5.
CMD
  ok "Slash command /compress-paste registered."
fi

# ── 8. Done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Installation complete!${RESET}"
echo ""
echo "  Quick start:"
echo "    echo 'your text' | imptokens --stats"
echo "    cat bigfile.txt | imptokens --keep-ratio 0.5"
echo "    compress-paste                  # compress clipboard"
echo "    python3 examples/02_token_viz.py --ratio 0.5"
echo ""
echo "  In Claude Code CLI, type /compress-paste to compress your clipboard."
echo ""
echo "  Restart Claude Code for hook changes to take effect."
