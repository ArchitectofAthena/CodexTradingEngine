#![forbid(unsafe_code)]

use codex_delta_verifier::{verify_repricing_request, RepricingRequest};
use serde_json::json;
use std::io::{self, Read};

const MAX_INPUT_BYTES: usize = 64 * 1024;

fn fail(kind: &str, message: &str) -> ! {
    let payload = json!({
        "schema_version": "delta-repricing-error-v0.1",
        "kind": kind,
        "message": message,
        "authority": false
    });
    eprintln!("{}", serde_json::to_string(&payload).expect("error JSON is serializable"));
    std::process::exit(2);
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

    let request: RepricingRequest = match serde_json::from_slice(&input) {
        Ok(request) => request,
        Err(error) => fail("invalid_request_json", &error.to_string()),
    };

    let response = match verify_repricing_request(&request) {
        Ok(response) => response,
        Err(error) => fail("verification_rejected", &error.to_string()),
    };

    match serde_json::to_string(&response) {
        Ok(encoded) => println!("{encoded}"),
        Err(error) => fail("response_serialization_failed", &error.to_string()),
    }
}
