from sqlalchemy.engine import make_url

from app.core.config import Settings


def test_database_credentials_round_trip_special_characters():
    settings = Settings(
        _env_file=None,
        postgres_user="user@name",
        postgres_password="p @/+:%#",
        postgres_host="::1",
        postgres_db="research",
    )
    url = make_url(settings.database_url)
    assert url.username == settings.postgres_user
    assert url.password == settings.postgres_password
    assert url.host == settings.postgres_host
    assert url.database == settings.postgres_db
