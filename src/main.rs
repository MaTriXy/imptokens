use std::io::{self, Read};
use std::path::PathBuf;

use anyhow::{Context, bail};
use clap::{Parser, ValueEnum};

/// 100 MB — hard cap on stdin to prevent OOM from unbounded input.
const MAX_INPUT_BYTES: u64 = 100 * 1024 * 1024;

use imptokens::{
    Compressor, Strategy,
    backend::LlamaCppBackend,
};

// ─── CLI definition ──────────────────────────────────────────────────────────

/// Fast logprob-based token compression (llama.cpp + Metal).
#[derive(Parser)]
#[command(version, about)]
struct Cli {
    /// Text to compress (mutually exclusive with --file).
    text: Option<String>,

    /// Read input from file ('-' for stdin).
    #[arg(short, long, value_name = "PATH")]
    file: Option<String>,

    // ── Model ─────────────────────────────────────────────────────────────
    /// HuggingFace repo id (e.g. bartowski/Llama-3.2-1B-Instruct-GGUF).
    #[arg(short, long, default_value = "bartowski/Llama-3.2-1B-Instruct-GGUF")]
    model: String,

    /// GGUF filename within the repo.
    #[arg(long, default_value = "Llama-3.2-1B-Instruct-Q4_K_M.gguf")]
    model_file: String,

    /// Use a local model file instead of downloading from HuggingFace.
    #[arg(long, value_name = "PATH")]
    local_model: Option<PathBuf>,

    // ── Strategy (mutually exclusive) ─────────────────────────────────────
    /// Keep tokens whose logprob is below this threshold [default: -1.0].
    #[arg(short, long, value_name = "LOGPROB")]
    threshold: Option<f32>,

    /// Keep this fraction of the most surprising tokens (0 < ratio ≤ 1).
    #[arg(short, long, value_name = "RATIO")]
    keep_ratio: Option<f32>,

    // ── Output ────────────────────────────────────────────────────────────
    #[arg(short, long = "output-format", default_value = "text")]
    output_format: OutputFormat,

    /// Print full per-token JSON (overrides --output-format).
    #[arg(short, long)]
    debug: bool,

    /// Print compression stats to stderr.
    #[arg(short, long)]
    stats: bool,

    // ── Hook mode ─────────────────────────────────────────────────────────
    /// Run as a Claude Code UserPromptSubmit hook: read JSON from stdin,
    /// compress if above --hook-threshold tokens, write hook JSON to stdout.
    #[arg(long)]
    hook_mode: bool,

    /// Minimum estimated token count before compressing in hook mode.
    #[arg(long, default_value_t = 500)]
    hook_threshold: usize,
}

#[derive(Clone, ValueEnum)]
enum OutputFormat {
    Text,
    TokenIds,
    Json,
}

// ─── Entry point ─────────────────────────────────────────────────────────────

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    if cli.hook_mode {
        return run_hook(&cli);
    }

    // Validate strategy flags
    if cli.threshold.is_some() && cli.keep_ratio.is_some() {
        bail!("--threshold and --keep-ratio are mutually exclusive");
    }

    // Read input
    let text = read_input(&cli)?;
    if text.trim().is_empty() {
        bail!("input text is empty");
    }

    // Build compressor
    let mut compressor = build_compressor(&cli)?;
    let model_path = resolve_model(&cli)?;
    compressor.load(&model_path)?;

    // Compress
    let result = compressor.compress(&text)?;

    // Stats to stderr
    if cli.stats {
        let stats = imptokens::result::CompressionStats::from(&result);
        eprintln!(
            "tokens: {}/{} kept  ({:.1}% reduction, {} saved)",
            result.n_kept(),
            result.n_original(),
            (1.0 - result.compression_ratio()) * 100.0,
            result.n_original() - result.n_kept(),
        );
        let _ = stats; // already printed above
    }

    // Output
    if cli.debug {
        println!("{}", serde_json::to_string_pretty(&result.to_dict())?);
    } else {
        match cli.output_format {
            OutputFormat::Text => println!("{}", result.to_text()),
            OutputFormat::TokenIds => {
                let ids: Vec<String> = result.to_token_ids().iter().map(|i| i.to_string()).collect();
                println!("{}", ids.join(" "));
            }
            OutputFormat::Json => {
                let j = serde_json::json!({
                    "original_text": result.original_text,
                    "compressed_text": result.to_text(),
                    "n_original": result.n_original(),
                    "n_kept": result.n_kept(),
                    "compression_ratio": result.compression_ratio(),
                });
                println!("{}", serde_json::to_string_pretty(&j)?);
            }
        }
    }

    Ok(())
}

