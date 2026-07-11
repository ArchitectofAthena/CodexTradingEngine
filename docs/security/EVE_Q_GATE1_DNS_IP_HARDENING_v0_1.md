# EVE_Q++ Gate 1 DNS and IP-Class Hardening v0.1

## Purpose

The Gate 1 pilot must not follow a reviewed hostname into a private, loopback, link-local, multicast, reserved, or unspecified address space.

This hardening layer adds a fail-closed DNS membrane before and after each bounded read-only capture.

## Enforced rules

A pilot source must:

- use HTTPS;
- use port 443;
- use a reviewed DNS hostname rather than an IP literal;
- match the exact source allowlist;
- resolve to at least one address;
- resolve only to globally routable addresses;
- preserve the same resolved address set between preflight and post-capture verification.

Any mixed public/private result is rejected in full. The public address does not rescue the private one.

## Rejected address classes

The guard rejects:

- private addresses;
- loopback addresses;
- link-local addresses;
- multicast addresses;
- reserved addresses;
- unspecified addresses;
- invalid resolver output.

Both IPv4 and IPv6 are checked.

## Resolution receipt

A successful preflight emits a content-addressed `Gate1ResolutionReceipt` containing:

- source ID and reviewed URI;
- reviewed hostname and port;
- sorted unique resolved addresses;
- a canonical hash of the address set;
- producer commit;
- pilot gate posture;
- explicit non-authority fields.

The launcher re-resolves the reviewed host after capture and compares the address set to the preflight receipt. A mismatch fails closed and creates a rollback receipt.

## Honest boundary

The current implementation provides:

```text
preflight public-address validation
→ bounded HTTPS capture
→ post-capture public-address validation
→ address-set drift detection
```

It does not claim transport-level IP pinning inside the Python HTTPS connection. A later hardening layer may pin the selected IP while preserving TLS hostname verification. Until then, the pre/post guard is evidence-producing drift detection rather than a claim of perfect rebinding immunity.

## Authority posture

DNS success never grants authority:

```json
{
  "artifact_is_command": false,
  "authority": false,
  "human_promotion_required": true,
  "may_generate_live_proposal": false,
  "may_execute": false,
  "may_move_capital": false
}
```

Gate 1 remains pilot-only. Gate 2–6 remain locked.
