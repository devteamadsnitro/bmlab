import os

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, SQLModel, create_engine


def _normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


DATABASE_URL = _normalize_url(os.getenv("DATABASE_URL", "sqlite:///./bmlab.db"))
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_column_if_missing("user", "email", "VARCHAR")


def _add_column_if_missing(table: str, column: str, sql_type: str) -> None:
    with engine.connect() as conn:
        try:
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {column} {sql_type}'))
            conn.commit()
        except DBAPIError:
            conn.rollback()


def get_session():
    with Session(engine) as session:
        yield session
