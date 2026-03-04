use serde::Serialize;

/// Output of a single compression operation.
///
/// Token bytes are decoded eagerly at creation time so this struct is
/// self-contained (no backend reference needed).
pub struct CompressResult {
    pub original_text: String,
    pub token_ids: Vec<u32>,
    /// Raw bytes for each token (byte-piece tokenizers may split Unicode across tokens).
    token_bytes: Vec<Vec<u8>>,
    pub logprobs: Vec<Option<f32>>,
    pub mask: Vec<bool>,
}

impl CompressResult {
    pub fn new(
        original_text: String,
        token_ids: Vec<u32>,
        token_bytes: Vec<Vec<u8>>,
        logprobs: Vec<Option<f32>>,
        mask: Vec<bool>,
    ) -> Self {
        Self { original_text, token_ids, token_bytes, logprobs, mask }
    }

    pub fn n_original(&self) -> usize {
        self.token_ids.len()
    }

    pub fn n_kept(&self) -> usize {
        self.mask.iter().filter(|&&b| b).count()
    }

    pub fn compression_ratio(&self) -> f64 {
        if self.n_original() == 0 { 0.0 } else { self.n_kept() as f64 / self.n_original() as f64 }
    }

    pub fn to_token_ids(&self) -> Vec<u32> {
        self.token_ids
            .iter()
            .zip(&self.mask)
            .filter_map(|(&id, &keep)| if keep { Some(id) } else { None })
            .collect()
    }

    /// Assemble kept tokens' raw bytes then convert to UTF-8.
    pub fn to_text(&self) -> String {
        let bytes: Vec<u8> = self
            .token_bytes
            .iter()
            .zip(&self.mask)
            .filter_map(|(b, &keep)| if keep { Some(b.as_slice()) } else { None })
            .flat_map(|b| b.iter().copied())
            .collect();
        String::from_utf8_lossy(&bytes).into_owned()
    }

    pub fn to_dict(&self) -> serde_json::Value {
        let compressed_text = self.to_text();
        let tokens: Vec<serde_json::Value> = self
            .token_ids
            .iter()
            .zip(&self.token_bytes)
            .zip(&self.logprobs)
            .zip(&self.mask)
            .map(|(((&id, bytes), lp), &kept)| {
                let text = String::from_utf8_lossy(bytes).into_owned();
                serde_json::json!({
                    "id": id,
                    "text": text,
                    "logprob": lp,
                    "kept": kept,
                })
            })
            .collect();

        serde_json::json!({
            "original_text": self.original_text,
            "compressed_text": compressed_text,
            "n_original": self.n_original(),
            "n_kept": self.n_kept(),
            "compression_ratio": self.compression_ratio(),
            "tokens": tokens,
        })
    }
}

/// Token-level stats for `--stats` output (written to stderr).
#[derive(Serialize)]
pub struct CompressionStats {
    pub n_original: usize,
    pub n_kept: usize,
    pub compression_ratio: f64,
    pub tokens_saved: usize,
}

impl From<&CompressResult> for CompressionStats {
    fn from(r: &CompressResult) -> Self {
        Self {
            n_original: r.n_original(),
            n_kept: r.n_kept(),
            compression_ratio: r.compression_ratio(),
            tokens_saved: r.n_original() - r.n_kept(),
        }
    }
}
