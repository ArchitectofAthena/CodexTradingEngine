# Ethereum Sepolia PublicNode block-number candidate v0.1

## Purpose

Review a second Ethereum Sepolia observation source for Gate 1A.1 without silently adding it to the active Gate 1 runtime.

```text
published endpoint metadata
+ Ethereum JSON-RPC method contract
+ exact content-addressed request body
+ candidate provenance classification
→ HOLD_TERMS_REVIEW
→ bounded operator capture proposal
→ human eligibility review
```

## Candidate

```yaml
source_id: ethereum-sepolia-publicnode-blocknumber-v0-1
network: Ethereum Sepolia
chain_id: "11155111"
operator: PublicNode
host: ethereum-sepolia-rpc.publicnode.com
endpoint: https://ethereum-sepolia-rpc.publicnode.com
transport_method: POST
rpc_method: eth_blockNumber
request_body_sha256: 0094f94313d26ab04a2c854b4af649acb9193cebbc2ac237110eacbdfcb2a427
provenance_group: publicnode-ethereum-sepolia-jsonrpc
relationship_to_primary: DISTINCT_OPERATOR_CANDIDATE
current_decision: HOLD_TERMS_REVIEW
```

The exact request body described by this candidate is:

```json
{"id":1,"jsonrpc":"2.0","method":"eth_blockNumber","params":[]}
```

No arbitrary JSON-RPC method, parameter, URL, host, identifier, header, credential, or request body is admitted by this artifact.

## Source evidence

PublicNode currently publishes the Ethereum Sepolia endpoint `https://ethereum-sepolia-rpc.publicnode.com` on its Sepolia gateway page.

Ethereum's JSON-RPC documentation defines `eth_blockNumber` as returning the number of the most recent block known to the client. The response quantity is hexadecimal and `0x`-prefixed.

These facts establish a plausible candidate interface. They do not establish:

- uptime or response behavior at the time of an approved run;
- rate limits applicable to this exact endpoint;
- terms compatibility;
- upstream node or infrastructure independence;
- agreement with Blockscout;
- eligibility for active Gate 1 capture.

## Relationship to the primary source

The active source is the Blockscout Ethereum Sepolia explorer instance. The candidate is presented by PublicNode through a JSON-RPC interface and therefore has a distinct visible operator and interface.

That is only a **distinct-operator candidate classification**. It is not proof of fully independent upstream infrastructure. Shared network membership is expected because both observe Ethereum Sepolia. Shared hosting, upstream nodes, proxy infrastructure, or data derivation would require a concentration HOLD.

## Why it remains on HOLD

```yaml
terms_review: PENDING
live_capture_status: NOT_RUN
capture_receipt: null
eligible: false
capture_authorized: false
```

The current execution shell could not resolve external DNS, so no live probe was performed while creating this review. That limitation is preserved as evidence rather than painted over.

The active Gate 1 runtime is also intentionally GET/HEAD-only. This candidate uses an exact POST body and cannot inherit runtime eligibility from the existing explorer source.

## Promotion requirements

Before `READY_FOR_ELIGIBILITY_REVIEW`:

1. review the endpoint's current terms, privacy posture, and rate-limit guidance;
2. determine whether PublicNode's upstream infrastructure is independent of Blockscout's source path;
3. implement or approve a separate bounded JSON-RPC capture membrane;
4. permit exactly one explicit operator-invoked request;
5. pin the public IP after DNS validation and reject mixed or non-public resolution;
6. require TLS, exact host, exact URL, exact POST body, and no redirects;
7. cap timeout and response size;
8. reject JSON-RPC errors, identifier drift, malformed hexadecimal quantities, extra authority fields, and response ambiguity;
9. emit an immutable capture receipt;
10. route the result through human eligibility review.

Eligibility review still would not produce source consensus. Two contemporaneous observations must then enter the existing offline consensus evaluator, which preserves disagreement and never averages sources into an executable quote.

## Authority boundary

```yaml
artifact_is_command: false
authority: false
network_capture_performed: false
capture_authorized: false
eligible: false
may_generate_live_proposal: false
may_execute: false
may_sign: false
may_submit_transaction: false
may_access_wallet: false
may_move_capital: false
automatic_promotion: false
human_promotion_required: true
```

> A second URL is not a quorum. A distinct logo is not independence. Evidence earns the next review, never authority.
