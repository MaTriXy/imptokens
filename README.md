<h1 align="center">imptokens</h1>

<p align="center">
  <strong>Cut your Claude / GPT token costs by 30–60%.</strong><br/>
  Runs 100% locally. No data leaves your machine. No API. No subscription.
</p>

<p align="center">
  <a href="https://github.com/nimhar/imptokens/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-16a34a"></a>
  <a href="https://github.com/nimhar/imptokens"><img alt="Platform" src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-111827"></a>
  <a href="https://www.rust-lang.org/"><img alt="Rust" src="https://img.shields.io/badge/rust-1.70%2B-f97316"></a>
  <a href="https://github.com/nimhar/imptokens/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/nimhar/imptokens?style=flat-square&logo=github&label=Stars"></a>
</p>

```bash
curl -fsSL https://raw.githubusercontent.com/nimhar/imptokens/main/install.sh | bash
```

Then wire it into Claude Code once — and never think about it again:

```bash
imptokens --setup-claude
# ✓ Claude Code hook configured
#   Every prompt over 500 tokens is automatically compressed before it reaches the model.
#   Restart Claude Code to activate.
```

`imptokens` uses a small local model to score every token by information density, keeps the signal, and drops predictable filler. In practice this cuts context size by 30–70% with no meaningful loss in answer quality.

```bash
git diff HEAD~5 | imptokens --keep-ratio 0.5 --stats
# tokens: 312/624 kept  (50.0% reduction, 312 saved)
```

## Table of contents

