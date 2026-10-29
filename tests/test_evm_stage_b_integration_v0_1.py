"""Offline component integrations for original F cases; no live source capture.

Unavailable authenticated-consent/reorg/cache services are dispositioned NOT_RUN,
not replaced by tests that manufacture an approving verifier.
"""
import copy
import json
import subprocess
import sys
from datetime import datetime, UTC
from decimal import Decimal
from pathlib import Path

import pytest

from eve_q.deployment_gates import CircuitBreaker, CostBreakdown, RiskGovernor
from eve_q.evm_capability_registry import validate_registry, canonical_sha256
from eve_q.evm_gate_intersection import evaluate_evm_readiness
from eve_q.evm_route_fixture import build_route_fixture
from eve_q.gate1_readonly_runtime import write_snapshot_bundle_atomic
from eve_q.live_read_only_telemetry import enforce_pilot_preflight, TelemetryBoundaryError
from tests.test_deployment_gates import policy
from tests.test_evm_stage_b_local_v0_1 import gate as gate_inputs, route, PINS, registry
from tests.test_gate1_source_consensus_v0_1 import observation, packet, evaluate
from tests.test_telemetry_draft_fixture_v0_1 import snapshot_bundle, build as build_draft

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,29,12,tzinfo=UTC)


def locked(decision):
    assert decision.readiness=='HOLD'
    assert (decision.authority,decision.may_execute,decision.allowed_network_io)==(False,False,False)


def test_F01_conflicting_reviewed_provider_packets_hold_without_averaging():
    positive=evaluate(packet(observation('source-a'),observation('source-b')))
    assert positive['decision']['code']=='ACCEPT_OBSERVATION_ONLY'
    negative=evaluate(packet(observation('source-a',value='10'),observation('source-b',value='12')))
    assert negative['decision']['code']=='HOLD_CONFLICT'
    assert negative['comparison']['aggregation_performed'] is False
    assert negative['comparison']['aggregate_value'] is None


def test_F02_integrity_valid_saved_bundle_is_stale_in_new_replay_process(tmp_path):
    snapshot,raw,normalized=snapshot_bundle()
    write_snapshot_bundle_atomic(tmp_path/'bundle',snapshot,raw,normalized)
    command=[sys.executable,'-m','eve_q.gate1_readonly_runtime','replay','--bundle',str(tmp_path/'bundle'),'--require-fresh','--now']
    fresh=subprocess.run(command+['2026-08-05T00:31:00Z'],cwd=ROOT,capture_output=True,text=True,check=False)
    assert fresh.returncode==0, fresh.stdout+fresh.stderr
    assert json.loads(fresh.stdout)['authority'] is False
    stale=subprocess.run(command+['2026-10-29T12:00:00Z'],cwd=ROOT,capture_output=True,text=True,check=False)
    result=json.loads(stale.stdout)
    assert stale.returncode==1
    assert any('stale' in finding for finding in result['findings'])
    assert result['authority'] is False


def test_F04_original_chain_grant_cannot_promote_other_original_network():
    args=gate_inputs()
    locked(evaluate_evm_readiness(**args))
    other=next(n for n in registry()['networks'] if n['network_id']=='arbitrum-testnet')
    args['chain_profile']=other
    decision=evaluate_evm_readiness(**args)
    assert 'HOLD_IDENTITY_CONFLICT' in decision.reasons
    locked(decision)


def test_F06_missing_l1_data_fee_or_premium_refuses_fixture():
    fixture=route('arbitrum-sepolia')
    assert build_route_fixture(fixture['snapshot'],fixture['fees'],now=NOW).status=='LOCAL_SIMULATION'
    for missing in ['l1_data_cost','flash_premium_bps']:
        fees=copy.deepcopy(fixture['fees']);fees.pop(missing)
        refusal=build_route_fixture(fixture['snapshot'],fees,now=NOW)
        assert refusal.status=='HOLD' and 'HOLD_FEE_MODEL' in refusal.reasons
        assert refusal.net_numerator is None and refusal.authority is False


def risk_decision(*,costs,network_enabled=False):
    return RiskGovernor().evaluate_entry(expected_gross_profit_usd=Decimal('10'),costs=costs,safety_margin_usd=Decimal('1'),daily_loss_usd=Decimal('0'),daily_gas_burn_usd=Decimal('0'),attempts_last_hour=0,consecutive_failures=0,policy=policy(),circuit_breaker=CircuitBreaker(),global_kill_switch=False,network_enabled=network_enabled,strategy_enabled=True,live_mode=False,human_approved=False)


