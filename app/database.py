import os

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


def get_session():
    with Session(engine) as session:
        yield session
