from codexflow.secret_filter import SecretFilter, matches_any


def test_secret_filter_excludes_configured_and_secret_paths() -> None:
    filter_ = SecretFilter(exclude_patterns=["node_modules/**"])

    assert not filter_.should_include("node_modules/pkg/index.js").included
    assert filter_.should_include("node_modules/pkg/index.js").reason == "excluded_by_config"
    assert not filter_.should_include(".env").included
    assert filter_.should_include(".env").reason == "secret_path"
    assert filter_.should_include("src/app.py").included


def test_secret_filter_tracks_protected_paths() -> None:
    filter_ = SecretFilter(protected_patterns=["prod.yaml", "**/*token*"])

    assert filter_.is_protected_path("prod.yaml")
    assert filter_.is_protected_path("config/api-token.txt")
    assert not filter_.is_protected_path("src/app.py")


def test_matches_any_matches_basename_and_glob() -> None:
    assert matches_any("src/.env", [".env"])
    assert matches_any("config/client-secret.json", ["**/*secret*"])
    assert not matches_any("config/client.json", ["**/*secret*"])


def test_secret_filter_redacts_sensitive_content() -> None:
    content = """OPENAI_API_KEY=sk-testabcdefghijklmnopqrstuvwxyz
github_token: ghp_abcdefghijklmnopqrstuvwxyz123456
normal=value
"""

    redacted = SecretFilter().redact_text(content)

    assert "sk-test" not in redacted
    assert "ghp_" not in redacted
    assert "OPENAI_API_KEY=[REDACTED]" in redacted
    assert "github_token: [REDACTED]" in redacted
    assert "normal=value" in redacted
