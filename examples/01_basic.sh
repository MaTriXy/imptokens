#!/usr/bin/env bash
# Example 01: Basic compression — threshold vs keep-ratio
# Run from the imptokens/ directory:
#   bash examples/01_basic.sh
set -euo pipefail

BIN="${1:-./target/release/imptokens}"

TEXT="The transformer architecture introduced in 'Attention Is All You Need' \
revolutionized natural language processing. Self-attention mechanisms allow \
models to weigh the importance of different tokens when encoding a sequence. \
Positional encodings provide information about token order since transformers \
have no inherent notion of sequence. Feed-forward layers process each position \
independently after the attention step. Layer normalization stabilizes training \
by normalizing activations before each sub-layer."

echo "═══════════════════════════════════════════════════════════"
echo " imptokens — Example 01: Basic Compression"
echo "═══════════════════════════════════════════════════════════"
echo
echo "INPUT (~$(echo "$TEXT" | wc -w | tr -d ' ') words):"
echo "$TEXT"
echo

echo "── Default threshold (-1.0): keep tokens with logprob < -1.0 ──"
echo "$TEXT" | "$BIN" --stats 2>&1
echo

echo "── keep-ratio 0.4: keep 40% most surprising tokens ──"
echo "$TEXT" | "$BIN" --keep-ratio 0.4 --stats 2>&1
echo

echo "── keep-ratio 0.7: keep 70% (lighter compression) ──"
echo "$TEXT" | "$BIN" --keep-ratio 0.7 --stats 2>&1
