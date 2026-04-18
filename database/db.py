from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from config import DATABASE_URL
from database.models import Base

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")    # lecturas concurrentes mientras escribe
    cursor.execute("PRAGMA foreign_keys=ON")     # hace cumplir integridad referencial
    cursor.execute("PRAGMA cache_size=-16000")   # 16 MB de cache en memoria
    cursor.execute("PRAGMA synchronous=NORMAL")  # más rápido que FULL, seguro con WAL
    cursor.close()

SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Crea todas las tablas si no existen."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Devuelve una sesión de base de datos (uso manual con try/finally)."""
    return SessionLocal()


@contextmanager
def db_session():
    """Context manager — cierra y hace rollback automáticamente si hay error.

    Uso:
        with db_session() as session:
            session.add(obj)
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
