# EVE_Q++ Gate 1 Release Criteria v0.1

This branch may merge as pilot infrastructure when:

- all synthetic boundary tests pass on Python 3.11 and 3.13;
- the snapshot schema validates;
- the launcher remains read-only;
- the threat model and rollback plan remain explicitly draft;
- no live source is selected or contacted by CI;
- Gate 0 remains active;
- Gate 1 remains pilot-only;
- Gate 2–6 remain locked.

Merging this branch does not activate Gate 1. Activation requires later live-read-only evidence, tested rollback, and explicit human promotion.
