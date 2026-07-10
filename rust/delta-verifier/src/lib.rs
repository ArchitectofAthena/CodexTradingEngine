#![forbid(unsafe_code)]

//! Exact, dependency-free verification for simulation-only triangular routes.
//! The crate performs arithmetic only. It cannot access networks, wallets,
//! signers, schedulers, or capital.

const BPS: f64 = 10_000.0;

#[derive(Debug, Clone, PartialEq)]
pub struct EdgeQuote {
    pub edge_id: String,
    pub source_asset: String,
    pub target_asset: String,
    pub quoted_rate: f64,
    pub fee_bps: f64,
    pub slippage_bps: f64,
    pub latency_penalty_bps: f64,
}

impl EdgeQuote {
    pub fn effective_rate(&self) -> Result<f64, VerificationError> {
        validate_nonempty(&self.edge_id, "edge_id")?;
        validate_nonempty(&self.source_asset, "source_asset")?;
        validate_nonempty(&self.target_asset, "target_asset")?;
        if self.source_asset == self.target_asset {
            return Err(VerificationError::InvalidRoute(
                "edge must connect distinct assets".to_string(),
            ));
        }
        if !self.quoted_rate.is_finite() || self.quoted_rate <= 0.0 {
            return Err(VerificationError::InvalidNumber(
                "quoted_rate must be finite and positive".to_string(),
            ));
        }
        for (name, value) in [
            ("fee_bps", self.fee_bps),
            ("slippage_bps", self.slippage_bps),
            ("latency_penalty_bps", self.latency_penalty_bps),
        ] {
            if !value.is_finite() || !(0.0..BPS).contains(&value) {
                return Err(VerificationError::InvalidNumber(format!(
                    "{name} must be finite in [0, 10000)"
                )));
            }
        }

        Ok(self.quoted_rate
            * (1.0 - self.fee_bps / BPS)
            * (1.0 - self.slippage_bps / BPS)
            * (1.0 - self.latency_penalty_bps / BPS))
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct CycleVerification {
    pub edge_ids: [String; 3],
    pub asset_path: [String; 4],
    pub net_multiplier: f64,
    pub net_log_delta: f64,
    pub minimum_log_delta: f64,
    pub profitable: bool,
    pub passes_margin: bool,
    pub authority: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VerificationError {
    InvalidNumber(String),
    InvalidRoute(String),
    MissingField(String),
}

impl std::fmt::Display for VerificationError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidNumber(message)
            | Self::InvalidRoute(message)
            | Self::MissingField(message) => formatter.write_str(message),
        }
    }
}

impl std::error::Error for VerificationError {}

fn validate_nonempty(value: &str, field: &str) -> Result<(), VerificationError> {
    if value.trim().is_empty() {
        return Err(VerificationError::MissingField(format!(
            "{field} is required"
        )));
    }
    Ok(())
}

pub fn verify_triangle(
    edges: [&EdgeQuote; 3],
    gas_penalty_log: f64,
    minimum_log_delta: f64,
) -> Result<CycleVerification, VerificationError> {
    if !gas_penalty_log.is_finite() || gas_penalty_log < 0.0 {
        return Err(VerificationError::InvalidNumber(
            "gas_penalty_log must be finite and non-negative".to_string(),
        ));
    }
    if !minimum_log_delta.is_finite() {
        return Err(VerificationError::InvalidNumber(
            "minimum_log_delta must be finite".to_string(),
        ));
    }

    let [first, second, third] = edges;
    if first.target_asset != second.source_asset
        || second.target_asset != third.source_asset
        || third.target_asset != first.source_asset
    {
        return Err(VerificationError::InvalidRoute(
            "edges do not form a closed directed route".to_string(),
        ));
    }

    let assets = [
        first.source_asset.as_str(),
        first.target_asset.as_str(),
        second.target_asset.as_str(),
    ];
    if assets[0] == assets[1] || assets[0] == assets[2] || assets[1] == assets[2] {
        return Err(VerificationError::InvalidRoute(
            "triangle requires three distinct assets".to_string(),
        ));
    }

    let net_multiplier = first.effective_rate()?
        * second.effective_rate()?
        * third.effective_rate()?;
    let net_log_delta = net_multiplier.ln() - gas_penalty_log;

    Ok(CycleVerification {
        edge_ids: [
            first.edge_id.clone(),
            second.edge_id.clone(),
            third.edge_id.clone(),
        ],
        asset_path: [
            first.source_asset.clone(),
            first.target_asset.clone(),
            second.target_asset.clone(),
            third.target_asset.clone(),
        ],
        net_multiplier,
        net_log_delta,
        minimum_log_delta,
        profitable: net_log_delta > 0.0,
        passes_margin: net_log_delta >= minimum_log_delta,
        authority: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn edge(id: &str, source: &str, target: &str, rate: f64) -> EdgeQuote {
        EdgeQuote {
            edge_id: id.to_string(),
            source_asset: source.to_string(),
            target_asset: target.to_string(),
            quoted_rate: rate,
            fee_bps: 0.0,
            slippage_bps: 0.0,
            latency_penalty_bps: 0.0,
        }
    }

    #[test]
    fn verifies_profitable_triangle_without_authority() {
        let first = edge("usd-eth", "USD", "ETH", 0.0005);
        let second = edge("eth-btc", "ETH", "BTC", 0.05);
        let third = edge("btc-usd", "BTC", "USD", 41_000.0);

        let result = verify_triangle([&first, &second, &third], 0.0, 0.01).unwrap();

        assert!((result.net_multiplier - 1.025).abs() < 1e-12);
        assert!(result.profitable);
        assert!(result.passes_margin);
        assert!(!result.authority);
    }

    #[test]
    fn rejects_broken_route() {
        let first = edge("usd-eth", "USD", "ETH", 0.0005);
        let second = edge("sol-btc", "SOL", "BTC", 0.05);
        let third = edge("btc-usd", "BTC", "USD", 41_000.0);

        let error = verify_triangle([&first, &second, &third], 0.0, 0.0).unwrap_err();
        assert!(matches!(error, VerificationError::InvalidRoute(_)));
    }

    #[test]
    fn proportional_costs_can_remove_profit() {
        let mut first = edge("usd-eth", "USD", "ETH", 0.0005);
        let mut second = edge("eth-btc", "ETH", "BTC", 0.05);
        let mut third = edge("btc-usd", "BTC", "USD", 40_100.0);
        for quote in [&mut first, &mut second, &mut third] {
            quote.fee_bps = 50.0;
            quote.slippage_bps = 50.0;
        }

        let result = verify_triangle([&first, &second, &third], 0.0, 0.0).unwrap();
        assert!(!result.profitable);
        assert!(!result.passes_margin);
    }
}
