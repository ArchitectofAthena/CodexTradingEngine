"""Regression checks for security detection and the Python 3.11 report path."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'scripts/security_audit_v0_1.py'
SPEC = importlib.util.spec_from_file_location('codex_security_audit', PATH)
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


class SecurityAuditRegressionTests(unittest.TestCase):
    def test_mutable_actions_in_mapping_and_list_forms(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workflows = root / '.github/workflows'
            workflows.mkdir(parents=True)
            (workflows/'sample.yml').write_text(
                'steps:\n  - uses: actions/checkout@v7\n'
                '  - name: setup\n    uses: actions/setup-python@main\n'
                '  - uses: actions/checkout@' + 'a'*40 + '\n'
                '  - uses: ./local\n  - uses: docker://alpine:3\n')
            findings = audit.scan_workflows(root)
            mutable = [f for f in findings if f.rule_id == 'GH003']
            self.assertEqual([f.line for f in mutable], [2,4])

    def test_markdown_escapes_pipe_in_finding(self):
        finding = audit.Finding('PY001','HIGH','file.py',3,'unsafe | call','hash')
        self.assertIn('unsafe \\| call', audit.markdown([finding],0))

    def test_multiline_action_scalar_remains_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            workflows=root/'.github/workflows'
            workflows.mkdir(parents=True)
            (workflows/'sample.yml').write_text(
                'steps:\n  - name: Checkout\n    uses:\n      actions/checkout@v7\n')
            findings=audit.scan_workflows(root)
            self.assertEqual([f.rule_id for f in findings],['GH003'])
            self.assertEqual(findings[0].line,3)

    def test_existing_python_and_container_detection_remains(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'unsafe.py').write_text('import subprocess\neval("1")\nsubprocess.run("echo x", shell=True)\n')
            (root/'compose.yml').write_text('services:\n  app:\n    privileged: true\n')
            self.assertEqual({f.rule_id for f in audit.scan_python(root)}, {'PY001','PY003'})
            self.assertIn('CTR001', {f.rule_id for f in audit.scan_containers(root)})

    def test_high_confidence_secret_is_redacted(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            # Construct a synthetic token locally; this is not a credential.
            (root/'source.txt').write_text('ghp_' + 'aB3z'*10)
            findings=audit.scan_secrets(root)
            self.assertEqual([f.rule_id for f in findings], ['SEC003'])
            self.assertIn('redacted',findings[0].message)
            self.assertNotIn('aB3z',audit.markdown(findings,0))


if __name__=='__main__':
    unittest.main()
