from smart_doc_search.core.config import Settings


def test_mysql_url_uses_pymysql_driver() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="mysql://user:password@localhost/doc_search",
    )

    assert settings.database_url == (
        "mysql+pymysql://user:password@localhost/doc_search"
    )


def test_async_mysql_url_is_converted_to_sync_driver() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="mysql+asyncmy://user:password@localhost/doc_search",
    )

    assert settings.database_url.startswith("mysql+pymysql://")
