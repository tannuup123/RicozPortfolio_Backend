import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base

# We connect to localhost:5432 because we are running tests locally against the Docker DB
TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/ricozportfolio_test"

import os
from alembic.config import Config
from alembic import command
from app.core.config import settings

@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(bind=engine)
    
    # Save original URL and override for alembic
    orig_url = settings.DATABASE_URL
    settings.DATABASE_URL = TEST_DATABASE_URL
    
    try:
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
        command.upgrade(alembic_cfg, "head")
        
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        settings.DATABASE_URL = orig_url

@pytest.fixture
def db_session(db_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()
