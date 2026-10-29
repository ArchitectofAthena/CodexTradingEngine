"""Pure synthetic constant-product cycle research; no live data or commands.

All fees are in SYN-A, assumed equal to USD solely in the fixture. This is a
restricted local fixture format, not an existing producer pipeline adapter.
"""
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction
import re

from .evm_capability_registry import canonical_sha256, SOURCE_COMMIT


# Synthetic fixture names are not accepted as canonical registry network IDs.
SYNTHETIC_IDENTITIES = {
    'base-mainnet': ('8453','mainnet','Base'),
    'base-sepolia': ('84532','testnet','Base Sepolia'),
    'arbitrum-one': ('42161','mainnet','Arbitrum One'),
    'arbitrum-sepolia': ('421614','testnet','Arbitrum Sepolia'),
}


@dataclass(frozen=True)
class LocalFixture:
    status: str
    reasons: tuple[str, ...]
    corpus_sha256: str | None = None
    model_sha256: str | None = None
    route_id: str | None = None
    edges: tuple = ()
    net_numerator: int | None = None
    net_denominator: int | None = None
    authority: bool = field(default=False, init=False)
    may_execute: bool = field(default=False, init=False)
    allowed_network_io: bool = field(default=False, init=False)


def build_route_fixture(reviewed_snapshot, fee_assumptions, *, now) -> LocalFixture:
    """Consume strict synthetic fixture data, refusing malformed or missing evidence."""
    def hold(code): return LocalFixture('HOLD', (code,))
    snapshot, fees = reviewed_snapshot, fee_assumptions
    if not isinstance(snapshot, dict) or set(snapshot) != {'payload', 'payload_sha256'}:
        return hold('HOLD_FIXTURE_SCHEMA')
    payload = snapshot['payload']
    try:
        if canonical_sha256(payload) != snapshot['payload_sha256']:
            return hold('HOLD_HASH')
    except (ValueError, TypeError):
        return hold('HOLD_FIXTURE_SCHEMA')
    required = {'fixture_kind','profile_id','chain_id','environment','observed_at','ttl_seconds',
                'units','source_commit','provenance','tokens','pools'}
    if not isinstance(payload, dict) or set(payload) != required:
        return hold('HOLD_FIXTURE_SCHEMA')
    if payload['fixture_kind'] != 'SYNTHETIC' or payload['source_commit'] != SOURCE_COMMIT:
        return hold('HOLD_PROVENANCE')
    if payload['provenance'] != dict(observed=[],assumed=['all_market_quantities','borrowed_token_equals_usd'],
                                     derived=[],unknown=['live_liquidity','provider_support']):
        return hold('HOLD_PROVENANCE')
    if payload['units'] != 'raw_integer_token_units': return hold('HOLD_UNITS')
    key = payload['profile_id']
    expected = SYNTHETIC_IDENTITIES.get(key) if isinstance(key, str) else None
    if expected is None or payload['environment'] != 'testnet' or expected[:2] != (payload['chain_id'],payload['environment']):
        return hold('HOLD_IDENTITY')
    try:
        observed = datetime.fromisoformat(payload['observed_at'].replace('Z','+00:00'))
        ttl = payload['ttl_seconds']
        if type(ttl) is not int or not 0 < ttl <= 120 or now.tzinfo is None or observed.tzinfo is None:
            return hold('HOLD_CLOCK')
        age = (now-observed).total_seconds()
        if age < 0 or age >= ttl: return hold('HOLD_STALE')
    except (ValueError, TypeError, AttributeError):
        return hold('HOLD_CLOCK')
    # Synthetic asset pins are independent of untrusted fixture declarations.
    tokens = payload['tokens']
    if (tokens != [dict(id=x,decimals=6) for x in ('SYN-A','SYN-B','SYN-C')] or
            any(type(token['decimals']) is not int for token in tokens)):
        return hold('HOLD_DECIMALS')
    fee_keys = {'principal','capacity','flash_premium_bps','gas_cost','l1_data_cost',
                'expected_revert_cost','safety_margin','slippage_bps','latency_bps',
                'max_slippage_bps','provenance'}
    if not isinstance(fees,dict) or set(fees) != fee_keys or fees['provenance'] != 'ASSUMED_SYNTHETIC':
        return hold('HOLD_FEE_MODEL')
    numbers = {}
    try:
        for key in ('principal','capacity','gas_cost','l1_data_cost','expected_revert_cost','safety_margin'):
            value = fees[key]
            if not isinstance(value,str) or not re.fullmatch(r'(0|[1-9][0-9]*)(\.[0-9]+)?',value):
                return hold('HOLD_FEE_MODEL')
            numbers[key] = Fraction(value)
        for key in ('flash_premium_bps','slippage_bps','latency_bps','max_slippage_bps'):
            if type(fees[key]) is not int or not 0 <= fees[key] < 10000:
                return hold('HOLD_FEE_MODEL')
        if numbers['principal'] <= 0 or any(v < 0 for v in numbers.values()):
            return hold('HOLD_FEE_MODEL')
        if numbers['principal'] > numbers['capacity']: return hold('HOLD_CAPACITY')
        if fees['slippage_bps'] > fees['max_slippage_bps'] or fees['slippage_bps']+fees['latency_bps'] >= 10000:
            return hold('HOLD_SLIPPAGE')
    except (ValueError, TypeError, ZeroDivisionError):
        return hold('HOLD_FEE_MODEL')
    pools = payload['pools']
    if not isinstance(pools,list) or len(pools) != 3: return hold('HOLD_FIXTURE_SCHEMA')
    amount = numbers['principal']
    edges, seen = [], set()
    cycle = [('SYN-A','SYN-B'),('SYN-B','SYN-C'),('SYN-C','SYN-A')]
    for pool, assets in zip(pools,cycle):
        if not isinstance(pool,dict) or set(pool) != {'pool_id','chain_id','protocol','source_asset','target_asset','reserve_in','reserve_out','dex_fee_bps'}:
            return hold('HOLD_FIXTURE_SCHEMA')
        if pool['chain_id'] != payload['chain_id']: return hold('HOLD_CROSS_CHAIN')
        if pool['protocol'] != 'synthetic_xyk': return hold('HOLD_PROTOCOL')
        if (pool['source_asset'],pool['target_asset']) != assets: return hold('HOLD_ROUTE')
        if not isinstance(pool['pool_id'],str) or not pool['pool_id'] or pool['pool_id'] in seen:
            return hold('HOLD_POOL_IDENTITY')
        seen.add(pool['pool_id'])
        # Bound decimal raw quantities before int conversion. The synthetic EVM
        # model admits uint256 reserves only, not arbitrary-size Python integers.
        if any(not isinstance(pool[k],str) or len(pool[k]) > 78 or
               not re.fullmatch(r'0|[1-9][0-9]*',pool[k]) for k in ('reserve_in','reserve_out')):
            return hold('HOLD_LIQUIDITY')
        if any(int(pool[k]) > 2**256 - 1 for k in ('reserve_in','reserve_out')):
            return hold('HOLD_LIQUIDITY')
        reserves = [Fraction(int(pool[k]),10**6) for k in ('reserve_in','reserve_out')]
        if min(reserves) <= 0: return hold('HOLD_LIQUIDITY')
        dex_fee = pool['dex_fee_bps']
        if type(dex_fee) is not int or not 0 <= dex_fee < 10000: return hold('HOLD_FEE_MODEL')
        net_input = amount * Fraction(10000-dex_fee,10000)
        output = reserves[1]*net_input/(reserves[0]+net_input)
        output *= Fraction(10000-fees['slippage_bps']-fees['latency_bps'],10000)
        edges.append((pool['pool_id'],*assets,amount.numerator,amount.denominator,output.numerator,output.denominator))
        amount = output
    net = amount - numbers['principal'] - numbers['principal']*Fraction(fees['flash_premium_bps'],10000)
    net -= sum((numbers[k] for k in ('gas_cost','l1_data_cost','expected_revert_cost','safety_margin')),Fraction())
    model_hash = canonical_sha256({'payload':payload,'fees':fees,'algorithm':'xyk-fraction-v0.1'})
    return LocalFixture('LOCAL_SIMULATION',(),snapshot['payload_sha256'],model_hash,
                        canonical_sha256({'model':model_hash,'pools':[e[0] for e in edges]}),
                        tuple(edges),net.numerator,net.denominator)
