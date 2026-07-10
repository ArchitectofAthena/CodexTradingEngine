# Phase 2C-2 Verification Checklist

- [x] route/provider/bucket geometry is deterministic
- [x] provider capacities and fees are explicit inputs
- [x] infeasible candidates receive a QUBO penalty
- [x] QAOA-compatible variables identify complete geometries
- [x] a separate Rust binary reconstructs route identity
- [x] Rust verifies borrowed-asset alignment
- [x] Rust verifies capacity, repayment, and minimum net profit
- [x] Python uses an absolute executable path and `shell=False`
- [x] request and response sizes are bounded
- [x] request and response schemas are strict
- [x] candidate identity drift is rejected
- [x] authority escalation is rejected
- [x] no network, wallet, signer, scheduler, RPC, or borrowing surface exists
- [x] all artifacts retain `authority: false`

The remaining proof obligation is GitHub CI on Python 3.11/3.13, Qiskit 2.5, and stable Rust using the compiled binaries.
