#!/usr/bin/env python3
"""
Example 04: Rich compression visualization

Shows compression is:
  (1) HIGH QUALITY  — color-coded heatmap: informative tokens (red/yellow) are
                      kept; the dim tokens that vanish are genuinely low-value.
  (2) HIGH DENSITY  — visual density bar + before/after token count.

Usage:
    python3 examples/04_demo.py                       # demo all built-in texts
    python3 examples/04_demo.py --text git_diff
    echo 'your text' | python3 examples/04_demo.py
    python3 examples/04_demo.py --html report.html    # also export HTML
    python3 examples/04_demo.py --ratio 0.3           # aggressive compression
"""
import subprocess, json, sys, argparse, shutil, os

BIN = shutil.which("imptokens") or "./target/release/imptokens"

# ── ANSI codes ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
# logprob heatmap: low logprob = surprising = important = warm colour
HEAT = [
    "\033[91m",   # bright red     logprob < -5  (extremely informative)
    "\033[93m",   # yellow         logprob < -3
    "\033[32m",   # green          logprob < -1.5
    "\033[92m",   # bright green   logprob < -0.5
]


def _heat_color(lp: float | None) -> str:
    if lp is None:
        return "\033[96m"   # cyan — BOS token
    if lp < -5.0: return HEAT[0]
    if lp < -3.0: return HEAT[1]
    if lp < -1.5: return HEAT[2]
    return HEAT[3]


# ── Built-in sample texts ────────────────────────────────────────────────────

SAMPLES = {
    "git_diff": (
        "diff --git a/src/model.py b/src/model.py\n"
        "index 3f4a2b1..8c9d0e2 100644\n"
        "--- a/src/model.py\n"
        "+++ b/src/model.py\n"
        "@@ -42,7 +42,9 @@ class Transformer(nn.Module):\n"
        "     def forward(self, x):\n"
        "-        return self.layers(x)\n"
        "+        x = self.embed(x)\n"
        "+        x = self.layers(x)\n"
        "+        return self.head(x)\n"
    ),
    "technical": (
        "Transformers use self-attention to compute weighted sums of value vectors, "
        "where weights are derived from queries and keys via scaled dot-product attention. "
        "The multi-head variant projects inputs into multiple subspaces, enabling the model "
        "to attend to information from different representation subspaces simultaneously. "
        "Residual connections and layer normalization stabilize training of deep networks."
    ),
    "error_log": (
        "Traceback (most recent call last):\n"
        "  File 'train.py', line 142, in run_epoch\n"
        "    loss = criterion(outputs, targets)\n"
        "  File 'loss.py', line 67, in forward\n"
        "    return F.cross_entropy(input, target, reduction=self.reduction)\n"
        "RuntimeError: Expected input batch_size (32) to match target batch_size (16). "
        "Check that DataLoader drop_last=True or that batch sizes are consistent."
    ),
    "repetitive": (
        "To install the package, run pip install mypackage. "
        "After installation, import the package with import mypackage. "
        "The package provides the following functions. "
        "The first function is mypackage.compress() which compresses data. "
        "The second function is mypackage.decompress() which decompresses data. "
        "The third function is mypackage.validate() which validates data. "
        "All functions return True on success and False on failure."
    ),
}


# ── Compression call ─────────────────────────────────────────────────────────

def compress(text: str, ratio: float | None, threshold: float | None) -> dict:
    cmd = [BIN]
    if ratio is not None:
        cmd += ["--keep-ratio", str(ratio)]
    elif threshold is not None:
        cmd += ["--threshold", str(threshold)]
    cmd += ["--debug"]
    r = subprocess.run(cmd, input=text, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"imptokens error:\n{r.stderr[:400]}", file=sys.stderr)
        sys.exit(1)
    return json.loads(r.stdout)


# ── Terminal rendering ────────────────────────────────────────────────────────

def _density_bar(ratio: float, width: int = 44) -> str:
    filled = round(ratio * width)
    bar  = "\033[92m" + "█" * filled
    bar += DIM + "░" * (width - filled)
    bar += RESET
    return bar


