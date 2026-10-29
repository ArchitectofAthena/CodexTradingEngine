import copy
import json
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, UTC
from pathlib import Path

from eve_q.evm_capability_registry import validate_registry, load_registry_json, canonical_sha256
from eve_q.evm_gate_intersection import evaluate_evm_readiness
from eve_q.evm_route_fixture import build_route_fixture

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]
from eve_q.evm_capability_registry import PINNED_NETWORKS
PINS = {key:value[0] for key,value in PINNED_NETWORKS.items()}

def registry():
    return json.loads((ROOT/'registry/evm_capabilities_v0_1.json').read_text())

def gate():
    return dict(capability_gate='1A', deployment_tier=1,
        chain_profile=registry()['networks'][1],
        source_review=dict(network_id='base-testnet', chain_id='84532', source_id='synthetic',
            source_sha='a'*64, method='GET', review_expires_at='2026-10-30T12:00:00Z'),
        promotion_receipt=dict(receipt_id='b'*64, network_id='base-testnet', chain_id='84532',
            source_id='synthetic', source_sha='a'*64, expires_at='2026-10-30T12:00:00Z',
            approved_by='Architect'), revocations=[], now=NOW)

def route(chain='base-sepolia'):
    return json.loads((ROOT/f'tests/fixtures/{chain}.json').read_text())

class RegistryTests(unittest.TestCase):
    def test_baseline_non_authoritative(self):
        self.assertEqual(validate_registry(registry(),now=NOW,pinned_identities=PINS),())
        self.assertEqual(len(registry()['networks']),14)

    def test_duplicate_json_keys(self):
        with self.assertRaisesRegex(ValueError,'HOLD_DUPLICATE_KEY'):
            load_registry_json('{"authority":false,"authority":true}')

    def test_canonical_hash(self):
        self.assertEqual(canonical_sha256({'b':2,'a':1}), canonical_sha256({'a':1,'b':2}))
        self.assertNotEqual(canonical_sha256({'a':1}),canonical_sha256({'a':2}))

    def test_naive_clock(self):
        self.assertIn('HOLD_CLOCK',validate_registry(registry(),now=NOW.replace(tzinfo=None),pinned_identities=PINS))

    def test_mutations_have_exact_codes(self):
        cases=json.loads((ROOT/'tests/fixtures/local_registry_mutations_v0_1.json').read_text())
        for case in cases:
            with self.subTest(case=case['id']):
                raw=registry(); obj=raw
                for key in case['path'][:-1]: obj=obj[key]
                obj[case['path'][-1]]=case['value']
                self.assertIn(case['expected'],validate_registry(raw,now=NOW,pinned_identities=PINS))

    def test_duplicate_identity(self):
        raw=registry(); raw['networks'].append(copy.deepcopy(raw['networks'][0]))
        self.assertIn('NETWORK_IDENTITY_DUPLICATE',validate_registry(raw,now=NOW,pinned_identities=PINS))

    def test_unknown_pin(self):
        self.assertIn('CHAIN_ID_MISMATCH',validate_registry(registry(),now=NOW,pinned_identities={}))

class GateTests(unittest.TestCase):
    def check(self, args, expected):
        d=evaluate_evm_readiness(**args)
        self.assertIn(expected,d.reasons)
        self.assertEqual((d.authority,d.may_execute,d.allowed_network_io),(False,False,False))
        self.assertEqual(d.readiness,'HOLD')
        return d

    def test_free_text_approver_and_verified_boolean_do_not_authenticate(self):
        a=gate(); a['promotion_receipt']['verified']=True
        d=self.check(a,'HOLD_VERIFIER_UNAVAILABLE')
        with self.assertRaises(FrozenInstanceError): d.authority=True

    def test_missing_receipt(self):
        a=gate(); a['promotion_receipt']=None; self.check(a,'HOLD_MISSING_RECEIPT')

    def test_cross_chain_and_environment(self):
        for profile,chain in [('arbitrum-testnet','421614'),('base-mainnet','8453')]:
            a=gate(); a['promotion_receipt'].update(network_id=profile,chain_id=chain)
            self.check(a,'HOLD_IDENTITY_CONFLICT')

    def test_phase_alias_and_gate_skip(self):
        for cap in ['constrained_mainnet','mainnet','2','6','testnet']:
            a=gate(); a['capability_gate']=cap; self.check(a,'HOLD_CAPABILITY_SCOPE')

    def test_tier_two_cannot_activate_profiles(self):
        a=gate(); a['deployment_tier']=2; self.check(a,'HOLD_TIER_SCOPE')

    def test_expired_source_and_promotion(self):
        for key,datekey in [('source_review','review_expires_at'),('promotion_receipt','expires_at')]:
            a=gate(); a[key][datekey]='2026-09-04T01:12:00Z'
            d=self.check(a,'HOLD_EXPIRED_REVIEW' if key=='source_review' else 'HOLD_EXPIRED_PROMOTION')
            self.assertEqual(d.disposition,'EXPIRED')

    def test_post_refused(self):
        a=gate(); a['source_review']['method']='POST'; self.check(a,'HOLD_METHOD_SCOPE')

    def test_revocation_precedence_and_restart_replay(self):
        a=gate(); a['revocations']=['b'*64]; a['promotion_receipt']['expires_at']='2026-01-01T00:00:00Z'
        for _ in range(2):
            d=self.check(copy.deepcopy(a),'HOLD_REVOKED'); self.assertEqual(d.disposition,'REVOKED')

    def test_missing_revocation_snapshot(self):
        a=gate(); a['revocations']=None; self.check(a,'HOLD_REVOCATIONS_UNKNOWN')

    def test_malformed_identity_is_hold(self):
        a=gate(); a['chain_profile']['network_id']=[]
        self.check(a,'HOLD_IDENTITY_CONFLICT')

    def test_source_hash_is_validated(self):
        a=gate(); a['source_review']['source_sha']='not-a-sha'
        self.check(a,'HOLD_SOURCE_HASH')

