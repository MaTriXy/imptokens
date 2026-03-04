# imptokens

**Semantic token compression for LLM context windows — fast, local, Metal-accelerated.**

Runs a small language model locally to score every token by surprise (log-probability). Predictable tokens — articles, repeated phrases, boilerplate — are dropped. Informative ones are kept. The result is the same meaning in 30–70% fewer tokens.

```
git diff HEAD~5 | imptokens --keep-ratio 0.5 --stats
# tokens: 312/624 kept  (50.0% reduction, 312 saved)
```

---

## How it works

Every token in your text gets a **log-probability** score: how likely was the model to predict this token given everything before it?

- **Low logprob** (e.g. `-8.5`) → token is *surprising* → carries information → **keep**
- **High logprob** (e.g. `-0.1`) → token is *predictable* → adds little → **drop**

```
Input:   The model predicts the next token. The model predicts the next word.
         ─── ───── ──────── ─── ──── ─────  ─── ───── ──────── ─── ──── ────
logprob: BOS  -9.4   -5.1  -1.4 -6.2 -7.7  -1.5 -1.9   -1.8  -.22 -.28 -2.1
kept?:    ✓    ✓      ✓     ✓    ✓    ✓      ✓    ✓      ✓     ✗    ✗    ✓

Output:  The model predicts the next token. The model predicts word.
```

By the second sentence, the model already knows the pattern — so only the novel ending (`word` instead of `token`) is kept.

