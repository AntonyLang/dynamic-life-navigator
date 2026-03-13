from app.core.config import get_settings


def test_settings_use_environment_override(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Test Navigator")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("PARSER_PROVIDER", "openai_responses")
    monkeypatch.setenv("STRUCTURED_PARSER_MODEL_NAME", "test-structured-model")
    monkeypatch.setenv("STRUCTURED_PARSER_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app_name == "Test Navigator"
    assert settings.log_level == "DEBUG"
    assert settings.parser_provider == "openai_responses"
    assert settings.structured_parser_validation_retries == 1
    assert settings.structured_parser_model_name == "test-structured-model"
    assert settings.structured_parser_timeout_seconds == 12.5
    assert settings.openai_base_url == "https://api.example.test/v1"
    assert settings.openai_api_key == "sk-test"

    get_settings.cache_clear()


def test_settings_support_gemini_direct_provider(monkeypatch):
    monkeypatch.setenv("PARSER_PROVIDER", "gemini_direct")
    monkeypatch.setenv("STRUCTURED_PARSER_MODEL_NAME", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
    monkeypatch.setenv("STRUCTURED_PARSER_TIMEOUT_SECONDS", "15")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.parser_provider == "gemini_direct"
    assert settings.structured_parser_model_name == "gemini-2.5-flash"
    assert settings.gemini_api_key == "gemini-test-key"
    assert settings.gemini_base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert settings.structured_parser_timeout_seconds == 15

    get_settings.cache_clear()
