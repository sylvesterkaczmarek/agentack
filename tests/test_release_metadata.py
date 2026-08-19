from __future__ import annotations

import pathlib
import tomllib
import unittest

import agentack


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_version_is_consistent_across_package_metadata(self):
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
        self.assertEqual(project["version"], agentack.__version__)
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        self.assertIn(f"version: {agentack.__version__}", citation)

    def test_readme_uses_published_pypi_install_paths(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("pipx install agentack", readme)
        self.assertIn("python -m pip install agentack", readme)

    def test_social_card_reference_is_absent_until_png_exists(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        social_card = ROOT / "assets" / "social" / "github-social-card-agentack.png"
        if not social_card.exists():
            self.assertNotIn("github-social-card-agentack.png", readme)
