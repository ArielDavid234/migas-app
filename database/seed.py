import hashlib
from database.db import get_session, init_db
from database.models import User, Category, UserRole
from config import DEFAULT_CATEGORIES, HOURLY_RATE, APP_SALT


def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), APP_SALT.encode(), 100_000
    ).hex()


def seed_categories(session):
    existing = {c.name for c in session.query(Category).all()}
    for name in DEFAULT_CATEGORIES:
        if name not in existing:
            session.add(Category(name=name))
    session.commit()
    print(f"  ✓ {len(DEFAULT_CATEGORIES)} categorías verificadas")


def seed_admin(session):
    admin = session.query(User).filter_by(username="admin").first()
    if not admin:
        admin = User(
            name="Administrador",
            username="admin",
            password_hash=hash_password("admin123"),
            role=UserRole.ADMIN,
            clock_code="0000",
            hourly_rate=HOURLY_RATE,
        )
        session.add(admin)
        session.commit()
        print("  ✓ Usuario admin creado (usuario: admin, contraseña: admin123)")
    else:
        print("  ✓ Usuario admin ya existe")

    # ArielDavid admin
    ariel = session.query(User).filter_by(username="ArielDavid").first()
    if not ariel:
        ariel = User(
            name="Ariel David",
            username="ArielDavid",
            password_hash=hash_password("A.rielD12345"),
            role=UserRole.ADMIN,
            clock_code="1111",
            hourly_rate=HOURLY_RATE,
        )
        session.add(ariel)
        session.commit()
        print("  ✓ Usuario ArielDavid creado (admin)")
    else:
        print("  ✓ Usuario ArielDavid ya existe")


def seed_demo_workers(session):
    # Jennifer — worker
    jennifer = session.query(User).filter_by(username="jennifer").first()
    if not jennifer:
        session.add(User(
            name="Jennifer",
            username="jennifer",
            password_hash=hash_password("jen123"),
            role=UserRole.WORKER,
            clock_code="1234",
            hourly_rate=HOURLY_RATE,
        ))

    # Daylin — admin
    daylin = session.query(User).filter_by(username="daylin").first()
    if not daylin:
        session.add(User(
            name="Daylin",
            username="daylin",
            password_hash=hash_password("day123"),
            role=UserRole.ADMIN,
            clock_code="5678",
            hourly_rate=HOURLY_RATE,
        ))
    else:
        # Ensure existing Daylin is admin
        daylin.role = UserRole.ADMIN

    session.commit()
    print("  ✓ Trabajadoras verificadas (Jennifer=worker, Daylin=admin)")


def run_seed():
    print("Inicializando base de datos...")
    init_db()
    session = get_session()
    try:
        seed_categories(session)
        seed_admin(session)
        seed_demo_workers(session)
        print("¡Seed completado!")
    finally:
        session.close()


if __name__ == "__main__":
    run_seed()