**Backend:** [llama.cpp](https://github.com/ggerganov/llama.cpp) with Metal GPU acceleration on Apple Silicon. Default model: `Llama-3.2-1B-Instruct-Q4_K_M` (~700 MB, auto-downloaded on first use).

---

## Installation

### Prerequisites

- macOS with Apple Silicon (M1/M2/M3/M4) — Metal GPU required for fast inference
- [Rust](https://rustup.rs/) 1.70+

```bash
# Install Rust if needed
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

### Build & install

```bash
git clone https://github.com/nimhar/imptokens.git
cd imptokens
bash install.sh
```

`install.sh` builds the release binary, copies it to `~/.local/bin/`, and optionally sets up the Claude Code hook.

### Manual build

```bash
cargo build --release
# Binary at: ./target/release/imptokens
```

The model (~700 MB) downloads automatically from HuggingFace on first run and caches at `~/.cache/huggingface/hub/`.

---

## Usage

### Inline text

```bash
imptokens "Your long text here" --stats
```

### From file

```bash
imptokens --file document.txt --keep-ratio 0.5
```

### From stdin (pipe)

```bash
cat bigfile.py | imptokens --keep-ratio 0.6
git diff HEAD~5 | imptokens --stats
curl -s https://example.com/api | imptokens --keep-ratio 0.5
```

---

## All flags

### Input

| Flag | Description |
|------|-------------|
| `[TEXT]` | Positional text argument |
| `-f, --file <PATH>` | Read from file (`-` for stdin) |

### Model

| Flag | Default | Description |
|------|---------|-------------|
| `-m, --model <REPO>` | `bartowski/Llama-3.2-1B-Instruct-GGUF` | HuggingFace repo ID |
| `--model-file <FILE>` | `Llama-3.2-1B-Instruct-Q4_K_M.gguf` | GGUF filename within the repo |
| `--local-model <PATH>` | — | Use a local `.gguf` file (skips download) |

Any GGUF model works. Smaller = faster startup; larger = better compression quality:

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| `Llama-3.2-1B-Instruct-Q4_K_M` | 700 MB | ~1.5s | Good |
| `Llama-3.2-3B-Instruct-Q4_K_M` | 1.8 GB | ~3s | Better |
| `Qwen2.5-1.5B-Instruct-Q4_K_M` | 900 MB | ~2s | Good |

### Compression strategy (pick one)

| Flag | Default | Description |
|------|---------|-------------|
| `-t, --threshold <LOGPROB>` | `-1.0` | Keep tokens where logprob < threshold |
| `-k, --keep-ratio <RATIO>` | — | Keep the N most surprising tokens (0 < ratio ≤ 1) |

**Threshold guide** — lower = more aggressive:

| Threshold | Approx. probability cutoff | Typical reduction |
|-----------|---------------------------|-------------------|
| `-0.5` | p < 61% | 20–40% |
| `-1.0` *(default)* | p < 37% | 30–55% |
| `-1.5` | p < 22% | 45–65% |
| `-2.0` | p < 14% | 55–75% |

**Keep-ratio guide:**

| Ratio | Tokens kept | Good for |
|-------|-------------|----------|
| `0.7` | 70% | Light compression, preserve most detail |
| `0.5` | 50% | Balanced — recommended for most uses |
| `0.3` | 30% | Aggressive — repetitive text, logs |

### Output

| Flag | Description |
|------|-------------|
| `-o, --output-format <FMT>` | `text` (default), `token-ids`, or `json` |
| `-d, --debug` | Full per-token JSON with logprobs and keep/drop decisions |
| `-s, --stats` | Print `n_kept/n_original` stats to stderr |

---

## Quality benchmark

Real results on representative text types (measured with `examples/03_quality_benchmark.py`):

| Text type | Target | Actual reduction | Key-phrase survival |
|-----------|--------|-----------------|---------------------|
| Dense technical prose | 30% | 30.8% | 20% |
| Dense technical prose | 50% | 50.8% | 20% |
| Dense technical prose | 70% | 70.8% | 60% |
| Repetitive documentation | 30% | 31.2% | 60% |
| Repetitive documentation | 50% | 51.2% | 60% |
| Repetitive documentation | 70% | 70.0% | 60% |
| Git diff output | 30% | 30.9% | 75% |
| Git diff output | 50% | 50.5% | **100%** |
| Git diff output | 70% | 70.1% | **100%** |
| Error log / stack trace | 30% | 30.7% | 0% |
| Error log / stack trace | 50% | 51.1% | 60% |
| Error log / stack trace | 70% | 70.5% | 60% |

**Key insight:** Git diffs at 50% ratio preserve 100% of key symbols (`forward`, `embed`, `head`, etc.) while halving token count — the model recognises that diff markers and changed lines are informative, boilerplate lines are not.

**Rule of thumb:** use `--keep-ratio 0.5` for code/diffs, `--keep-ratio 0.7` for dense prose.

Run the benchmark yourself:

```bash
python3 examples/03_quality_benchmark.py
```

Visualise which tokens are kept/dropped:

```bash
python3 examples/02_token_viz.py --ratio 0.5
```

---

## Claude Code integration

- Claude Code hooks docs: https://docs.anthropic.com/en/docs/claude-code/hooks
- RTL/RTK platform (complementary): https://www.rtk-ai.app/

### compress-paste — pre-compress clipboard before sending

```bash
# 1. Copy text (Cmd+C)
compress-paste          # keep 50% (default)
compress-paste 0.3      # keep 30% (more aggressive)
# 2. Paste into Claude (Cmd+V) — compressed text is in clipboard
```

### Automatic bash output compression

When installed, the `install.sh` adds a step to the RTK pre-tool-use hook so that large bash command outputs are semantically compressed before entering Claude's context:

```
cat bigfile.py    →  rtk read bigfile.py | compress-if-large
git diff HEAD~5   →  rtk git diff HEAD~5 | compress-if-large
git log --stat    →  rtk git log --stat  | compress-if-large
```

`compress-if-large` is a no-op for outputs under ~1000 tokens (4000 chars). Tune via environment variables:

```bash
# in ~/.zshrc
export COMPRESS_MIN_CHARS=2000   # compress outputs > ~500 tokens
export COMPRESS_RATIO=0.5        # keep 50% instead of 60%
```

### Slash command inside Claude Code

Type `/compress-paste` in Claude Code to compress your current clipboard via Claude's Bash tool.

### Hook mode (advanced)

The binary includes a `--hook-mode` for direct integration with Claude Code's hook JSON protocol:

```bash
echo '{"prompt":"...long text..."}' | imptokens --hook-mode --hook-threshold 500
```

---

## Examples

See the `examples/` directory:

| File | Description |
|------|-------------|
| `examples/01_basic.sh` | Side-by-side comparison of threshold vs keep-ratio |
| `examples/02_token_viz.py` | Coloured token-by-token visualization with logprobs |
| `examples/03_quality_benchmark.py` | Measures key-phrase survival across text types and ratios |

---

## Roadmap

### Near-term

- [ ] **Streaming mode** — compress chunks as they arrive, no buffering (`--stream`)
- [ ] **Auto-chunking** — transparently split inputs larger than the model's context window
- [ ] **CoreML backend** — Apple Neural Engine via CoreML for even faster inference on M-series chips
- [ ] **Interactive mode** — show tokens before committing, let user adjust threshold interactively
- [ ] **JSON/JSONL input** — compress only the `content` fields of JSON objects, leave structure intact
- [ ] **`--min-tokens` guard** — skip compression entirely when input is below a token count

### Integrations

- [ ] **Cursor** — MCP server that hooks into Cursor's context pipeline and compresses file reads before they reach the model
- [ ] **VS Code extension** — right-click → "Copy compressed" in the editor
- [ ] **GitHub Actions** — compress PR diffs before sending to AI code review (`imptokens --file diff.patch | ai-review`)
- [ ] **Neovim plugin** — compress visual selection, replace in-buffer
- [ ] **HTTP server mode** — `imptokens serve --port 8080` for use as a sidecar in any pipeline
- [ ] **antigravity** — integration with [antigravity](https://github.com/antigravityai) agentic pipelines

### Quality & models

- [ ] **HuggingFace Transformers backend** — use any safetensors model without converting to GGUF
- [ ] **Sentence-level granularity** — score and drop at sentence level for better coherence
- [ ] **Perplexity output** — `--output-format perplexity` for use as a standalone text quality metric
- [ ] **Fine-tuned compression models** — train a model specifically to predict which tokens are important for downstream LLM comprehension
- [ ] **Context-aware compression** — preserve tokens that are relevant to a specific query (`--query "what is the return value?"`)

---

## Architecture

```
imptokens/
├── src/
│   ├── main.rs          # CLI (clap) + hook mode
│   ├── lib.rs           # public API
│   ├── compressor.rs    # Compressor struct, Strategy enum
│   ├── result.rs        # CompressResult (token ids, bytes, logprobs, mask)
│   ├── threshold.rs     # fixed_threshold / target_ratio / target_count
│   └── backend/
│       ├── mod.rs       # Backend trait (score, decode, token_to_bytes)
│       └── llama.rs     # LlamaCppBackend (Metal GPU via llama-cpp-2 crate)
└── examples/
    ├── 01_basic.sh
    ├── 02_token_viz.py
    └── 03_quality_benchmark.py
```

The `Backend` trait makes it straightforward to add new inference backends:

```rust
pub trait Backend: Send + Sync {
    fn load(&mut self, model_path: &Path) -> anyhow::Result<()>;
    fn score(&self, text: &str) -> anyhow::Result<ScoredTokens>;
    fn token_to_bytes(&self, token_id: u32) -> anyhow::Result<Vec<u8>>;
}
```

---

## License

MIT