def render_terminal(data: dict, label: str) -> None:
    tokens  = data["tokens"]
    n_orig  = data["n_original"]
    n_kept  = data["n_kept"]
    ratio   = data["compression_ratio"]
    n_drop  = n_orig - n_kept
    W = 62

    # ── header ──────────────────────────────────────────────────
    print(f"\n{BOLD}{'━' * W}{RESET}")
    print(f"{BOLD}  {label}{RESET}")
    print(f"{BOLD}{'━' * W}{RESET}")

    # ── density ──────────────────────────────────────────────────
    bar = _density_bar(ratio)
    pct_saved = (1 - ratio) * 100
    print(f"\n  {BOLD}DENSITY{RESET}  {bar}")
    print(f"           {BOLD}{n_kept}{RESET}/{n_orig} tokens kept"
          f"  ·  {BOLD}{pct_saved:.0f}%{RESET} reduction  ·  −{n_drop} tokens")

    # ── top informative tokens ────────────────────────────────────
    scored_kept = sorted(
        [(t["logprob"], t["text"].strip()) for t in tokens
         if t["kept"] and t["logprob"] is not None and t["text"].strip()],
    )[:8]
    if scored_kept:
        highlights = "  ".join(
            f"{HEAT[0] if lp < -5 else HEAT[1] if lp < -3 else HEAT[2]}"
            f'"{txt}"'
            f"{RESET}"
            for lp, txt in scored_kept
        )
        print(f"\n  {BOLD}QUALITY{RESET}  Most informative tokens kept:")
        print(f"           {highlights}")

    # ── inline heatmap of original text ──────────────────────────
    print(f"\n  {BOLD}ORIGINAL{RESET}"
          f"  {DIM}(warm=informative kept, dim=dropped){RESET}\n")

    col = 2
    sys.stdout.write("  ")
    for t in tokens:
        raw = t["text"]
        if t["kept"]:
            sys.stdout.write(f"{_heat_color(t['logprob'])}{raw}{RESET}")
        else:
            sys.stdout.write(f"{DIM}{raw}{RESET}")
        # soft wrap — only break at spaces after column 70
        col += len(raw)
        if col > 70 and " " in raw:
            sys.stdout.write("\n  ")
            col = 2
    print()

    # ── compressed output ─────────────────────────────────────────
    print(f"\n  {BOLD}COMPRESSED{RESET}\n")
    compressed = data["compressed_text"]
    # word-wrap at 70
    line = "  "
    for word in compressed.replace("\n", " \n ").split(" "):
        if len(line) + len(word) + 1 > 70:
            print(line.rstrip())
            line = "  " + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line.rstrip())

    print(f"\n{BOLD}{'━' * W}{RESET}\n")


# ── HTML report ───────────────────────────────────────────────────────────────

def _lp_to_css(lp: float | None, kept: bool) -> str:
    """CSS color for a token span."""
    if not kept:
        return "color:#444;text-decoration:none"
    if lp is None:
        return "color:#4dd0e1;font-weight:600"
    if lp < -5.0: return "background:#ff000030;color:#ff6b6b;border-bottom:2px solid #ff6b6b"
    if lp < -3.0: return "background:#ffa50022;color:#ffb74d;border-bottom:2px solid #ffb74d"
    if lp < -1.5: return "background:#4caf5022;color:#81c784;border-bottom:2px solid #81c784"
    return "color:#a5d6a7"


