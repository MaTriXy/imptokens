use std::collections::HashSet;

/// Keep tokens where `logprob < threshold` (lower = more surprising = keep).
/// The first token (logprob = None) is always kept.
pub fn fixed_threshold(logprobs: &[Option<f32>], threshold: f32) -> Vec<bool> {
    logprobs.iter().map(|lp| lp.map_or(true, |v| v < threshold)).collect()
}

/// Keep the `keep_ratio` most surprising fraction of scored tokens.
/// The first token is always kept on top of the ratio.
pub fn target_ratio(logprobs: &[Option<f32>], keep_ratio: f32) -> Vec<bool> {
    let scored: Vec<(usize, f32)> = logprobs
        .iter()
        .enumerate()
        .filter_map(|(i, lp)| lp.map(|v| (i, v)))
        .collect();

    let n_keep = ((scored.len() as f32 * keep_ratio).round() as usize).max(1).min(scored.len());

    let mut sorted = scored.clone();
    sorted.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
    let keep_set: HashSet<usize> = sorted.iter().take(n_keep).map(|(i, _)| *i).collect();

    logprobs
        .iter()
        .enumerate()
        .map(|(i, lp)| lp.is_none() || keep_set.contains(&i))
        .collect()
}

/// Keep exactly `n_keep` of the most surprising scored tokens.
/// The first token is always kept on top of `n_keep`.
pub fn target_count(logprobs: &[Option<f32>], n_keep: usize) -> Vec<bool> {
    let scored: Vec<(usize, f32)> = logprobs
        .iter()
        .enumerate()
        .filter_map(|(i, lp)| lp.map(|v| (i, v)))
        .collect();

    let n_keep = n_keep.min(scored.len());
    let mut sorted = scored.clone();
    sorted.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
    let keep_set: HashSet<usize> = sorted.iter().take(n_keep).map(|(i, _)| *i).collect();

    logprobs
        .iter()
        .enumerate()
        .map(|(i, lp)| lp.is_none() || keep_set.contains(&i))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_threshold_always_keeps_first() {
        let lps = vec![None, Some(-0.5_f32), Some(-2.0), Some(-0.1)];
        let mask = fixed_threshold(&lps, -1.0);
        // first: None → keep; -0.5 > -1.0 → drop; -2.0 < -1.0 → keep; -0.1 > -1.0 → drop
        assert_eq!(mask, vec![true, false, true, false]);
    }

    #[test]
    fn target_ratio_keeps_fraction() {
        let lps = vec![None, Some(-3.0_f32), Some(-1.0), Some(-2.0), Some(-0.5)];
        let mask = target_ratio(&lps, 0.5);
        // 4 scored tokens, keep 2 most surprising: -3.0 (idx 1) and -2.0 (idx 3)
        assert_eq!(mask, vec![true, true, false, true, false]);
    }
}
