from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
USES_LINE = re.compile(r"^\s*uses:\s*([^\s#]+)(?:\s+#\s*(.+))?\s*$")
FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")

REVIEWED_PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "dtolnay/rust-toolchain": "4cda84d5c5c54efe2404f9d843567869ab1699d4",
}


def test_all_third_party_workflow_actions_use_immutable_refs() -> None:
    findings: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            match = USES_LINE.match(line)
            if not match:
                continue
            spec, _comment = match.groups()
            if spec.startswith(("./", "docker://")):
                continue
            if "@" not in spec:
                findings.append(f"{path.name}:{line_number}: missing action ref")
                continue
            action, ref = spec.rsplit("@", 1)
            if not FULL_SHA.fullmatch(ref):
                findings.append(
                    f"{path.name}:{line_number}: {action} uses mutable ref {ref!r}"
                )
                continue
            expected = REVIEWED_PINS.get(action)
            if expected is not None and ref.lower() != expected:
                findings.append(
                    f"{path.name}:{line_number}: {action} does not use reviewed pin"
                )

    assert findings == [], "\n".join(findings)
