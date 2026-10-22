from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from offerpilot.config import DATA_DIR, DATABASE_URL
from offerpilot.db.models import Base

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