- [Why imptokens](#why-imptokens)
- [Demo](#demo)
- [Real workflow impact](#real-workflow-impact)
- [Quick start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [CLI reference](#cli-reference)
- [How it works](#how-it-works)
- [Quality benchmark](#quality-benchmark)
- [Performance](#performance)
- [Claude Code integration](#claude-code-integration)
- [Model guide](#model-guide)
- [Examples](#examples)
- [Contributing](#contributing)
- [Architecture](#architecture)
- [Roadmap](#roadmap)
- [License](#license)

## Why imptokens

- Built for AI-heavy developer workflows: diffs, logs, long docs, and generated outputs.
- Fully local execution on Apple Silicon via `llama.cpp` + Metal.
- CLI-first design for shell pipelines and agent/tool hooks.
- Multiple output formats (`text`, `token-ids`, `json`) and token-level debug view.
- Includes practical Claude Code integration helpers (`compress-if-large`, `compress-paste`, hook mode).

## Demo

![imptokens demo](video/out/Imptokens.gif)

## Real workflow impact

These are practical “before -> after” examples that show what the project contributes in day-to-day work:

### 1) Large git diff before review

```bash
git diff HEAD~8 | imptokens --keep-ratio 0.5 --stats
# Keeps key symbols and changed lines while cutting context cost
```

### 2) Long error output before asking Claude

```bash
pytest -q 2>&1 | imptokens --keep-ratio 0.6 --stats
# Preserves stack anchors and failure hints, trims repeated noise
```

### 3) Pre-compress clipboard for Claude prompts

```bash
compress-paste 0.5
# Paste a denser prompt with lower token spend
```

### 4) Optional RTK hook flow (only if RTK is installed)

```text
rtk read bigfile.py | compress-if-large
rtk git diff HEAD~5 | compress-if-large
```

### 5) Hook-mode compression for UserPromptSubmit events

```bash
echo '{"prompt":"...very long prompt..."}' | imptokens --hook-mode --hook-threshold 500
```

## Quick start

```bash
# Install (auto-detects GPU, no Rust required)
curl -fsSL https://raw.githubusercontent.com/nimhar/imptokens/main/install.sh | bash

# Wire into Claude Code — one time, then forget about it
imptokens --setup-claude

# Try it
echo "Your long text goes here" | imptokens --keep-ratio 0.5 --stats
```

## Installation

### One-liner (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/nimhar/imptokens/main/install.sh | bash
```

- Downloads a pre-built binary for your platform (no Rust needed)
- Falls back to compiling from source if no binary is available
- Auto-detects GPU backend: Metal → CUDA → Vulkan → CPU
- Installs to `~/.local/bin`

### Homebrew (macOS)

```bash
brew tap nimhar/imptokens https://github.com/nimhar/imptokens
brew install imptokens
```

### Build from source

Requires Rust 1.70+:

```bash
# macOS Apple Silicon (Metal)
cargo build --release --features metal

# NVIDIA GPU — requires CUDA toolkit installed
cargo build --release --features cuda

# Cross-platform Vulkan (Windows, Linux, etc.)
cargo build --release --features vulkan

# CPU-only fallback (any platform, no GPU required)
cargo build --release
```

The default model is downloaded once and cached at `~/.cache/huggingface/hub/`.

## Usage

### Inline text

```bash
imptokens "Your long text here" --stats
```

### From file

```bash
imptokens --file document.txt --keep-ratio 0.5
```

### From stdin

```bash
cat bigfile.py | imptokens --keep-ratio 0.6
git diff HEAD~5 | imptokens --stats
curl -s https://example.com/api | imptokens --keep-ratio 0.5
```

### Output formats

```bash
imptokens "text" --output-format text
imptokens "text" --output-format token-ids
imptokens "text" --output-format json
imptokens "text" --debug
```

## CLI reference

### Input

| Flag | Description |
|---|---|
| `[TEXT]` | Positional text input |
| `-f, --file <PATH>` | Read from file (`-` for stdin) |

### Model

| Flag | Default | Description |
|---|---|---|
| `-m, --model <REPO>` | `bartowski/Llama-3.2-1B-Instruct-GGUF` | HuggingFace repo ID |
| `--model-file <FILE>` | `Llama-3.2-1B-Instruct-Q4_K_M.gguf` | GGUF file in the repo |
| `--local-model <PATH>` | none | Use local GGUF path |

### Compression strategy

Use one strategy at a time.

| Flag | Default | Description |
|---|---|---|
| `-t, --threshold <LOGPROB>` | `-1.0` | Keep tokens where `logprob < threshold` |
| `-k, --keep-ratio <RATIO>` | none | Keep top most-surprising fraction (`0 < ratio <= 1`) |

### Output and diagnostics

| Flag | Description |
|---|---|
| `-o, --output-format <FMT>` | `text`, `token-ids`, or `json` |
| `-d, --debug` | Full per-token JSON |
| `-s, --stats` | Print compression stats to stderr |

### Hook mode

| Flag | Default | Description |
|---|---|---|
| `--hook-mode` | `false` | Claude Code UserPromptSubmit hook mode |
| `--hook-threshold <N>` | `500` | Min estimated tokens before compression |

### Claude Code setup

| Flag | Description |
|---|---|
| `--setup-claude` | Write hook config to `~/.claude/settings.json` |

## How it works

`imptokens` runs a small local model to assign an **information-density score** to every token in your input. Tokens that carry signal are kept. Tokens that are structurally predictable — boilerplate, repeated patterns, filler — are dropped.

The scoring is context-aware: the same word can be high-value in one position and redundant in another, depending on what surrounds it. This is what separates it from keyword filtering or stopword removal, which are context-blind.

```text
Input:   The model predicts the next token. The model predicts the next word.
kept?:    Y     Y      Y     Y    Y    Y      Y    Y      Y     N    N    Y
Output:  The model predicts the next token. The model predicts word.
```

The second sentence is mostly predictable repetition, so only the novel ending is retained. The scoring runs in a single local forward pass — no generation, no sampling, no network calls.

## Quality benchmark

Measured with `examples/03_quality_benchmark.py`.

| Text type | Target reduction | Actual reduction | Key-phrase survival |
|---|---:|---:|---:|
| Dense technical prose | 50% | 50.8% | 20% |
| Repetitive documentation | 50% | 51.2% | 60% |
| Git diff output | 50% | 50.5% | 100% |
| Error log / stack trace | 50% | 51.1% | 60% |

Practical defaults:

- `--keep-ratio 0.5` for diffs/code/logs
- `--keep-ratio 0.7` for dense prose where recall matters more

Run locally:

```bash
python3 examples/03_quality_benchmark.py
python3 examples/02_token_viz.py --ratio 0.5
```

## Performance

`imptokens` only runs a single forward pass (no generation) so throughput is dominated by prompt-processing speed, which is the fast path in llama.cpp.

### Tokens per second (Llama 3.2 1B Q4\_K\_M)

| Hardware | Estimated throughput |
|---|---|
| Apple M2 / M3 (Metal) | ~2,000–4,000 tok/s |
| Apple M1 (Metal) | ~1,000–2,000 tok/s |
| NVIDIA RTX 3090 (CUDA) | ~3,000–6,000 tok/s |
| CPU-only (modern laptop) | ~200–500 tok/s |

### Wall-clock time for common input sizes (Apple M2, Metal)

| Input | Tokens | Time |
|---|---:|---|
| Typical diff | ~2K | ~0.5–1s |
| Large diff / log | ~10K | ~2–5s |
| Full source file | ~30K | ~7–15s |
| Long document | ~50K | ~12–25s |
| Model context limit | ~128K | ~30–65s |

> **Note:** the default model (Llama 3.2 1B) supports up to 128K tokens. Inputs beyond that require chunking — see roadmap.

### KV cache memory at scale

The KV cache is allocated proportional to input size. At 128K tokens it requires ~2–4 GB of VRAM depending on the model. A 1M-token input would require ~32 GB — not feasible on consumer hardware today without chunking.

## Claude Code integration

### Automatic compression for every prompt (recommended)

One command wires `imptokens` into Claude Code as a `UserPromptSubmit` hook. Every prompt above the threshold is silently compressed before it reaches the model — you don't change anything about how you work.

```bash
imptokens --setup-claude
```

```
✓ Claude Code hook configured
  File:      ~/.claude/settings.json
  Threshold: 500 estimated tokens
  Ratio:     60% of tokens kept

Restart Claude Code for changes to take effect.
```

What it adds to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "",
      "hooks": [{ "type": "command", "command": "/path/to/imptokens --hook-mode --hook-threshold 500 --keep-ratio 0.6" }]
    }]
  }
}
```

Adjust the threshold and ratio:

```bash
# Only compress very large prompts, keep 70%
imptokens --setup-claude --hook-threshold 1000 --keep-ratio 0.7

# Aggressive: compress anything over 200 tokens, keep 50%
imptokens --setup-claude --hook-threshold 200 --keep-ratio 0.5
```

> **Latency note:** the hook adds ~2–4s on Apple Silicon (model cold-start). Only triggers above your threshold.

### Clipboard pre-compression (macOS)

```bash
# 1) Copy text to clipboard
compress-paste        # default keep-ratio 0.5
compress-paste 0.3    # more aggressive
# 2) Paste into Claude — already compressed
```

### Pipe any command output through compression

```bash
cat bigfile.py   | compress-if-large
git diff HEAD~5  | compress-if-large
pytest 2>&1      | compress-if-large
```

Tune behavior:

```bash
export COMPRESS_MIN_CHARS=2000   # only compress if > 2000 chars
export COMPRESS_RATIO=0.5        # keep 50% of tokens
```

### Slash command

```bash
/compress-paste          # compress clipboard, registered by install.sh
```

### Hook mode (raw API)

```bash
echo '{"prompt":"...long text..."}' | imptokens --hook-mode --hook-threshold 500
```

- Claude Code docs: https://docs.anthropic.com/en/docs/claude-code/hooks

## Model guide

Any GGUF model can be used.

| Model | Size | Speed | Quality |
|---|---|---|---|
| `Llama-3.2-1B-Instruct-Q4_K_M` | ~700 MB | Fast | Good default |
| `Llama-3.2-3B-Instruct-Q4_K_M` | ~1.8 GB | Medium | Better semantic retention |
| `Qwen2.5-1.5B-Instruct-Q4_K_M` | ~900 MB | Medium-fast | Good |

Use explicit model selection:

```bash
imptokens --model bartowski/Llama-3.2-3B-Instruct-GGUF --model-file Llama-3.2-3B-Instruct-Q4_K_M.gguf "text"
```

Or local model file:

```bash
imptokens --local-model /path/to/model.gguf "text"
```

## Examples

| File | Description |
|---|---|
| `examples/01_basic.sh` | Basic threshold vs keep-ratio comparison |
| `examples/02_token_viz.py` | Token-level color visualization |
| `examples/03_quality_benchmark.py` | Compression quality benchmark |
| `examples/04_demo.py` | Demo report generation |
| `examples/05_qa_demo.py` | QA preservation demo |

## Contributing

Contributions are welcome. If this project saves you tokens, please star the repo and open an issue or PR.

### Good first contributions

- Add benchmark datasets and report scripts for real-world traces.
- Improve Claude/RTK integration docs and setup robustness.
- Add tests around compression strategy edge cases.
- Add new backend experiments while keeping CLI compatibility.

### Local dev loop

```bash
cargo build
cargo run -- --help
python3 examples/03_quality_benchmark.py
```

## Architecture

```text
imptokens/
├── src/
│   ├── main.rs          # CLI + hook mode
│   ├── lib.rs           # public API
│   ├── compressor.rs    # Compressor + Strategy
│   ├── result.rs        # CompressResult and stats
│   ├── threshold.rs     # fixed_threshold / target_ratio / target_count
│   └── backend/
│       ├── mod.rs       # Backend trait
│       └── llama.rs     # llama.cpp backend (Metal / CUDA / Vulkan / CPU)
└── examples/
```

`Backend` is intentionally abstracted so additional inference backends can be added without changing CLI UX.

## Roadmap

- **Auto-chunking for large inputs** — sliding-window chunking with overlap to support inputs beyond the model's context limit (targeting 1M+ tokens via chunk-and-merge)
- **Persistent daemon mode** — keep the model loaded between calls to eliminate the ~2–4s cold-start overhead in hook mode
- **Streaming mode** (`--stream`) for chunked large inputs with incremental output
- **CoreML backend** — Apple Neural Engine exploration for lower power draw on macOS
- **JSON/JSONL selective field compression** — score and compress individual fields rather than treating JSON as flat text
- **Integrations** — Cursor, VS Code extension, Neovim, GitHub Actions

## License

MIT
