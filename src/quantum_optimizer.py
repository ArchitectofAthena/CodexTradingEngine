"""
Quantum optimizer module for the EVE_Q SlurperBot v2.

This module uses Qiskit to encode arbitrage routes as cost Hamiltonians and
employ a Quantum Approximate Optimization Algorithm (QAOA) style process to
select the most profitable route subject to risk penalties.  When run on
classical hardware, this falls back to a classical simulation of the circuit.

Note: QAOA here is illustrative; production use should be carefully tuned
and tested.  QAOA is used as an optimization algorithm, not a true quantum
speedup in this context.
"""

from typing import Dict, Any

try:
    from qiskit_algorithms import QAOA
    from qiskit_algorithms.optimizers import COBYLA
    from qiskit.primitives import Sampler
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import SparsePauliOp  # type: ignore
except ImportError:
    # Qiskit is optional; if not available, provide stubs.
    QAOA = None  # type: ignore
    COBYLA = None  # type: ignore
    Sampler = None  # type: ignore
    QuantumCircuit = None  # type: ignore
    SparsePauliOp = None  # type: ignore


def build_cost_hamiltonian(routes: Dict[str, Dict[str, float]]) -> SparsePauliOp:
    """Build a cost Hamiltonian for QAOA.

    The cost function encodes profit (positive), risk (negative), and
    gas costs (negative) for each candidate route.  In this simple example,
    we treat each route as a binary decision variable; more complex
    encodings are possible.

    Parameters
    ----------
    routes: dict
        A mapping from route identifiers to a dict with keys 'profit',
        'risk', and optionally 'gas_cost'.  Profit increases the cost
        function, while risk and gas_cost decrease it.

    Returns
    -------
    SparsePauliOp
        A Qiskit Pauli operator representing the cost Hamiltonian.
    """
    # For a simple 3‑route example, we use 3 qubits; generalize as needed.
    n = len(routes)
    import itertools
    from qiskit.quantum_info import Pauli
    from qiskit.quantum_info import SparsePauliOp

    paulis = []
    coeffs = []

    for i, (name, vals) in enumerate(routes.items()):
        profit = vals.get("profit", 0.0)
        risk = vals.get("risk", 0.0)
        gas_cost = vals.get("gas_cost", 0.0)
        # For QAOA, we maximize cost; profit contributes positively,
        # risk and gas_cost contribute negatively
        coeff = profit - risk - gas_cost
        # Construct a Z operator on qubit i
        z_str = ["I"] * n
        z_str[i] = "Z"
        pauli = Pauli("".join(z_str))
        paulis.append(pauli)
        coeffs.append(coeff)

    return SparsePauliOp.from_list([(p.to_label(), c) for p, c in zip(paulis, coeffs)])


def _compute_route_score(route_data: Dict[str, float]) -> float:
    """Compute net score for a route: profit - risk - gas_cost.

    This is the SINGLE SOURCE OF TRUTH for route scoring.
    Used by both QAOA interpretation and classical fallback.
    """
    return (route_data.get("profit", 0.0)
            - route_data.get("risk", 0.0)
            - route_data.get("gas_cost", 0.0))


def optimize_routes(routes: Dict[str, Dict[str, float]]) -> str:
    """Run a QAOA optimization to select the best route.

    This function simulates a QAOA run.  If Qiskit is not installed, it
    falls back to a classical selection based on profit minus risk minus gas.

    Parameters
    ----------
    routes: dict
        Mapping of route names to profit/risk/gas_cost dicts.

    Returns
    -------
    str
        The key of the chosen route.

    Raises
    ------
    ValueError
        If routes dict is empty or contains invalid data.
    RuntimeError
        If QAOA computation fails.
    """
    if not routes:
        raise ValueError("Cannot optimize: routes dictionary is empty")

    # Validate route data
    for route_name, route_data in routes.items():
        if "profit" not in route_data or "risk" not in route_data:
            raise ValueError(f"Route '{route_name}' missing profit or risk data")
        if not isinstance(route_data["profit"], (int, float)):
            raise ValueError(f"Route '{route_name}' profit must be numeric")
        if not isinstance(route_data["risk"], (int, float)):
            raise ValueError(f"Route '{route_name}' risk must be numeric")

    if QAOA is None:
        # Classical fallback: choose the route with max score
        # FIXED: Now includes gas_cost via _compute_route_score
        return max(routes, key=lambda k: _compute_route_score(routes[k]))

    try:
        # Build cost Hamiltonian
        cost_hamiltonian = build_cost_hamiltonian(routes)
        sampler = Sampler()
        qaoa = QAOA(sampler=sampler, optimizer=COBYLA(), reps=1)

        # Dummy mixer (X on all qubits) for simplicity
        n = len(routes)
        qc_mixer = QuantumCircuit(n)
        for i in range(n):
            qc_mixer.h(i)

        result = qaoa.compute_minimum_eigenvalue(operator=cost_hamiltonian, mixer=qc_mixer)

        # Extract measurement counts
        counts = result.eigenstate.to_dict()

        # FIXED: Properly handle bitstring to route mapping
        # QAOA returns the state with highest probability after optimization
        # We need to find which qubit (route) has the highest activation
        best_bitstring = max(counts, key=counts.get)

        # Find the route with best score among activated qubits
        # Bitstring is in computational basis: |q(n-1)...q1q0⟩
        route_list = list(routes.keys())
        best_route = None
        best_score = float('-inf')

        for i, bit in enumerate(best_bitstring):
            if bit == '1' and i < len(route_list):
                route_name = route_list[i]
                # FIXED: Use centralized scoring function that includes gas_cost
                score = _compute_route_score(routes[route_name])
                if score > best_score:
                    best_score = score
                    best_route = route_name

        # If no route was selected (all bits 0), fall back to classical
        if best_route is None:
            return max(routes, key=lambda k: _compute_route_score(routes[k]))

        return best_route

    except Exception as e:
        # If QAOA fails, fall back to classical optimization
        print(f"Warning: QAOA optimization failed ({e}), using classical fallback")
        return max(routes, key=lambda k: _compute_route_score(routes[k]))
