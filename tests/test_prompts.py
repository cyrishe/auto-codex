from pathlib import Path

import pytest

from codexflow.prompts import PromptRenderError, PromptRenderer


def test_prompt_renderer_loads_packaged_template_and_injects_safety() -> None:
    rendered = PromptRenderer().render(
        "dev_design",
        {
            "CONTEXT": "context body",
            "ISSUE": "issue body",
        },
    )

    assert "不允许泄露密钥" in rendered.content
    assert "context body" in rendered.content
    assert "issue body" in rendered.content
    assert "{{CONTEXT}}" not in rendered.content


def test_prompt_renderer_requires_all_variables() -> None:
    with pytest.raises(PromptRenderError, match="ISSUE"):
        PromptRenderer().render("dev_design", {"CONTEXT": "context"})


def test_prompt_renderer_writes_rendered_prompt(tmp_path: Path) -> None:
    output = tmp_path / "prompt.md"

    PromptRenderer().render_to_file(
        "review_code",
        {
            "ISSUE": "issue",
            "DESIGN_JSON": "{}",
            "GIT_DIFF": "diff",
            "TEST_LOG": "passed",
            "SAFETY_SCAN": "ok",
        },
        output,
    )

    assert output.exists()
    assert "passed" in output.read_text(encoding="utf-8")


def test_prompt_renderer_uses_user_template_directory(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "dev_design.md").write_text("Custom {{ISSUE}} {{CONTEXT}}", encoding="utf-8")

    rendered = PromptRenderer(templates_dir=templates).render(
        "dev_design",
        {
            "CONTEXT": "context",
            "ISSUE": "issue",
        },
    )

    assert "Custom issue context" in rendered.content
