def test_omega_package_import_surface():
    import omega_telemetry
    from omega_telemetry import Event, HealthWriter, PricePoint, TelemetryDB, load_config
    from omega_telemetry.models import ChainSignalEvent

    assert omega_telemetry is not None
    assert Event is not None
    assert ChainSignalEvent is not None
    assert PricePoint is not None
    assert TelemetryDB is not None
    assert HealthWriter is not None
    assert load_config is not None


def test_eve_q_package_import_surface():
    from eve_q.allocation.geodesic_policy import GeodesicInput, score_allocation
    from eve_q.gates.eve_phase import EvePhase, evaluate_phase
    from eve_q.research_cli import main as research_main
    from eve_q.telemetry.impact_score import ImpactSignal, score_impact
    from eve_q.telemetry.need_score import NeedSignal, score_need

    assert GeodesicInput is not None
    assert score_allocation is not None
    assert EvePhase is not None
    assert evaluate_phase is not None
    assert NeedSignal is not None
    assert score_need is not None
    assert ImpactSignal is not None
    assert score_impact is not None
    assert research_main is not None


def test_root_receipt_models_are_packaged():
    from models import CharityAllocation, CycleReceiptModel, RouteCandidate

    assert CharityAllocation is not None
    assert CycleReceiptModel is not None
    assert RouteCandidate is not None


def test_required_root_modules_are_importable():
    import eveq_failsafe_receipt
    import proof_adapters
    import shadow_cycle_runner

    assert eveq_failsafe_receipt is not None
    assert proof_adapters is not None
    assert shadow_cycle_runner is not None
