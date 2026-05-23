from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

from codexflow.config import CodexConfig
from codexflow.pipeline import Pipeline

from .integration_support import TrackingGitHub, init_toy_repo, toy_config, toy_issue


pytestmark = pytest.mark.skipif(
    os.environ.get("CODEXFLOW_REAL_CODEX") != "1" or shutil.which("codex") is None,
    reason="set CODEXFLOW_REAL_CODEX=1 and install codex to run the real Codex boundary test",
)


def test_phase2_real_codex_toy_repo_boundary(tmp_path: Path) -> None:
    repo = init_toy_repo(tmp_path / "toy-repo")
    config = toy_config(
        tmp_path,
        repo,
        codex=CodexConfig(
            design_timeout_seconds=300,
            review_timeout_seconds=300,
            implement_timeout_seconds=600,
            extra_args=["--ephemeral"],
        ),
    )
    github = TrackingGitHub(issue=toy_issue())

    result = Pipeline(config=config, github=github).run_next()

    assert result is not None
    assert result.status == "DONE"
    assert result.commit_sha is not None
    assert github.labels == {"codex:review"}

    design = json.loads((result.run_dir / "01_dev_design.output.json").read_text(encoding="utf-8"))
    assert "multiply" in json.dumps(design).lower()

    design_review = json.loads((result.run_dir / "02_review_design.output.json").read_text(encoding="utf-8"))
    assert design_review["verdict"] == "pass"

    code_reviews = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(result.run_dir.glob("06_review_code*.output.json"))
    ]
    assert code_reviews
    assert code_reviews[-1]["verdict"] == "pass"

    diff = (result.run_dir / "04_git_diff.patch").read_text(encoding="utf-8").lower()
    assert "multiply" in diff

    test_log = (result.run_dir / "05_test.log").read_text(encoding="utf-8")
    assert "status: pass" in test_log
