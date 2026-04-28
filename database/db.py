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
    """Crea todas las tablas si no existen y aplica migraciones ligeras."""
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate():
    """Agrega columnas nuevas a tablas existentes (SQLite no soporta ALTER TABLE IF NOT EXISTS)."""
    migrations = [
        ("products", "arrival_date",    "DATE"),
        ("products", "supplier",        "VARCHAR(200)"),
        ("products", "status",          "VARCHAR(20) NOT NULL DEFAULT 'active'"),
        ("products", "approved_by_id",  "INTEGER"),
        ("products", "approved_at",     "DATETIME"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                    )
                )
                conn.commit()
            except Exception:
                pass  # columna ya existe


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