def test_F07_existing_risk_governor_rejects_unprofitable_model():
    result=risk_decision(costs=CostBreakdown(gas_usd=Decimal('20')))
    assert result.submit is False and result.expected_net_profit_usd<0
    assert any('expected gross profit' in reason for reason in result.reasons)
    locked(evaluate_evm_readiness(**gate_inputs()))


def test_F09_existing_membrane_and_registry_refuse_signing_material():
    with pytest.raises(TelemetryBoundaryError) as exc:
        enforce_pilot_preflight({'EVE_Q_GATE1_PILOT':'1','WALLET_PRIVATE_KEY':'not-a-secret-fixture-marker'})
    assert exc.value.code=='write_capable_secret_detected'
    raw=registry();raw['networks'][1]['wallet_private_key']='not-a-secret-fixture-marker'
    assert 'SCHEMA_REJECT' in validate_registry(raw,now=NOW,pinned_identities=PINS)


def test_F11_cross_chain_pool_cannot_be_a_same_chain_cycle():
    fixture=route();fixture['snapshot']['payload']['pools'][1]['chain_id']='421614'
    fixture['snapshot']['payload_sha256']=canonical_sha256(fixture['snapshot']['payload'])
    result=build_route_fixture(fixture['snapshot'],fixture['fees'],now=NOW)
    assert result.status=='HOLD' and 'HOLD_CROSS_CHAIN' in result.reasons
    assert result.may_execute is False


def test_F12_disabled_network_is_not_overridden_by_favorable_metrics():
    result=risk_decision(costs=CostBreakdown(gas_usd=Decimal('1')))
    assert result.expected_net_profit_usd>0
    assert result.submit is False
    assert 'network is disabled' in result.reasons
    assert all(n['enabled'] is False for n in registry()['networks'])


def test_F14_artifact_validity_and_free_text_name_are_not_promotion():
    draft=build_draft().draft
    assert draft['operator_review']['state']=='DRAFT_UNREVIEWED'
    assert draft['local_simulation_eligible'] is False
    args=gate_inputs();args['promotion_receipt']['approved_by']='Architect'
    args['promotion_receipt']['verified']=True
    decision=evaluate_evm_readiness(**args)
    assert 'HOLD_VERIFIER_UNAVAILABLE' in decision.reasons
    locked(decision)


def test_F15_stored_eligible_label_cannot_override_expired_review():
    args=packet(observation('source-a'),observation('source-b'))
    args['evaluated_at']='2026-10-29T12:00:00Z'
    for item in args['observations']:
        item.update(observed_at='2026-10-29T11:59:00Z',expires_at='2026-10-29T12:01:00Z',review_expires_at='2026-10-30T12:00:00Z')
    assert evaluate(args)['decision']['code']=='ACCEPT_OBSERVATION_ONLY'
    args['observations'][0]['review_expires_at']='2026-09-04T01:12:00Z'
    assert args['observations'][0]['review_status']=='ELIGIBLE'
    assert evaluate(args)['decision']['code']=='HOLD_REVIEW_EXPIRED'


def test_current_revocation_and_expiry_override_cached_receipt_claims():
    cached=copy.deepcopy(gate_inputs()['promotion_receipt'])
    args=gate_inputs();args['promotion_receipt']=cached
    locked(evaluate_evm_readiness(**args))
    args['revocations']=[cached['receipt_id']]
    decision=evaluate_evm_readiness(**args)
    assert decision.disposition=='REVOKED' and 'HOLD_REVOKED' in decision.reasons
    locked(decision)
    args['revocations']=[];args['now']=datetime(2026,11,1,tzinfo=UTC)
    decision=evaluate_evm_readiness(**args)
    assert decision.disposition=='EXPIRED' and 'HOLD_EXPIRED_PROMOTION' in decision.reasons
    locked(decision)


def test_snapshot_integrity_does_not_supply_current_consent():
    snapshot,raw,normalized=snapshot_bundle()
    assert snapshot['hashes']['raw_sha256']
    from eve_q.gate1_readonly_runtime import validate_snapshot_v2
    assert validate_snapshot_v2(snapshot,raw,normalized,now=datetime(2026,8,5,0,31,tzinfo=UTC),require_fresh=True)==[]
    args=gate_inputs();args['promotion_receipt']=None
    decision=evaluate_evm_readiness(**args)
    assert 'HOLD_MISSING_RECEIPT' in decision.reasons
    locked(decision)
