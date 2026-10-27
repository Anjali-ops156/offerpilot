import socket
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from offerpilot.config import DATA_DIR, DATABASE_URL
from offerpilot.db.models import Base

DATA_DIR.mkdir(parents=True, exist_ok=True)


def _connect_args(database_url: str) -> dict:
    # check_same_thread is a SQLite-only pysqlite option — passing it to
    # psycopg2 (Postgres) raises "invalid dsn". Only set it for sqlite:// URLs.
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}

    if not database_url.startswith("postgresql"):
        return {}

    args: dict = {"connect_timeout": 10}

    # Some networks have a broken/black-holed IPv6 route to the host while
    # IPv4 works fine. DNS often lists the IPv6 address first, and libpq
    # does NOT reliably fall back to a later address from a single hostname
    # — it can hang far longer than connect_timeout on the dead route. Pre-
    # resolve to IPv4 ourselves and pass it as hostaddr (keeping `host` so
    # TLS hostname verification still works) to sidestep this entirely.
    # Harmless on a network where IPv6 works fine too — same IPv4 endpoint.
    hostname = urlparse(database_url).hostname
    if hostname:
        try:
            ipv4 = socket.getaddrinfo(hostname, None, socket.AF_INET)[0][4][0]
            args["hostaddr"] = ipv4
        except OSError:
            pass  # fall back to normal DNS resolution if this fails for any reason
    return args


engine = create_engine(DATABASE_URL, connect_args=_connect_args(DATABASE_URL), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
