#![forbid(unsafe_code)]

use codex_delta_verifier::{verify_repricing_request, EdgeQuote, RepricingRequest};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::io::{self, Read};

const BPS: f64 = 10_000.0;
const MAX_INPUT_BYTES: usize = 64 * 1024;
const REQUEST_SCHEMA: &str = "flash-liquidity-request-v0.1";
const RESPONSE_SCHEMA: &str = "flash-liquidity-response-v0.1";

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct FlashLiquidityRequest {
    schema_version: String,
    request_id: String,
    snapshot_sha256: String,
    model_sha256: String,
    confidence_receipt_id: String,
    flash_candidate_id: String,
    route_candidate_id: String,
    edges: [EdgeQuote; 3],
    gas_penalty_log: f64,
    provider_id: String,
    borrowed_asset: String,
    amount_bucket_id: String,
    principal_amount: f64,
    provider_fee_bps: f64,
    available_capacity: f64,
    minimum_net_profit: f64,
    authority: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct FlashLiquidityVerification {
    route_net_log_delta: f64,
    route_output_amount: f64,
    repayment_amount: f64,
    net_profit: f64,
    capacity_ok: bool,
    borrowed_asset_matches_route: bool,
    repayment_feasible: bool,
    authority: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct FlashLiquidityResponse {
    schema_version: String,
    request_id: String,
    snapshot_sha256: String,
    model_sha256: String,
    confidence_receipt_id: String,
    flash_candidate_id: String,
    route_candidate_id: String,
    verifier: String,
    status: String,
    verification: FlashLiquidityVerification,
    authority: bool,
}

fn fail(kind: &str, message: &str) -> ! {
    let payload = json!({
        "schema_version": "flash-liquidity-error-v0.1",
        "kind": kind,
        "message": message,
        "authority": false
    });
    eprintln!("{}", serde_json::to_string(&payload).expect("error JSON is serializable"));
    std::process::exit(2);
}

fn require_prefix(value: &str, prefix: &str, field: &str) -> Result<(), String> {
    if !value.starts_with(prefix) {
        return Err(format!("{field} must use the {prefix} namespace"));
    }
    Ok(())
}

fn require_sha256(value: &str, field: &str) -> Result<(), String> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(format!(
            "{field} must be 64 lowercase hexadecimal characters"
        ));
    }
    Ok(())
}

fn expected_flash_candidate_id(request: &FlashLiquidityRequest) -> String {
    let seed = format!(
        "{}|{}|{}",
        request.route_candidate_id, request.provider_id, request.amount_bucket_id
    );
    let digest = format!("{:x}", Sha256::digest(seed.as_bytes()));
    format!("flash-geometry:{}", &digest[..20])
}

fn verify(request: &FlashLiquidityRequest) -> Result<FlashLiquidityResponse, String> {
    if request.schema_version != REQUEST_SCHEMA {
        return Err(format!("schema_version must be {REQUEST_SCHEMA}"));
    }
    require_prefix(&request.request_id, "flash-verify:", "request_id")?;
    require_sha256(&request.snapshot_sha256, "snapshot_sha256")?;
    require_sha256(&request.model_sha256, "model_sha256")?;
    require_prefix(
        &request.confidence_receipt_id,
        "qaoa-confidence:",
        "confidence_receipt_id",
    )?;
    require_prefix(
        &request.flash_candidate_id,
        "flash-geometry:",
        "flash_candidate_id",
    )?;
    require_prefix(
        &request.route_candidate_id,
        "triangle:",
        "route_candidate_id",
    )?;
    require_prefix(&request.provider_id, "flash-provider:", "provider_id")?;
    require_prefix(
        &request.amount_bucket_id,
        "flash-bucket:",
        "amount_bucket_id",
    )?;
    if request.authority {
        return Err("flash-liquidity requests cannot grant authority".to_string());
    }
    if request.flash_candidate_id != expected_flash_candidate_id(request) {
        return Err("flash_candidate_id does not match route/provider/bucket identity".to_string());
    }
    if !request.principal_amount.is_finite() || request.principal_amount <= 0.0 {
        return Err("principal_amount must be finite and positive".to_string());
    }
    if !request.available_capacity.is_finite() || request.available_capacity <= 0.0 {
        return Err("available_capacity must be finite and positive".to_string());
    }
    if !request.provider_fee_bps.is_finite()
        || !(0.0..BPS).contains(&request.provider_fee_bps)
    {
        return Err("provider_fee_bps must be finite in [0, 10000)".to_string());
    }
    if !request.minimum_net_profit.is_finite() || request.minimum_net_profit < 0.0 {
        return Err("minimum_net_profit must be finite and non-negative".to_string());
    }

    let route_request = RepricingRequest {
        schema_version: "delta-repricing-request-v0.1".to_string(),
        request_id: format!("delta-reprice:embedded:{}", request.request_id),
        snapshot_sha256: request.snapshot_sha256.clone(),
        model_sha256: request.model_sha256.clone(),
        confidence_receipt_id: request.confidence_receipt_id.clone(),
        candidate_id: request.route_candidate_id.clone(),
        edges: request.edges.clone(),
        gas_penalty_log: request.gas_penalty_log,
        minimum_log_delta: f64::MIN_POSITIVE.ln(),
        authority: false,
    };
    let route_response = verify_repricing_request(&route_request).map_err(|error| error.to_string())?;
    let route = route_response.verification;

    let borrowed_asset_matches_route = request.borrowed_asset == request.edges[0].source_asset
        && request.borrowed_asset == request.edges[2].target_asset;
    let capacity_ok = request.principal_amount <= request.available_capacity;
    let route_output_amount = request.principal_amount * route.net_log_delta.exp();
    let repayment_amount = request.principal_amount * (1.0 + request.provider_fee_bps / BPS);
    let net_profit = route_output_amount - repayment_amount;
    let repayment_feasible = borrowed_asset_matches_route
        && capacity_ok
        && route_output_amount >= repayment_amount
        && net_profit >= request.minimum_net_profit;

    Ok(FlashLiquidityResponse {
        schema_version: RESPONSE_SCHEMA.to_string(),
        request_id: request.request_id.clone(),
        snapshot_sha256: request.snapshot_sha256.clone(),
        model_sha256: request.model_sha256.clone(),
        confidence_receipt_id: request.confidence_receipt_id.clone(),
        flash_candidate_id: request.flash_candidate_id.clone(),
        route_candidate_id: request.route_candidate_id.clone(),
        verifier: "codex-flash-liquidity-verifier/0.1.0".to_string(),
        status: "verified".to_string(),
        verification: FlashLiquidityVerification {
            route_net_log_delta: route.net_log_delta,
            route_output_amount,
            repayment_amount,
            net_profit,
            capacity_ok,
            borrowed_asset_matches_route,
            repayment_feasible,
            authority: false,
        },
        authority: false,
    })
}

