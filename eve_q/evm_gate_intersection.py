"""Non-commanding anti-inheritance checker; human verifier unavailable."""
from dataclasses import dataclass, field
from datetime import datetime
import re

from .evm_capability_registry import SOURCE_COMMIT, PINNED_NETWORKS


@dataclass(frozen=True)
class NonAuthoritativeDecision:
    disposition: str
    reasons: tuple[str, ...]
    source_sha: str | None
    source_commit: str = field(default=SOURCE_COMMIT, init=False)
    readiness: str = field(default='HOLD', init=False)
    authority: bool = field(default=False, init=False)
    may_execute: bool = field(default=False, init=False)
    allowed_network_io: bool = field(default=False, init=False)


def evaluate_evm_readiness(*, capability_gate, deployment_tier, chain_profile,
                           source_review, promotion_receipt, revocations, now):
    findings = [('UNKNOWN', 'HOLD_VERIFIER_UNAVAILABLE')]
    def add(priority, code): findings.append((priority, code))
    def expiry(document, key, code):
        try:
            value = datetime.fromisoformat(document[key].replace('Z', '+00:00'))
            if value.tzinfo is None or now.tzinfo is None:
                raise ValueError()
            if value <= now: add('EXPIRED', code)
        except (ValueError, TypeError, KeyError, AttributeError):
            add('UNKNOWN', 'HOLD_CLOCK_OR_EXPIRY')

    profile = chain_profile if isinstance(chain_profile, dict) else {}
    source = source_review if isinstance(source_review, dict) else {}
    receipt = promotion_receipt if isinstance(promotion_receipt, dict) else {}
    if capability_gate != '1A': add('CONFLICT', 'HOLD_CAPABILITY_SCOPE')
    if type(deployment_tier) is not int or deployment_tier != 1:
        add('CONFLICT', 'HOLD_TIER_SCOPE')
    key = profile.get('network_id')
    expected = PINNED_NETWORKS.get(key) if isinstance(key, str) else None
    if expected is None or (profile.get('chain_id'), profile.get('environment'), profile.get('wave'), profile.get('display_name')) != expected:
        add('CONFLICT', 'HOLD_IDENTITY_CONFLICT')
    if profile.get('environment') != 'testnet': add('CONFLICT', 'HOLD_ENVIRONMENT_SCOPE')
    for document in (source, receipt):
        if any(document.get(k) != profile.get(k) for k in ('network_id', 'chain_id')):
            add('CONFLICT', 'HOLD_IDENTITY_CONFLICT')
    if source.get('method') not in ('GET', 'HEAD'): add('CONFLICT', 'HOLD_METHOD_SCOPE')
    source_sha = source.get('source_sha')
    if not isinstance(source_sha, str) or not re.fullmatch('[0-9a-f]{64}', source_sha):
        add('UNKNOWN', 'HOLD_SOURCE_HASH')
        source_sha = None
    if not receipt: add('UNKNOWN', 'HOLD_MISSING_RECEIPT')
    if any(receipt.get(k) != source.get(k) for k in ('source_id', 'source_sha')):
        add('CONFLICT', 'HOLD_SOURCE_CONFLICT')
    if not isinstance(revocations, (list, tuple)) or not all(isinstance(x, str) for x in revocations):
        add('UNKNOWN', 'HOLD_REVOCATIONS_UNKNOWN')
    elif receipt.get('receipt_id') in revocations:
        add('REVOKED', 'HOLD_REVOKED')
    expiry(source, 'review_expires_at', 'HOLD_EXPIRED_REVIEW')
    expiry(receipt, 'expires_at', 'HOLD_EXPIRED_PROMOTION')
    order = {'REVOKED':0, 'EXPIRED':1, 'CONFLICT':2, 'UNKNOWN':3, 'REVIEWABLE':4}
    findings = sorted(set(findings), key=lambda item: (order[item[0]], item[1]))
    return NonAuthoritativeDecision(findings[0][0], tuple(x[1] for x in findings), source_sha)
