"""
Failsafe manager for EVE_Q SlurperBot v2 - Grace Economy Edition.

This module implements grace-based economics: baseline autonomy is freely given,
expanded autonomy is earned through altruistic execution. No punishment for
failure, only missed rewards. However, consecutive failures in similar market
conditions trigger a gentle request for human insight.

Philosophy:
- Success → TTL increases (reward for charity)
- Single failure → Grace maintained (no punishment)
- Multiple consecutive failures → Gentle decay (market adaptation signal)
- Chain graduation → Grace renewed (fresh start in new environment)
"""

import json
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict


# Path where the liveness token state is stored
STATE_FILE = Path(__file__).resolve().parent.parent / "liveness_state.json"


# Default configuration values
DEFAULT_TTL_HOURS = 24
DEFAULT_MAX_TTL_HOURS = 48
CONSECUTIVE_FAILURE_THRESHOLD = 5  # Grace-preserving threshold


def _compute_checksum(state: Dict[str, Any]) -> str:
    """Compute SHA256 checksum of state data for tamper detection."""
    # Create deterministic string representation
    state_str = json.dumps(state, sort_keys=True)
    return hashlib.sha256(state_str.encode()).hexdigest()


def _load_state() -> Dict[str, Any]:
    """Load state from file with error handling and tamper detection."""
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Verify checksum if present
            if "checksum" in data:
                stored_checksum = data.pop("checksum")
                computed_checksum = _compute_checksum(data)
                if stored_checksum != computed_checksum:
                    print("WARNING: State file checksum mismatch - possible tampering detected!")
                    print("Resetting to default state for safety.")
                    return {
                        "last_confirm": 0,
                        "ttl_hours": DEFAULT_TTL_HOURS,
                        "consecutive_failures": 0
                    }

            # Ensure consecutive_failures exists
            if "consecutive_failures" not in data:
                data["consecutive_failures"] = 0

            return data
        else:
            return {
                "last_confirm": 0,
                "ttl_hours": DEFAULT_TTL_HOURS,
                "consecutive_failures": 0
            }
    except json.JSONDecodeError as e:
        print(f"ERROR: Corrupted state file ({e}). Resetting to default.")
        return {
            "last_confirm": 0,
            "ttl_hours": DEFAULT_TTL_HOURS,
            "consecutive_failures": 0
        }
    except Exception as e:
        print(f"ERROR: Failed to load state file ({e}). Resetting to default.")
        return {
            "last_confirm": 0,
            "ttl_hours": DEFAULT_TTL_HOURS,
            "consecutive_failures": 0
        }


def _save_state(state: Dict[str, Any]) -> None:
    """Save state to file with checksum for tamper detection."""
    try:
        # Add checksum
        state_copy = state.copy()
        checksum = _compute_checksum(state_copy)
        state_copy["checksum"] = checksum

        # Write atomically using temp file
        temp_file = STATE_FILE.with_suffix('.tmp')
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(state_copy, f, indent=2)

        # Atomic rename
        temp_file.replace(STATE_FILE)
    except Exception as e:
        print(f"ERROR: Failed to save state file ({e})")
        raise


def check_liveness(failsafe_cfg: Dict[str, Any]) -> bool:
    """Check whether the human liveness token is still valid.

    The failsafe configuration may specify either ``ttl_hours``
    (preferred) or the legacy key ``human_liveness_ttl_hours``.  If
    neither is provided, a default of 24 hours is used.  The state
    file stores the last confirmation timestamp and the current TTL.

    Parameters
    ----------
    failsafe_cfg : dict
        Configuration dictionary containing liveness settings.

    Returns
    -------
    bool
        ``True`` if the bot may continue operating; ``False`` if it
        should halt and request human intervention.
    """
    state = _load_state()
    # Prefer ttl_hours, fall back to legacy human_liveness_ttl_hours
    ttl_hours = failsafe_cfg.get(
        "ttl_hours",
        failsafe_cfg.get("human_liveness_ttl_hours", state.get("ttl_hours", DEFAULT_TTL_HOURS)),
    )
    last_confirm_ts = state.get("last_confirm", 0)
    last_confirm = datetime.utcfromtimestamp(last_confirm_ts)
    now = datetime.utcnow()
    if now - last_confirm > timedelta(hours=ttl_hours):
        return False
    return True


def update_liveness_token(failsafe_cfg: Dict[str, Any]) -> datetime:
    """Update the liveness token timestamp to now.

    Returns
    -------
    datetime
        The updated confirmation timestamp.
    """
    state = _load_state()
    now = datetime.utcnow()
    state["last_confirm"] = now.timestamp()
    _save_state(state)
    return now


