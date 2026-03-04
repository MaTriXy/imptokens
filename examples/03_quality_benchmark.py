#!/usr/bin/env python3
"""
Example 03: Quality benchmark
Measures how well compression preserves information across multiple text types
and compression ratios. Reports:
  - Token reduction
  - Word retention (% of content words kept)
  - Key-phrase survival (did the main concepts make it through?)

Usage:
    python3 examples/03_quality_benchmark.py
"""
import subprocess, json, sys, shutil
from dataclasses import dataclass
from typing import Optional

BIN = shutil.which("imptokens") or "./target/release/imptokens"

# ── Test cases ──────────────────────────────────────────────────────────────
CASES = [
    {
        "label": "Dense technical prose",
        "text": (
            "Transformers use self-attention to compute weighted sums of value vectors, "
            "where weights are derived from queries and keys via scaled dot-product attention. "
            "The multi-head variant projects inputs into multiple subspaces, enabling the model "
            "to attend to information from different representation subspaces simultaneously. "
            "Residual connections and layer normalization stabilize training of deep networks."
        ),
        "key_phrases": ["self-attention", "queries", "keys", "multi-head", "residual"],
    },
    {
        "label": "Repetitive documentation",
        "text": (
            "To install the package, run pip install mypackage. "
            "After installation, import the package with import mypackage. "
            "The package provides the following functions. "
            "The first function is mypackage.compress() which compresses data. "
            "The second function is mypackage.decompress() which decompresses data. "
            "The third function is mypackage.validate() which validates data. "
            "All functions return True on success and False on failure."
        ),
        "key_phrases": ["compress", "decompress", "validate", "True", "False"],
    },
    {
        "label": "Git diff output",
        "text": (
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
        "key_phrases": ["forward", "embed", "layers", "head"],
    },
    {
        "label": "Stack trace / error log",
        "text": (
            "Traceback (most recent call last):\n"
            "  File 'train.py', line 142, in run_epoch\n"
            "    loss = criterion(outputs, targets)\n"
            "  File 'loss.py', line 67, in forward\n"
            "    return F.cross_entropy(input, target, reduction=self.reduction)\n"
            "RuntimeError: Expected input batch_size (32) to match target batch_size (16). "
            "Check that DataLoader drop_last=True or that batch sizes are consistent."
        ),
        "key_phrases": ["RuntimeError", "batch_size", "32", "16", "drop_last"],
    },
]

RATIOS = [0.7, 0.5, 0.3]


@dataclass
class Result:
    label: str
    ratio_target: float
    n_orig: int
    n_kept: int
    compression_ratio: float
    key_phrase_survival: float   # fraction of key phrases present in compressed text
    compressed_text: str


def run(text: str, ratio: float) -> dict:
    result = subprocess.run(
        [BIN, "--keep-ratio", str(ratio), "--debug"],
        input=text, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  Error: {result.stderr[:200]}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def key_phrase_survival(phrases: list[str], compressed: str) -> float:
    found = sum(1 for p in phrases if p.lower() in compressed.lower())
    return found / len(phrases) if phrases else 1.0


def benchmark() -> list[Result]:
    results = []
    total = len(CASES) * len(RATIOS)
    i = 0
    for case in CASES:
        for ratio in RATIOS:
            i += 1
            print(f"  [{i}/{total}] {case['label']} @ ratio={ratio}…", end=" ", flush=True)
            data = run(case["text"], ratio)
            survival = key_phrase_survival(case["key_phrases"], data["compressed_text"])
            results.append(Result(
                label=case["label"],
                ratio_target=ratio,
                n_orig=data["n_original"],
                n_kept=data["n_kept"],
                compression_ratio=data["compression_ratio"],
                key_phrase_survival=survival,
                compressed_text=data["compressed_text"],
            ))
            print(f"✓ {data['n_kept']}/{data['n_original']} tokens, "
                  f"{survival*100:.0f}% key phrases")
    return results


def report(results: list[Result]):
    print("\n" + "═"*72)
    print(" Quality Benchmark Results")
    print("═"*72)

    # Group by label
    by_label: dict[str, list[Result]] = {}
    for r in results:
        by_label.setdefault(r.label, []).append(r)

    for label, rs in by_label.items():
        print(f"\n  {label}")
        print(f"  {'─'*50}")
        print(f"  {'Target':>8}  {'Actual':>8}  {'Tokens':>14}  {'Key phrases':>12}")
        for r in sorted(rs, key=lambda x: x.ratio_target, reverse=True):
            actual_pct = r.compression_ratio * 100
            bar = "█" * int(r.key_phrase_survival * 10) + "░" * (10 - int(r.key_phrase_survival * 10))
            print(f"  {r.ratio_target*100:>7.0f}%  {actual_pct:>7.1f}%  "
                  f"{r.n_kept:>5}/{r.n_orig:<5}  "
                  f"{bar} {r.key_phrase_survival*100:.0f}%")

    # Summary
    print("\n" + "─"*72)
    avg_survival = sum(r.key_phrase_survival for r in results) / len(results)
    avg_reduction = 1 - sum(r.compression_ratio for r in results) / len(results)
    print(f"  Average token reduction:     {avg_reduction*100:.1f}%")
    print(f"  Average key phrase survival: {avg_survival*100:.1f}%")
    print(f"\n  Interpretation: key phrases = domain-critical terms that")
    print(f"  should survive compression. High survival + high reduction = good.")
    print("═"*72)


if __name__ == "__main__":
    print("imptokens — Quality Benchmark")
    print(f"Binary: {BIN}")
    print(f"Cases: {len(CASES)}, Ratios: {RATIOS}\n")
    print("Running compressions…")
    results = benchmark()
    report(results)
