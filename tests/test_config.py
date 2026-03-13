from app.core.config import get_settings


def test_settings_use_environment_override(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Test Navigator")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app_name == "Test Navigator"
    assert settings.log_level == "DEBUG"

    get_settings.cache_clear()
