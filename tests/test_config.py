from app.core.config import get_settings


def test_settings_use_environment_override(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Test Navigator")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("PARSER_PROVIDER", "openai_responses")
    monkeypatch.setenv("PARSER_SHADOW_ENABLED", "false")
    monkeypatch.setenv("PARSER_SHADOW_PROVIDER", "deterministic")
    monkeypatch.setenv("PROFILE_PROVIDER", "deterministic")
    monkeypatch.setenv("PROFILE_SHADOW_ENABLED", "false")
    monkeypatch.setenv("PROFILE_SHADOW_PROVIDER", "deterministic")
    monkeypatch.setenv("STRUCTURED_PARSER_MODEL_NAME", "test-structured-model")
    monkeypatch.setenv("STRUCTURED_PARSER_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("STRUCTURED_PROFILE_MODEL_NAME", "test-profile-model")
    monkeypatch.setenv("STRUCTURED_PROFILE_TIMEOUT_SECONDS", "9.5")
    monkeypatch.setenv("PUSH_DELIVERY_ENABLED", "false")
    monkeypatch.setenv("PUSH_DELIVERY_CHANNEL", "webhook_sink")
    monkeypatch.setenv("PUSH_WEBHOOK_URL", "https://example.test/push")
    monkeypatch.setenv("PUSH_WEBHOOK_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("PUSH_DELIVERY_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app_name == "Test Navigator"
    assert settings.log_level == "DEBUG"
    assert settings.parser_provider == "openai_responses"
    assert settings.parser_shadow_enabled is False
    assert settings.parser_shadow_provider == "deterministic"
    assert settings.profile_provider == "deterministic"
    assert settings.profile_shadow_enabled is False
    assert settings.profile_shadow_provider == "deterministic"
    assert settings.structured_parser_validation_retries == 1
    assert settings.structured_parser_model_name == "test-structured-model"
    assert settings.structured_parser_timeout_seconds == 12.5
    assert settings.structured_profile_model_name == "test-profile-model"
    assert settings.structured_profile_timeout_seconds == 9.5
    assert settings.push_delivery_enabled is False
    assert settings.push_delivery_channel == "webhook_sink"
    assert settings.push_webhook_url == "https://example.test/push"
    assert settings.push_webhook_timeout_seconds == 12
    assert settings.push_delivery_max_attempts == 4
    assert settings.openai_base_url == "https://api.example.test/v1"
    assert settings.openai_api_key == "sk-test"

    get_settings.cache_clear()


def test_settings_support_gemini_direct_provider(monkeypatch):
    monkeypatch.setenv("PARSER_PROVIDER", "gemini_direct")
    monkeypatch.setenv("PARSER_SHADOW_ENABLED", "true")
    monkeypatch.setenv("PARSER_SHADOW_PROVIDER", "gemini_direct")
    monkeypatch.setenv("PROFILE_PROVIDER", "gemini_direct")
    monkeypatch.setenv("PROFILE_SHADOW_ENABLED", "true")
    monkeypatch.setenv("PROFILE_SHADOW_PROVIDER", "gemini_direct")
    monkeypatch.setenv("STRUCTURED_PARSER_MODEL_NAME", "gemini-2.5-flash")
    monkeypatch.setenv("STRUCTURED_PROFILE_MODEL_NAME", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
    monkeypatch.setenv("STRUCTURED_PARSER_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("STRUCTURED_PROFILE_TIMEOUT_SECONDS", "11")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.parser_provider == "gemini_direct"
    assert settings.parser_shadow_enabled is True
    assert settings.parser_shadow_provider == "gemini_direct"
    assert settings.profile_provider == "gemini_direct"
    assert settings.profile_shadow_enabled is True
    assert settings.profile_shadow_provider == "gemini_direct"
    assert settings.structured_parser_model_name == "gemini-2.5-flash"
    assert settings.structured_profile_model_name == "gemini-2.5-flash"
    assert settings.gemini_api_key == "gemini-test-key"
    assert settings.gemini_base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert settings.structured_parser_timeout_seconds == 15
    assert settings.structured_profile_timeout_seconds == 11

    get_settings.cache_clear()
