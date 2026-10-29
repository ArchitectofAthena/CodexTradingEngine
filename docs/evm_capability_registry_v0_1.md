# Inert EVM registry — Stage A reconciled local proposal

The registry and JSON Schema are byte-identical to verified Stage A payloads; fourteen original networks, IDs, order and all nested fields are retained. Root authority is false and every network remains disabled/HOLD/NO_NETWORK, empty transport allowlists and zero nested permissions. All capabilities UNKNOWN and review fields null. Human signoff is empty/unverified in the separate provenance sidecar, which also separates observed bytes, assumed metadata, derived values and unknown economics. No extra fields were inserted into the original schema.

Use load_registry_json to reject duplicate JSON members; validate_registry(raw, now=aware_datetime, pinned_identities=...) returns sorted refusal strings. Empty tuple accepts inert proposal shape/semantics only. Original N01–N22 codes are preserved (SCHEMA_REJECT and semantic codes); added source/evidence/pin refusals strengthen the local implementation without changing originals.

The gate checker consumes network_id/display_name/wave from original records; it always returns HOLD with no execution/network authority because no trusted promotion verifier exists. Synthetic route profile_id aliases are explicitly separate and mapped in the provenance sidecar; aliases do not act as grants. Raw synthetic reserves are bounded to uint256 before conversion. Exact rational model arithmetic is not EVM execution or pool rounding verification.

Standalone original harness 22/22 and the independent implementation's ported 22-case outcome are separate evidence. Fifteen original F integrations, existing-pipeline/QAOA/Rust verification and external Work/Mog findings remain outstanding. All proposed changes require human review; no upstream application or promotion.

Repo-native verification now tests actual product components for original F01/F02/F07/F15; other original F integrations remain NOT_RUN with partial guard coverage reported separately. No source/consent/restore authority service is invented. Schema is also distributed as an exact package resource for wheel/container imports.
