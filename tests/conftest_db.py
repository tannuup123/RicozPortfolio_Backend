import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base

# We connect to localhost:5432 because we are running tests locally against the Docker DB
TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/ricozportfolio_test"

from alembic.config import Config
from alembic import command
from app.core.config import settings

@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DATABASE_URL)

    # Save original URL and override for alembic env.py
    orig_url = settings.DATABASE_URL
    settings.DATABASE_URL = TEST_DATABASE_URL

    try:
        # Drop and recreate the public schema atomically.
        # This wipes all tables (including alembic_version) regardless of
        # whether CI or a previous local run has already migrated the DB.
        # Using schema recreation is more reliable than `alembic downgrade base`
        # because the downgrade chain requires every table to exist, which fails
        # if the DB is already partially or fully torn down.
        with engine.connect() as conn:
            conn.execute(sa.text("DROP SCHEMA public CASCADE"))
            conn.execute(sa.text("CREATE SCHEMA public"))
            conn.commit()

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
        command.upgrade(alembic_cfg, "head")

        yield engine
    finally:
        with engine.connect() as conn:
            conn.execute(sa.text("DROP SCHEMA public CASCADE"))
            conn.execute(sa.text("CREATE SCHEMA public"))
            conn.commit()
        engine.dispose()
        settings.DATABASE_URL = orig_url

@pytest.fixture
def db_session(db_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()
