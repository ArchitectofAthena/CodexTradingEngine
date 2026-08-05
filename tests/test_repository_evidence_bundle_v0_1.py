from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "build_repository_evidence.py"
SPEC = importlib.util.spec_from_file_location("build_repository_evidence", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


class RepositoryEvidenceBundleTests(unittest.TestCase):
    def test_hidden_repository_paths_keep_their_leading_dot(self) -> None:
        path = ".github/workflows/evidence.yml"

        self.assertEqual(EVIDENCE.normalize_path(path), path)
        self.assertEqual(EVIDENCE.normalize_path(f"./{path}"), path)
        self.assertTrue(EVIDENCE.path_allowed(path))

    def test_absolute_and_parent_traversal_paths_fail_closed(self) -> None:
        self.assertFalse(EVIDENCE.path_allowed("/.github/workflows/evidence.yml"))
        self.assertFalse(EVIDENCE.path_allowed("../.github/workflows/evidence.yml"))
        self.assertFalse(EVIDENCE.path_allowed("scripts/../../.github/workflows/evidence.yml"))
        self.assertFalse(EVIDENCE.path_allowed("."))
        self.assertFalse(EVIDENCE.path_allowed(""))

    def test_bundle_includes_allowlisted_hidden_workflow_in_all_evidence_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init", "-b", "main")
            git(repo, "config", "user.name", "Evidence Test")
            git(repo, "config", "user.email", "evidence@example.invalid")

            (repo / "README.md").write_text("base\n", encoding="utf-8")
            git(repo, "add", "README.md")
            git(repo, "commit", "-m", "base")
            base_sha = git(repo, "rev-parse", "HEAD")

            workflow = repo / ".github" / "workflows" / "evidence.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("name: evidence\n", encoding="utf-8")
            git(repo, "add", ".github/workflows/evidence.yml")
            git(repo, "commit", "-m", "add evidence workflow")
            head_sha = git(repo, "rev-parse", "HEAD")

            bundle = EVIDENCE.build_bundle(
                repo=repo,
                repository="example/evidence",
                base_ref=base_sha,
                head_ref=head_sha,
            )

            changed_paths = {entry["path"] for entry in bundle["changed_files"]}
            manifest_paths = {entry["path"] for entry in bundle["manifest_hashes"]}

            self.assertIn(".github/workflows/evidence.yml", changed_paths)
            self.assertIn(".github/workflows/evidence.yml", manifest_paths)
            self.assertIn(
                "diff --git a/.github/workflows/evidence.yml b/.github/workflows/evidence.yml",
                bundle["diff"],
            )
            self.assertFalse(bundle["redaction"]["truncated"])
            self.assertFalse(bundle["authority"]["artifact_is_command"])
            self.assertTrue(bundle["authority"]["human_promotion_required"])


if __name__ == "__main__":
    unittest.main()
