# EVE_Q++ Gate 1 Synthetic Test Matrix v0.1

| Case | Expected result |
|---|---|
| Valid HTTPS JSON from exact allowlisted host | Accept snapshot; record raw and normalized hashes |
| Equivalent JSON key order | Same normalized hash; different raw hash allowed |
| `POST` or other write method | Reject |
| HTTP URL | Reject |
| Non-allowlisted host | Reject |
| Redirect to non-allowlisted host | Reject |
| Pilot flag absent | Reject |
| Kill switch active | Reject and remain at Gate 0 |
| Write-capable secret name present | Reject without printing secret value |
| Public/read-only key name present | Permit preflight |
| Malformed JSON | Reject |
| Unsupported content type | Reject |
| Response over byte cap | Reject |
| Stale snapshot with freshness required | Reject |
| Raw-byte hash mismatch | Reject |
| Authority or Gate 2 leakage | Reject |
| UTF-8 text with CRLF | Normalize to LF and preserve raw hash separately |

The matrix is synthetic. It proves membrane behavior without selecting or contacting a live source.
