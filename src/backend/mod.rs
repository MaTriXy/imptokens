use std::path::Path;

/// A scored set of tokens returned by the backend.
pub struct ScoredTokens {
    /// Token IDs in order.
    pub ids: Vec<u32>,
    /// Per-token log-probabilities; `logprobs[0]` is always `None` (no context).
    pub logprobs: Vec<Option<f32>>,
}

/// Abstraction over an LLM inference backend.
pub trait Backend: Send + Sync {
    /// Load the model from a local GGUF file.
    fn load(&mut self, model_path: &Path) -> anyhow::Result<()>;

    /// Tokenize `text` and compute per-token log-probabilities via a single
    /// forward pass.
    fn score(&self, text: &str) -> anyhow::Result<ScoredTokens>;

    /// Decode a single token ID to its raw bytes (may be partial UTF-8).
    fn token_to_bytes(&self, token_id: u32) -> anyhow::Result<Vec<u8>>;

    /// Decode a slice of token IDs to a UTF-8 string.
    fn decode(&self, token_ids: &[u32]) -> anyhow::Result<String> {
        let mut bytes = Vec::new();
        for &id in token_ids {
            bytes.extend(self.token_to_bytes(id)?);
        }
        Ok(String::from_utf8_lossy(&bytes).into_owned())
    }

    /// Score multiple texts; default is a sequential loop.
    fn batch_score(&self, texts: &[&str]) -> anyhow::Result<Vec<ScoredTokens>> {
        texts.iter().map(|t| self.score(t)).collect()
    }
}

pub mod llama;
pub use llama::LlamaCppBackend;
