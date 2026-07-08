# Receipt Carrier Attestation Example

This example demonstrates a safe receipt-to-carrier attestation.

The attestation binds a receipt identifier to a carrier manifest digest and CID. It does not create execution authority.

## Attestation Law

```text
Receipt remembers.
Carrier points.
TTL expires.
Human promotes.
```

## Example Files

Carrier manifest:

```text
examples/artifact_carrier_manifest.example.json
```

Receipt carrier attestation:

```text
examples/receipt_carrier_attestation.example.json
```

## What The Attestation Proves

The example attestation records:

- the receipt identifier
- the carrier manifest SHA-256 digest
- the carrier CID
- artifact-only TTL mode
- human promotion requirement
- no execution authority
- no reverse execution channel

## What The Attestation Does Not Do

The attestation does not:

- execute commands
- sign wallets
- move capital
- schedule actions
- mutate receipts
- open a reverse execution channel

## Safe Chain

```text
receipt
-> carrier manifest digest
-> carrier CID
-> encrypted payload pointer
-> human review
```

## Drift Detection

If the carrier manifest changes after attestation, the SHA-256 digest changes and validation fails.

The attestation binds.
The hash detects drift.
The carrier still does not command.
