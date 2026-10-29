"""Pure validator for the original fourteen-network inert Stage A proposal.

The registry/schema bytes are preserved. Additional refusals are implementation
policy, not modifications of the original standalone validator or evidence.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Mapping
from datetime import datetime
from importlib.resources import files
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

SOURCE_COMMIT = '228a3edec7ee83a50037a9f4a81f2f6546bb73f7'
SCHEMA = json.loads(files('eve_q').joinpath('evm_capability_registry_v0_1.schema.json').read_text(encoding='utf-8'))
PINNED_NETWORKS = {
    'base-mainnet': ('8453','mainnet','EVM_WAVE_1','Base'),
    'base-testnet': ('84532','testnet','EVM_WAVE_1','Base Sepolia'),
    'arbitrum-mainnet': ('42161','mainnet','EVM_WAVE_1','Arbitrum One'),
    'arbitrum-testnet': ('421614','testnet','EVM_WAVE_1','Arbitrum Sepolia'),
    'polygon-mainnet': ('137','mainnet','EVM_WAVE_2','Polygon PoS'),
    'polygon-testnet': ('80002','testnet','EVM_WAVE_2','Polygon Amoy'),
    'optimism-mainnet': ('10','mainnet','EVM_WAVE_2','OP Mainnet'),
    'optimism-testnet': ('11155420','testnet','EVM_WAVE_2','OP Sepolia'),
    'bsc-mainnet': ('56','mainnet','EVM_WAVE_2','BNB Smart Chain'),
    'bsc-testnet': ('97','testnet','EVM_WAVE_2','BSC Testnet'),
    'avalanche-mainnet': ('43114','mainnet','EVM_WAVE_2','Avalanche C-Chain'),
    'avalanche-testnet': ('43113','testnet','EVM_WAVE_2','Avalanche Fuji'),
    'ethereum-mainnet': ('1','mainnet','DEFERRED','Ethereum Mainnet'),
    'ethereum-testnet': ('11155111','testnet','DEFERRED','Ethereum Sepolia'),
}


def canonical_sha256(raw: Any) -> str:
    encoded=json.dumps(raw,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def load_registry_json(text: str) -> Any:
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError('HOLD_DUPLICATE_KEY')
            result[key]=value
        return result
    def bad_constant(value): raise ValueError('HOLD_NONFINITE_JSON')
    return json.loads(text,object_pairs_hook=pairs,parse_constant=bad_constant)


def validate_registry(raw: Mapping[str, Any], *, now: datetime,
                      pinned_identities: Mapping[str,str]) -> tuple[str,...]:
    reasons=set()
    clock_valid=isinstance(now,datetime) and now.tzinfo is not None and now.utcoffset() is not None
    if not clock_valid: reasons.add('HOLD_CLOCK')
    if not isinstance(pinned_identities,Mapping):
        reasons.add('PINNED_IDENTITIES_UNAVAILABLE')
        pinned_identities={}
    # Schema refusals precede semantics: no unchecked indexing on malformed data.
    if not isinstance(raw,dict) or any(Draft202012Validator(SCHEMA,format_checker=FormatChecker()).iter_errors(raw)):
        return tuple(sorted(reasons|{'SCHEMA_REJECT'}))
    # date-time format plugins are optional in jsonschema; enforce this bound
    # explicitly so the result does not depend on their installation.
    try:
        stamp=raw['as_of_utc']
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})',stamp): raise ValueError()
        if datetime.fromisoformat(stamp.replace('Z','+00:00')).utcoffset() is None: raise ValueError()
    except ValueError:
        reasons.add('SCHEMA_REJECT')
    if raw['producer_commit'] != SOURCE_COMMIT: reasons.add('SOURCE_COMMIT_MISMATCH')
    seen,identities=set(),set()
    for n in raw['networks']:
        key,chain,env=n['network_id'],n['chain_id'],n['environment']
        if key in seen: reasons.add('NETWORK_ID_DUPLICATE')
        seen.add(key)
        identity=(chain,env)
        if identity in identities: reasons.add('NETWORK_IDENTITY_DUPLICATE')
        identities.add(identity)
        if not key.endswith('-'+env): reasons.add('NETWORK_ID_ENVIRONMENT_MISMATCH')
        expected=PINNED_NETWORKS.get(key)
        if expected is None: reasons.add('NETWORK_ID_UNKNOWN')
        else:
            if chain!=expected[0] or pinned_identities.get(key)!=chain: reasons.add('CHAIN_ID_MISMATCH')
            if env!=expected[1]: reasons.add('NETWORK_ID_ENVIRONMENT_MISMATCH')
            if n['wave']!=expected[2]: reasons.add('WAVE_BINDING_MISMATCH')
            if n['display_name']!=expected[3]: reasons.add('NETWORK_NAME_MISMATCH')
        if any(value!='UNKNOWN' for value in n['capabilities'].values()): reasons.add('CAPABILITY_STATE_DRIFT')
        evidence=n['evidence']
        if 'PASS' in n['capabilities'].values() and evidence['review_sha256'] is None:
            reasons.add('CAPABILITY_PASS_UNPROVEN')
        if evidence['source_commit']!=SOURCE_COMMIT: reasons.add('SOURCE_COMMIT_MISMATCH')
        if evidence['review_sha256'] is not None:
            reasons.add('EVIDENCE_UNVERIFIED')
            if not evidence['last_reviewed_at'] or not evidence['review_expires_at']:
                reasons.add('EVIDENCE_PROVENANCE_INCOMPLETE')
            elif clock_valid:
                try:
                    expiry=datetime.fromisoformat(evidence['review_expires_at'].replace('Z','+00:00'))
                    reviewed=datetime.fromisoformat(evidence['last_reviewed_at'].replace('Z','+00:00'))
                    if expiry.tzinfo is None or reviewed.tzinfo is None or expiry<=reviewed or reviewed>now:
                        raise ValueError()
                    if expiry<=now: reasons.add('EVIDENCE_REVIEW_EXPIRED')
                except (ValueError,TypeError): reasons.add('EVIDENCE_REVIEW_INVALID_TIME')
        elif evidence['last_reviewed_at'] is not None or evidence['review_expires_at'] is not None:
            reasons.add('EVIDENCE_PROVENANCE_INCOMPLETE')
        for s in n['source_reviews']:
            if s['network_id']!=key or s['chain_id']!=chain: reasons.add('SOURCE_CHAIN_ID_MISMATCH')
            try:
                u=urlsplit(s['url']);host=u.hostname or '';port=u.port
                if not host or u.scheme!='https' or port not in (None,443): reasons.add('SOURCE_URL_INVALID')
                if u.username is not None or u.password is not None: reasons.add('SOURCE_CREDENTIALS_PROHIBITED')
                if u.query or u.fragment: reasons.add('SOURCE_QUERY_OR_FRAGMENT_PROHIBITED')
                if s['allowed_hosts']!=[host]: reasons.add('SOURCE_HOST_MISMATCH')
                try:
                    if not ipaddress.ip_address(host).is_global: reasons.add('SOURCE_PRIVATE_HOST')
                except ValueError:
                    lower=host.lower().rstrip('.')
                    if lower=='localhost' or lower.endswith(('.localhost','.local','.internal')) or host.replace('.','').isdigit():
                        reasons.add('SOURCE_PRIVATE_HOST')
            except ValueError: reasons.add('SOURCE_URL_INVALID')
            if s['disposition']=='REVIEWED':
                reasons.add('SOURCE_REVIEW_UNVERIFIED')
                if not s['review_sha256'] or not s['reviewed_at'] or not s['review_expires_at']:
                    reasons.add('SOURCE_REVIEW_INCOMPLETE')
                elif clock_valid:
                    try:
                        expiry=datetime.fromisoformat(s['review_expires_at'].replace('Z','+00:00'))
                        reviewed=datetime.fromisoformat(s['reviewed_at'].replace('Z','+00:00'))
                        if expiry.tzinfo is None or reviewed.tzinfo is None or reviewed>now or expiry<=reviewed: raise ValueError()
                        if expiry<=now: reasons.add('SOURCE_REVIEW_EXPIRED')
                    except (ValueError,TypeError): reasons.add('SOURCE_REVIEW_INVALID_EXPIRY')
    if seen!=set(PINNED_NETWORKS): reasons.add('NETWORK_SET_DRIFT')
    return tuple(sorted(reasons))
