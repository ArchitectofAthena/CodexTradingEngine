#![forbid(unsafe_code)]

//! Exact verification for simulation-only triangular routes.
//! The crate performs bounded arithmetic and deterministic JSON protocol work.
//! It cannot access networks, wallets, signers, schedulers, or capital.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const BPS: f64 = 10_000.0;
const REQUEST_SCHEMA: &str = "delta-repricing-request-v0.1";
const RESPONSE_SCHEMA: &str = "delta-repricing-response-v0.1";

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
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

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
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

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RepricingRequest {
    pub schema_version: String,
    pub request_id: String,
    pub snapshot_sha256: String,
    pub model_sha256: String,
    pub confidence_receipt_id: String,
    pub candidate_id: String,
    pub edges: [EdgeQuote; 3],
    pub gas_penalty_log: f64,
    pub minimum_log_delta: f64,
    pub authority: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RepricingResponse {
    pub schema_version: String,
    pub request_id: String,
    pub snapshot_sha256: String,
    pub model_sha256: String,
    pub confidence_receipt_id: String,
    pub candidate_id: String,
    pub verifier: String,
    pub status: String,
    pub verification: CycleVerification,
    pub authority: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VerificationError {
    InvalidAuthority(String),
    InvalidHash(String),
    InvalidNumber(String),
    InvalidRoute(String),
    InvalidSchema(String),
    MissingField(String),
}

impl std::fmt::Display for VerificationError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidAuthority(message)
            | Self::InvalidHash(message)
            | Self::InvalidNumber(message)
            | Self::InvalidRoute(message)
            | Self::InvalidSchema(message)
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

fn validate_sha256(value: &str, field: &str) -> Result<(), VerificationError> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()) {
        return Err(VerificationError::InvalidHash(format!(
            "{field} must be 64 lowercase hexadecimal characters"
        )));
    }
    Ok(())
}

fn expected_candidate_id(edges: &[EdgeQuote; 3]) -> String {
    let ids = [
        edges[0].edge_id.as_str(),
        edges[1].edge_id.as_str(),
        edges[2].edge_id.as_str(),
    ];
    let seeds = [
        format!("{}|{}|{}", ids[0], ids[1], ids[2]),
        format!("{}|{}|{}", ids[1], ids[2], ids[0]),
        format!("{}|{}|{}", ids[2], ids[0], ids[1]),
    ];
    let canonical = seeds.iter().min().expect("three rotations always exist");
    let digest = format!("{:x}", Sha256::digest(canonical.as_bytes()));
    format!("triangle:{}", &digest[..20])
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

    let edge_ids = [first.edge_id.as_str(), second.edge_id.as_str(), third.edge_id.as_str()];
    if edge_ids[0] == edge_ids[1] || edge_ids[0] == edge_ids[2] || edge_ids[1] == edge_ids[2] {
        return Err(VerificationError::InvalidRoute(
            "triangle requires three distinct edge identifiers".to_string(),
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

pub fn verify_repricing_request(
    request: &RepricingRequest,
) -> Result<RepricingResponse, VerificationError> {
    if request.schema_version != REQUEST_SCHEMA {
        return Err(VerificationError::InvalidSchema(format!(
            "schema_version must be {REQUEST_SCHEMA}"
        )));
    }
    validate_nonempty(&request.request_id, "request_id")?;
    if !request.request_id.starts_with("delta-reprice:") {
        return Err(VerificationError::InvalidSchema(
            "request_id must use the delta-reprice namespace".to_string(),
        ));
    }
    validate_sha256(&request.snapshot_sha256, "snapshot_sha256")?;
    validate_sha256(&request.model_sha256, "model_sha256")?;
    if !request.confidence_receipt_id.starts_with("qaoa-confidence:") {
        return Err(VerificationError::InvalidSchema(
            "confidence_receipt_id must use the qaoa-confidence namespace".to_string(),
        ));
    }
    if request.authority {
        return Err(VerificationError::InvalidAuthority(
            "repricing requests cannot grant authority".to_string(),
        ));
    }

    let expected = expected_candidate_id(&request.edges);
    if request.candidate_id != expected {
        return Err(VerificationError::InvalidHash(format!(
            "candidate_id mismatch: expected {expected}"
        )));
    }

    let verification = verify_triangle(
        [&request.edges[0], &request.edges[1], &request.edges[2]],
        request.gas_penalty_log,
        request.minimum_log_delta,
    )?;

    Ok(RepricingResponse {
        schema_version: RESPONSE_SCHEMA.to_string(),
        request_id: request.request_id.clone(),
        snapshot_sha256: request.snapshot_sha256.clone(),
        model_sha256: request.model_sha256.clone(),
        confidence_receipt_id: request.confidence_receipt_id.clone(),
        candidate_id: request.candidate_id.clone(),
        verifier: "codex-delta-verifier/0.2.0".to_string(),
        status: "verified".to_string(),
        verification,
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

    fn request() -> RepricingRequest {
        let edges = [
            edge("usd-eth", "USD", "ETH", 0.0005),
            edge("eth-btc", "ETH", "BTC", 0.05),
            edge("btc-usd", "BTC", "USD", 41_000.0),
        ];
        RepricingRequest {
            schema_version: REQUEST_SCHEMA.to_string(),
            request_id: "delta-reprice:test".to_string(),
            snapshot_sha256: "a".repeat(64),
            model_sha256: "b".repeat(64),
            confidence_receipt_id: "qaoa-confidence:test".to_string(),
            candidate_id: expected_candidate_id(&edges),
            edges,
            gas_penalty_log: 0.0,
            minimum_log_delta: 0.01,
            authority: false,
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
    fn repricing_protocol_binds_candidate_and_hashes() {
        let response = verify_repricing_request(&request()).unwrap();

        assert_eq!(response.status, "verified");
        assert_eq!(response.snapshot_sha256, "a".repeat(64));
        assert!(response.verification.passes_margin);
        assert!(!response.authority);
        assert!(!response.verification.authority);
    }

    #[test]
    fn repricing_protocol_rejects_candidate_identity_drift() {
        let mut altered = request();
        altered.candidate_id = "triangle:00000000000000000000".to_string();

        let error = verify_repricing_request(&altered).unwrap_err();
        assert!(matches!(error, VerificationError::InvalidHash(_)));
    }

    #[test]
    fn repricing_protocol_rejects_authority_escalation() {
        let mut altered = request();
        altered.authority = true;

        let error = verify_repricing_request(&altered).unwrap_err();
        assert!(matches!(error, VerificationError::InvalidAuthority(_)));
    }

    #[test]
    fn strict_json_rejects_unknown_fields() {
        let mut value = serde_json::to_value(request()).unwrap();
        value["wallet"] = serde_json::json!("forbidden");

        let error = serde_json::from_value::<RepricingRequest>(value).unwrap_err();
        assert!(error.to_string().contains("unknown field"));
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