// ─── Hook mode ───────────────────────────────────────────────────────────────

/// Claude Code UserPromptSubmit hook.
///
/// Reads JSON from stdin, compresses the prompt if it exceeds
/// `--hook-threshold` estimated tokens, then writes hook output JSON to stdout.
///
/// Input:  `{"prompt": "...", "session_id": "...", ...}`
/// Output: `{}` (no-op) or `{"hookSpecificOutput": {"hookOutputText": "..."}}`
fn run_hook(cli: &Cli) -> anyhow::Result<()> {
    // Read stdin (bounded to prevent OOM from malicious/accidental huge input).
    let mut stdin_buf = String::new();
    io::stdin()
        .take(MAX_INPUT_BYTES)
        .read_to_string(&mut stdin_buf)
        .context("failed to read stdin")?;

    let input: serde_json::Value = serde_json::from_str(&stdin_buf).unwrap_or_default();
    let prompt = match input.get("prompt").and_then(|v| v.as_str()) {
        Some(p) => p,
        None => {
            // Not a UserPromptSubmit event or no prompt field — pass through.
            println!("{{}}");
            return Ok(());
        }
    };

    // Rough token estimate: ~4 chars per token
    let estimated_tokens = prompt.len() / 4;
    if estimated_tokens < cli.hook_threshold {
        println!("{{}}");
        return Ok(());
    }

    // Compress with conservative ratio (keep 60% — light, fast).
    let strategy = Strategy::TargetRatio(cli.keep_ratio.unwrap_or(0.6));
    let backend = LlamaCppBackend::new().context("failed to create backend")?;
    let mut compressor = Compressor::new(Box::new(backend), strategy);
    let model_path = resolve_model(cli)?;
    compressor.load(&model_path)?;

    let result = compressor.compress(prompt)?;
    let compressed = result.to_text();
    let saved_pct = (1.0 - result.compression_ratio()) * 100.0;

    // Return hook output: inject compressed prompt as context annotation.
    let hook_text = format!(
        "[imptokens: prompt compressed {:.0}% ({}/{} tokens kept)]\n{}",
        saved_pct,
        result.n_kept(),
        result.n_original(),
        compressed,
    );

    let output = serde_json::json!({
        "hookSpecificOutput": {
            "hookOutputText": hook_text,
        }
    });
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

fn build_compressor(cli: &Cli) -> anyhow::Result<Compressor> {
    let strategy = if let Some(r) = cli.keep_ratio {
        if !(0.0 < r && r <= 1.0) {
            bail!("--keep-ratio must be in (0, 1]");
        }
        Strategy::TargetRatio(r)
    } else {
        Strategy::FixedThreshold(cli.threshold.unwrap_or(-1.0))
    };

    let backend = LlamaCppBackend::new().context("failed to initialise llama.cpp backend")?;
    Ok(Compressor::new(Box::new(backend), strategy))
}

fn resolve_model(cli: &Cli) -> anyhow::Result<PathBuf> {
    if let Some(p) = &cli.local_model {
        return Ok(p.clone());
    }
    download_model(&cli.model, &cli.model_file)
}

fn download_model(repo_id: &str, filename: &str) -> anyhow::Result<PathBuf> {
    use hf_hub::api::sync::Api;
    eprintln!("fetching model {repo_id}/{filename} (cached after first download)…");
    let api = Api::new().context("failed to create HuggingFace API client")?;
    let hf_repo = api.model(repo_id.to_string());
    let path = hf_repo.get(filename).with_context(|| format!("failed to download {filename}"))?;
    Ok(path)
}

fn read_input(cli: &Cli) -> anyhow::Result<String> {
    if let Some(text) = &cli.text {
        return Ok(text.clone());
    }
    if let Some(file) = &cli.file {
        if file == "-" {
            let mut buf = String::new();
            io::stdin()
                .take(MAX_INPUT_BYTES)
                .read_to_string(&mut buf)
                .context("failed to read stdin")?;
            return Ok(buf);
        }
        return std::fs::read_to_string(file)
            .with_context(|| format!("failed to read file {file}"));
    }
    // Fall back to stdin if no positional text and no --file
    let mut buf = String::new();
    io::stdin()
        .take(MAX_INPUT_BYTES)
        .read_to_string(&mut buf)
        .context("failed to read stdin")?;
    Ok(buf)
}
