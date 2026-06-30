from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, List


class EvePhase(str, Enum):
    SIMULATION = "simulation"
    TESTNET = "testnet"
    SANDBOX = "sandbox"
    CONSTRAINED_MAINNET = "constrained_mainnet"


@dataclass(slots=True)
class PhaseDecision:
    phase: EvePhase
    allowed_to_simulate: bool
    allowed_to_run_testnet: bool
    allowed_to_run_constrained_live: bool
    requires_human_review: bool
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def phase_from_config(cfg: Dict[str, Any]) -> EvePhase:
    deployment = cfg.get("deployment", {}) if cfg else {}
    mode = str(deployment.get("mode", "simulation")).lower()
    aliases = {"shadow_mainnet": EvePhase.SIMULATION, "mainnet": EvePhase.CONSTRAINED_MAINNET}
    try:
        return aliases.get(mode, EvePhase(mode))
    except ValueError:
        return EvePhase.SIMULATION


def evaluate_phase(cfg: Dict[str, Any], *, human_reviewed: bool = False) -> PhaseDecision:
    phase = phase_from_config(cfg)
    reasons: List[str] = []
    allowed_to_simulate = True
    allowed_to_run_testnet = phase in {EvePhase.TESTNET, EvePhase.SANDBOX} and human_reviewed
    allowed_to_run_constrained_live = phase is EvePhase.CONSTRAINED_MAINNET and human_reviewed

    if not human_reviewed:
        reasons.append("human_review_missing")
    if phase is EvePhase.SIMULATION:
        reasons.append("simulation_only")
    if phase is EvePhase.TESTNET:
        reasons.append("testnet_only")
    if phase is EvePhase.SANDBOX:
        reasons.append("sandbox_only")
    if phase is EvePhase.CONSTRAINED_MAINNET and not human_reviewed:
        reasons.append("constrained_live_requires_review")

    return PhaseDecision(
        phase=phase,
        allowed_to_simulate=allowed_to_simulate,
        allowed_to_run_testnet=allowed_to_run_testnet,
        allowed_to_run_constrained_live=allowed_to_run_constrained_live,
        requires_human_review=True,
        reasons=reasons or ["approved_with_constraints"],
    )
