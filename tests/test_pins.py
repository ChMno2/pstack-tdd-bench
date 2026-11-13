import json
import subprocess

from bench.pins import LIMS_COMMIT, PSTACK_COMMIT, REPO_ROOT


def test_lims_submodule_is_pinned():
    head = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT / "sut/lims"), "rev-parse", "HEAD"], text=True
    ).strip()
    assert head == LIMS_COMMIT == "227be16e3365e9956da0dec8efa987db3e0f3e4f"


def test_vendored_pstack_matches_pinned_commit():
    manifest = json.loads((REPO_ROOT / "vendor/pstack/.claude-plugin/plugin.json").read_text())
    assert manifest["version"] == "0.15.36"
    assert PSTACK_COMMIT in (REPO_ROOT / "vendor/pstack/PROVENANCE.md").read_text()
    assert (REPO_ROOT / "vendor/pstack/LICENSE").exists()
