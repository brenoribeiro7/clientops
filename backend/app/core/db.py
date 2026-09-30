from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine

from app.core.config import ApiSettings

metadata = MetaData()


def create_database_engine(settings: ApiSettings) -> Engine:
    return create_engine(
        settings.DATABASE_URL.get_secret_value(),
        pool_pre_ping=True,
        pool_timeout=2,
        connect_args={"connect_timeout": 2, "options": "-c statement_timeout=2000"},
    )
