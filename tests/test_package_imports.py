def test_omega_package_import_surface():
    import omega_telemetry
    from omega_telemetry import Event, PricePoint, TelemetryDB, HealthWriter, load_config
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
    from eve_q.telemetry.need_score import NeedSignal, score_need
    from eve_q.telemetry.impact_score import ImpactSignal, score_impact

    assert GeodesicInput is not None
    assert score_allocation is not None
    assert EvePhase is not None
    assert evaluate_phase is not None
    assert NeedSignal is not None
    assert score_need is not None
    assert ImpactSignal is not None
    assert score_impact is not None
