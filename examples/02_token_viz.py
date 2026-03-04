#!/usr/bin/env python3
"""
Example 02: Token-level visualization
Shows exactly which tokens are kept (green) and dropped (red),
with their log-probabilities, so you can see WHY each decision was made.

Usage:
    python3 examples/02_token_viz.py [--ratio 0.5] [--threshold -1.0]
"""
import subprocess, json, sys, argparse, shutil

BIN = shutil.which("imptokens") or "./target/release/imptokens"

TEXTS = {
    "prose": (
        "The quick brown fox jumps over the lazy dog. "
        "This sentence is often used to test typefaces because it contains "
        "every letter of the English alphabet at least once."
    ),
    "code_comment": (
        "# This function iterates over all elements in the list and returns "
        "a new list containing only the elements that satisfy the predicate. "
        "It uses a list comprehension for conciseness and efficiency."
    ),
    "repetitive": (
        "The model predicts the next token. "
        "The model predicts the next word. "
        "The model predicts the next symbol. "
        "The model predicts the next character. "
        "The model predicts the next element."
    ),
}

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
DIM    = "\033[2m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def compress_debug(text: str, args) -> dict:
    cmd = [BIN]
    if args.ratio:
        cmd += ["--keep-ratio", str(args.ratio)]
    elif args.threshold:
        cmd += ["--threshold", str(args.threshold)]
    cmd += ["--debug"]
    result = subprocess.run(cmd, input=text, capture_output=True, text=True)
    return json.loads(result.stdout)


def render(data: dict, label: str):
    tokens = data["tokens"]
    n_orig = data["n_original"]
    n_kept = data["n_kept"]
    ratio  = data["compression_ratio"]

    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}{label}{RESET}  "
          f"[{n_kept}/{n_orig} tokens kept, {ratio*100:.0f}% retained]")
    print(f"{'─'*60}")

    # Token-by-token visualization
    print("\nToken view  (green=kept, red=dropped, logprob shown):\n")
    for t in tokens:
        text  = repr(t["text"])[1:-1]          # strip outer quotes
        lp    = t["logprob"]
        kept  = t["kept"]
        lp_str = f"{lp:+.2f}" if lp is not None else " BOS"
        color  = GREEN if kept else RED
        marker = "✓" if kept else "✗"
        print(f"  {color}{marker} {text!s:<18}{RESET} {DIM}{lp_str}{RESET}")

    print(f"\n{BOLD}Original:{RESET}   {data['original_text'][:120]}")
    print(f"{BOLD}Compressed:{RESET} {data['compressed_text'][:120]}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ratio",     type=float, default=None)
    p.add_argument("--threshold", type=float, default=-1.0)
    p.add_argument("--text",      choices=list(TEXTS), default=None,
                   help="which example text to use (default: all)")
    args = p.parse_args()

    targets = {args.text: TEXTS[args.text]} if args.text else TEXTS

    print(f"{BOLD}imptokens — Token-Level Visualization{RESET}")
    strategy = f"keep-ratio {args.ratio}" if args.ratio else f"threshold {args.threshold}"
    print(f"Strategy: {strategy}")

    for label, text in targets.items():
        data = compress_debug(text, args)
        render(data, label)


if __name__ == "__main__":
    main()