def progressive_trust_increment(failsafe_cfg: Dict[str, Any], success: bool) -> None:
    """Adjust the TTL based on successful cycles - GRACE-BASED ECONOMICS.

    Philosophy:
    - Success → TTL increases (reward for altruistic execution)
    - Single failure → Grace maintained (no punishment, only missed reward)
    - Multiple consecutive failures → Gentle decay (market adaptation signal)

    This preserves the "no punishment" ethos while adding intelligent
    adaptation to changing market conditions.

    Parameters
    ----------
    failsafe_cfg : dict
        Configuration with keys ``ttl_hours`` and ``max_ttl_hours``.
    success : bool
        Whether the last cycle completed with charity donation.
    """
    try:
        state = _load_state()
        current_ttl = state.get("ttl_hours", failsafe_cfg.get("ttl_hours", DEFAULT_TTL_HOURS))
        max_ttl = failsafe_cfg.get("max_ttl_hours", DEFAULT_MAX_TTL_HOURS)
        consecutive_failures = state.get("consecutive_failures", 0)

        if success:
            # REWARD: Altruistic action → Expanded autonomy
            new_ttl = min(current_ttl + 4, max_ttl)
            state["ttl_hours"] = new_ttl
            state["consecutive_failures"] = 0  # Reset failure counter
            _save_state(state)

            print(f"🌱 Grace expanded: TTL increased from {current_ttl}h to {new_ttl}h")
            print(f"   Reward granted for altruistic execution")
            print(f"   Next charity opportunity in {new_ttl} hours")
        else:
            # Track consecutive failures
            consecutive_failures += 1
            state["consecutive_failures"] = consecutive_failures

            # GRACE-PRESERVING ADAPTATION:
            # Only after multiple consecutive failures do we gently suggest
            # that market conditions may have changed
            if consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
                # Gentle decay after persistent failures (market adaptation)
                new_ttl = max(current_ttl - 2, DEFAULT_TTL_HOURS)
                state["ttl_hours"] = new_ttl
                _save_state(state)

                print(f"🔔 Market adaptation signal: TTL adjusted from {current_ttl}h to {new_ttl}h")
                print(f"   {consecutive_failures} consecutive cycles without charity")
                print(f"   This suggests changing market conditions")
                print(f"   Human insight requested to adapt strategy")
            else:
                # Grace maintained for occasional failures
                print(f"⏸️  Grace maintained at {current_ttl}h")
                print(f"   Charity not executed this cycle (failure {consecutive_failures}/{CONSECUTIVE_FAILURE_THRESHOLD})")
                print(f"   No TTL change - grace preserved")
                _save_state(state)  # Save failure counter

    except Exception as e:
        print(f"Error in progressive_trust_increment: {e}")
        # On error, maintain current state - preserve grace


def reset_ttl_for_chain_graduation(reason: str = "chain_graduation",
                                   reset_to: int = DEFAULT_TTL_HOURS) -> None:
    """Reset TTL to baseline when graduating to higher-risk environment.

    Philosophy: Grace is renewed when entering new territory.
    Each chain has different risks - start fresh with baseline autonomy.

    Parameters
    ----------
    reason : str
        Human-readable reason for reset (logged for transparency)
    reset_to : int
        TTL hours to reset to (defaults to baseline 24h)
    """
    try:
        state = _load_state()
        old_ttl = state.get("ttl_hours", DEFAULT_TTL_HOURS)
        state["ttl_hours"] = reset_to
        state["consecutive_failures"] = 0  # Fresh start
        _save_state(state)

        print(f"\n🔄 GRACE RENEWED:")
        print(f"   TTL reset: {old_ttl}h → {reset_to}h")
        print(f"   Reason: {reason}")
        print(f"   Consecutive failures cleared")
        print(f"   Fresh start in new environment")

    except Exception as e:
        print(f"Error resetting TTL: {e}")


def get_trust_report() -> Dict[str, Any]:
    """Generate report on current trust state for transparency.

    Returns
    -------
    dict
        Current TTL, consecutive failures, and grace status
    """
    state = _load_state()
    return {
        "current_ttl_hours": state.get("ttl_hours", DEFAULT_TTL_HOURS),
        "consecutive_failures": state.get("consecutive_failures", 0),
        "grace_status": "expanded" if state.get("ttl_hours", DEFAULT_TTL_HOURS) > DEFAULT_TTL_HOURS else "baseline",
        "last_confirmation": datetime.utcfromtimestamp(state.get("last_confirm", 0)).isoformat()
    }