def render_html(data: dict, label: str, path: str) -> None:
    tokens = data["tokens"]
    n_orig = data["n_original"]
    n_kept = data["n_kept"]
    ratio  = data["compression_ratio"]
    n_drop = n_orig - n_kept
    pct_kept  = ratio * 100
    pct_saved = (1 - ratio) * 100

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    token_spans = []
    for t in tokens:
        txt = esc(t["text"])
        lp  = t["logprob"]
        lp_str = f"{lp:.3f}" if lp is not None else "BOS"
        style = _lp_to_css(lp, t["kept"])
        kept_label = "kept" if t["kept"] else "dropped"
        token_spans.append(
            f'<span style="{style};border-radius:2px;padding:0 1px" '
            f'title="{kept_label}  logprob: {lp_str}">{txt}</span>'
        )

    compressed_esc = esc(data["compressed_text"])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>imptokens — {label}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Menlo','Monaco','Courier New',monospace;
    background: #0d1117; color: #c9d1d9;
    padding: 32px 24px; font-size: 14px; line-height: 1.6;
  }}
  h1 {{ color: #58a6ff; font-size: 1.4em; margin-bottom: 4px; }}
  .sub {{ color: #8b949e; font-size: 0.9em; margin-bottom: 28px; }}
  .card {{
    background: #161b22; border: 1px solid #30363d;
    border-radius: 8px; padding: 20px; margin-bottom: 18px;
  }}
  .card-title {{
    font-size: 0.75em; text-transform: uppercase; letter-spacing: 1px;
    color: #58a6ff; margin-bottom: 14px;
  }}
  .stats {{ display: flex; gap: 32px; flex-wrap: wrap; margin-bottom: 20px; }}
  .stat .n {{ font-size: 2.2em; font-weight: 700; color: #58a6ff; line-height: 1; }}
  .stat .l {{ font-size: 0.75em; color: #8b949e; margin-top: 2px; }}
  .bar-wrap {{
    background: #21262d; border-radius: 4px; height: 10px; overflow: hidden;
  }}
  .bar-fill {{
    background: linear-gradient(90deg,#238636,#3fb950);
    height: 100%; border-radius: 4px;
    width: {pct_kept:.1f}%;
  }}
  .bar-labels {{
    display: flex; justify-content: space-between;
    font-size: 0.72em; color: #8b949e; margin-top: 4px;
  }}
  .legend {{ display: flex; gap: 18px; flex-wrap: wrap; font-size: 0.78em; color: #8b949e; margin-bottom: 14px; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }}
  .text {{ white-space: pre-wrap; word-break: break-word; font-size: 0.92em; line-height: 2; }}
  .compressed {{ color: #3fb950; }}
</style>
</head>
<body>
<h1>imptokens</h1>
<div class="sub">{label}</div>

<div class="card">
  <div class="stats">
    <div class="stat"><div class="n">{pct_saved:.0f}%</div><div class="l">reduction</div></div>
    <div class="stat"><div class="n">{n_kept}</div><div class="l">tokens kept</div></div>
    <div class="stat"><div class="n">{n_drop}</div><div class="l">tokens dropped</div></div>
    <div class="stat"><div class="n">{n_orig}</div><div class="l">original tokens</div></div>
  </div>
  <div class="bar-wrap"><div class="bar-fill"></div></div>
  <div class="bar-labels"><span>{pct_kept:.0f}% kept</span><span>{pct_saved:.0f}% dropped</span></div>
</div>

<div class="card">
  <div class="card-title">Original text — hover tokens for logprob · warm = informative · dim = dropped</div>
  <div class="legend">
    <span><span class="dot" style="background:#ff6b6b"></span>very informative (logprob &lt; −5)</span>
    <span><span class="dot" style="background:#ffb74d"></span>informative (−5 to −3)</span>
    <span><span class="dot" style="background:#81c784"></span>mildly informative (−3 to −1.5)</span>
    <span><span class="dot" style="background:#a5d6a7"></span>kept (predictable)</span>
    <span><span class="dot" style="background:#333;border:1px solid #555"></span>dropped</span>
  </div>
  <div class="text">{"".join(token_spans)}</div>
</div>

<div class="card">
  <div class="card-title">Compressed output</div>
  <div class="text compressed">{compressed_esc}</div>
</div>
</body>
</html>
"""
    with open(path, "w") as f:
        f.write(html)
    print(f"  → HTML report: {path}", file=sys.stderr)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Rich compression quality + density visualization")
    p.add_argument("--ratio",     type=float, default=0.5,
                   help="keep-ratio (default 0.5)")
    p.add_argument("--threshold", type=float, default=None,
                   help="logprob threshold (overrides --ratio)")
    p.add_argument("--text",      choices=list(SAMPLES), default=None,
                   help="built-in sample text (default: all)")
    p.add_argument("--html",      metavar="PATH", default=None,
                   help="write HTML report to PATH (per-sample suffix added when running all)")
    args = p.parse_args()

    ratio     = None if args.threshold is not None else args.ratio
    threshold = args.threshold

    # stdin
    if not sys.stdin.isatty() and args.text is None:
        text = sys.stdin.read()
        data = compress(text, ratio, threshold)
        render_terminal(data, "stdin")
        if args.html:
            render_html(data, "stdin", args.html)
        return

    # single built-in sample
    if args.text is not None:
        text = SAMPLES[args.text]
        data = compress(text, ratio, threshold)
        render_terminal(data, args.text)
        if args.html:
            render_html(data, args.text, args.html)
        return

    # all built-in samples
    for key, text in SAMPLES.items():
        data = compress(text, ratio, threshold)
        render_terminal(data, key)
        if args.html:
            base, ext = os.path.splitext(args.html)
            ext = ext or ".html"
            render_html(data, key, f"{base}_{key}{ext}")


if __name__ == "__main__":
    main()
