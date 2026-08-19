from __future__ import annotations

import pathlib
import tomllib
import unittest

import agentack


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def _project(self):
        with (ROOT / "pyproject.toml").open("rb") as handle:
            return tomllib.load(handle)["project"]

    def test_version_is_consistent_across_package_metadata(self):
        project = self._project()
        self.assertEqual(project["version"], agentack.__version__)
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        self.assertIn(f"version: {agentack.__version__}", citation)

    def test_readme_uses_published_pypi_install_paths(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("pipx install agentack", readme)
        self.assertIn("python -m pip install agentack", readme)

    def test_social_card_is_present_referenced_and_placeholder_removed(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        social_dir = ROOT / "assets" / "social"
        social_card = social_dir / "github-social-card-agentack.png"
        placeholder = social_dir / "README.md"
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        self.assertTrue(social_card.is_file())
        self.assertGreater(social_card.stat().st_size, 0)
        self.assertIn("assets/social/github-social-card-agentack.png", readme)
        self.assertFalse(placeholder.exists())
        self.assertIn("include assets/social/github-social-card-agentack.png", manifest)
        self.assertNotIn("assets/social/README.md", manifest)

    def test_python_314_is_advertised(self):
        project = self._project()
        self.assertIn("Programming Language :: Python :: 3.14", project["classifiers"])
        self.assertEqual(project["requires-python"], ">=3.11")

    def test_public_codex_claims_are_detection_only(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        coverage = (ROOT / "docs" / "live-coverage.md").read_text(encoding="utf-8")
        codex_doc = (ROOT / "docs" / "codex-cli.md").read_text(encoding="utf-8")
        self.assertNotIn("| Codex CLI | yes | **yes**", readme)
        self.assertNotIn("Integration: Codex CLI\n\nProbe isolation              PASS", readme)
        self.assertIn("| Codex CLI | yes | no", readme)
        self.assertIn("does **not currently advertise a verified Codex live approval-integrity test**", codex_doc)
        for line in coverage.splitlines():
            if line.startswith("| `ACK"):
                self.assertIn("| TRACE |", line)


if __name__ == "__main__":
    unittest.main()