class RouteTests(unittest.TestCase):
    def test_synthetic_base_and_arbitrum(self):
        for chain in ['base-sepolia','arbitrum-sepolia']:
            a=route(chain); d=build_route_fixture(a['snapshot'],a['fees'],now=NOW)
            self.assertEqual(d.status,'LOCAL_SIMULATION')
            self.assertFalse(d.authority); self.assertFalse(d.may_execute)
            self.assertEqual(len(d.edges),3)
            self.assertEqual(d,build_route_fixture(a['snapshot'],a['fees'],now=NOW))
            # Independent rational arithmetic for three constant-product pools:
            from fractions import Fraction as F
            amount=F(100)
            for _ in range(3):
                net=amount*F(997,1000)
                amount=F(11000)*net/(F(10000)+net)
                amount*=F(9990,10000) # explicit slippage + latency haircut
            expected=amount-F(100)-F(100)*F(5,10000)-F(4)
            self.assertEqual(F(d.net_numerator,d.net_denominator),expected)

    def check(self,mutate,reason,rehash=True):
        a=route(); mutate(a)
        if rehash: a['snapshot']['payload_sha256']=canonical_sha256(a['snapshot']['payload'])
        d=build_route_fixture(a['snapshot'],a['fees'],now=NOW)
        self.assertEqual(d.status,'HOLD'); self.assertIn(reason,d.reasons)
        self.assertFalse(d.authority); self.assertFalse(d.may_execute)

    def test_chain_mislabel(self):
        self.check(lambda a:a['snapshot']['payload'].update(chain_id='8453'),'HOLD_IDENTITY')

    def test_hash_mismatch(self):
        self.check(lambda a:a['snapshot']['payload'].update(chain_id='421614'),'HOLD_HASH',False)

    def test_stale(self):
        self.check(lambda a:a['snapshot']['payload'].update(observed_at='2026-10-28T00:00:00Z'),'HOLD_STALE')

    def test_missing_chain(self):
        self.check(lambda a:a['snapshot']['payload'].pop('chain_id'),'HOLD_FIXTURE_SCHEMA')

    def test_decimal_spoof(self):
        self.check(lambda a:a['snapshot']['payload']['tokens'][0].update(decimals=18),'HOLD_DECIMALS')

    def test_decimal_type_is_integer(self):
        self.check(lambda a:a['snapshot']['payload']['tokens'][0].update(decimals=6.0),'HOLD_DECIMALS')

    def test_observed_zero_not_replaced_by_assumption(self):
        self.check(lambda a:a['snapshot']['payload']['pools'][0].update(reserve_in='0'),'HOLD_LIQUIDITY')

    def test_cross_chain_pool(self):
        self.check(lambda a:a['snapshot']['payload']['pools'][0].update(chain_id='421614'),'HOLD_CROSS_CHAIN')

    def test_unknown_protocol(self):
        self.check(lambda a:a['snapshot']['payload']['pools'][0].update(protocol='unknown'),'HOLD_PROTOCOL')

    def test_capacity_shortfall(self):
        self.check(lambda a:a['fees'].update(capacity='99'),'HOLD_CAPACITY')

    def test_missing_rollup_cost(self):
        self.check(lambda a:a['fees'].pop('l1_data_cost'),'HOLD_FEE_MODEL')

    def test_slippage_exceeds_margin(self):
        self.check(lambda a:a['fees'].update(slippage_bps=501),'HOLD_SLIPPAGE')

    def test_unknown_fields_cannot_request_wallet_or_payout(self):
        self.check(lambda a:a['fees'].update(payout=True),'HOLD_FEE_MODEL')

    def test_nonfinite_fee(self):
        self.check(lambda a:a['fees'].update(gas_cost='NaN'),'HOLD_FEE_MODEL')

    def test_oversized_raw_reserve_is_hold(self):
        self.check(lambda a:a['snapshot']['payload']['pools'][0].update(reserve_in='1'*4301),'HOLD_LIQUIDITY')

    def test_raw_reserve_exceeding_uint256_is_hold(self):
        self.check(lambda a:a['snapshot']['payload']['pools'][0].update(reserve_out=str(2**256)),'HOLD_LIQUIDITY')

    def test_malformed_identity(self):
        self.check(lambda a:a['snapshot']['payload'].update(profile_id=[]),'HOLD_IDENTITY')

    def test_source_relabel_retaining_hash(self):
        a=route('arbitrum-sepolia'); a['snapshot']['payload']['profile_id']='base-sepolia'
        d=build_route_fixture(a['snapshot'],a['fees'],now=NOW)
        self.assertIn('HOLD_HASH',d.reasons)

    def test_fee_changes_bind_model_and_route_ids(self):
        a=route(); d=build_route_fixture(a['snapshot'],a['fees'],now=NOW)
        a['fees']['gas_cost']='2'; e=build_route_fixture(a['snapshot'],a['fees'],now=NOW)
        self.assertNotEqual(d.model_sha256,e.model_sha256)
        self.assertNotEqual(d.route_id,e.route_id)
        from fractions import Fraction as F
        self.assertEqual(F(d.net_numerator,d.net_denominator)-F(e.net_numerator,e.net_denominator),1)

if __name__=='__main__': unittest.main()
