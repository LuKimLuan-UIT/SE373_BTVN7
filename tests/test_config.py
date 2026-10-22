"""Test đọc cấu hình từ `.env` — đặc biệt là trường hợp đã điền key sau khi server chạy."""

from __future__ import annotations

from memory_agent import config, paths


def write_env(tmp_path, content: str):
    env_path = tmp_path / ".env"
    env_path.write_text(content, encoding="utf-8")
    return env_path


def test_reads_key_and_model(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ENV_PATH", write_env(tmp_path, "OPENAI_API_KEY=sk-test\nMODEL_NAME=gpt-4o-mini\n"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)

    settings, missing = config.load_settings()
    assert missing == []
    assert settings is not None
    assert settings.api_key == "sk-test"
    assert settings.model_name == "gpt-4o-mini"


def test_filling_key_after_start_is_picked_up(tmp_path, monkeypatch):
    """Regression: `.env` trống lúc start, sau đó điền key -> phải nhận được.

    Với `load_dotenv(override=False)`, key rỗng đã nằm trong `os.environ` nên
    các lần đọc sau vẫn thấy giá trị rỗng -> app báo thiếu cấu hình.
    """
    env_path = write_env(tmp_path, "OPENAI_API_KEY=\nMODEL_NAME=\n")
    monkeypatch.setattr(paths, "ENV_PATH", env_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)

    settings, missing = config.load_settings()
    assert settings is None
    assert missing == ["OPENAI_API_KEY", "MODEL_NAME"]

    # Người dùng điền key (không cần restart server)
    write_env(tmp_path, "OPENAI_API_KEY=sk-test\nMODEL_NAME=gpt-4o-mini\n")

    settings, missing = config.load_settings()
    assert missing == []
    assert settings.api_key == "sk-test"


def test_flags_and_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(
        paths,
        "ENV_PATH",
        write_env(tmp_path, "OPENAI_API_KEY=k\nMODEL_NAME=m\nMEMORY_LONG_TERM=0\nMEMORY_PLACEMENT=end\n"),
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)

    settings, _ = config.load_settings()
    assert settings.enable_long_term_memory is False
    assert settings.memory_placement == "end"