fn main() {
    let mut input = Vec::new();
    if let Err(error) = io::stdin()
        .take((MAX_INPUT_BYTES + 1) as u64)
        .read_to_end(&mut input)
    {
        fail("stdin_read_failed", &error.to_string());
    }
    if input.len() > MAX_INPUT_BYTES {
        fail("payload_too_large", "request exceeds 65536 bytes");
    }
    let request: FlashLiquidityRequest = match serde_json::from_slice(&input) {
        Ok(request) => request,
        Err(error) => fail("invalid_request_json", &error.to_string()),
    };
    let response = match verify(&request) {
        Ok(response) => response,
        Err(error) => fail("verification_rejected", &error),
    };
    match serde_json::to_string(&response) {
        Ok(encoded) => println!("{encoded}"),
        Err(error) => fail("response_serialization_failed", &error.to_string()),
    }
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

    fn request() -> FlashLiquidityRequest {
        let edges = [
            edge("usd-eth", "USD", "ETH", 0.0005),
            edge("eth-btc", "ETH", "BTC", 0.05),
            edge("btc-usd", "BTC", "USD", 41_000.0),
        ];
        let route_seed = "btc-usd|usd-eth|eth-btc";
        let route_digest = format!("{:x}", Sha256::digest(route_seed.as_bytes()));
        let route_candidate_id = format!("triangle:{}", &route_digest[..20]);
        let provider_id = "flash-provider:test".to_string();
        let bucket_id = "flash-bucket:usd-1000".to_string();
        let flash_seed = format!("{route_candidate_id}|{provider_id}|{bucket_id}");
        let flash_digest = format!("{:x}", Sha256::digest(flash_seed.as_bytes()));
        FlashLiquidityRequest {
            schema_version: REQUEST_SCHEMA.to_string(),
            request_id: "flash-verify:test".to_string(),
            snapshot_sha256: "a".repeat(64),
            model_sha256: "b".repeat(64),
            confidence_receipt_id: "qaoa-confidence:test".to_string(),
            flash_candidate_id: format!("flash-geometry:{}", &flash_digest[..20]),
            route_candidate_id,
            edges,
            gas_penalty_log: 0.0,
            provider_id,
            borrowed_asset: "USD".to_string(),
            amount_bucket_id: bucket_id,
            principal_amount: 1_000.0,
            provider_fee_bps: 9.0,
            available_capacity: 10_000.0,
            minimum_net_profit: 1.0,
            authority: false,
        }
    }

    #[test]
    fn verifies_capacity_and_repayment_without_authority() {
        let response = verify(&request()).unwrap();
        assert!(response.verification.capacity_ok);
        assert!(response.verification.borrowed_asset_matches_route);
        assert!(response.verification.repayment_feasible);
        assert!(response.verification.net_profit > 0.0);
        assert!(!response.authority);
        assert!(!response.verification.authority);
    }

    #[test]
    fn rejects_candidate_identity_drift() {
        let mut altered = request();
        altered.flash_candidate_id = "flash-geometry:00000000000000000000".to_string();
        assert!(verify(&altered).is_err());
    }

    #[test]
    fn reports_over_capacity_as_infeasible() {
        let mut altered = request();
        altered.available_capacity = 500.0;
        let response = verify(&altered).unwrap();
        assert!(!response.verification.capacity_ok);
        assert!(!response.verification.repayment_feasible);
    }

    #[test]
    fn rejects_authority_escalation() {
        let mut altered = request();
        altered.authority = true;
        assert!(verify(&altered).is_err());
    }
}
