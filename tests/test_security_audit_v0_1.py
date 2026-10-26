from pathlib import Path

from scripts.security_audit_v0_1 import scan_workflows


def test_scan_workflows_detects_list_form_mutable_action_refs(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    workflow = workflows / "mutable.yml"
    workflow.write_text(
        """name: mutable
jobs:
  demo:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
""",
        encoding="utf-8",
    )

    findings = scan_workflows(tmp_path)

    assert [item.rule_id for item in findings] == ["GH003", "GH003"]
    assert all(item.severity == "MEDIUM" for item in findings)
    assert "actions/checkout" in findings[0].message
    assert "actions/setup-python" in findings[1].message
