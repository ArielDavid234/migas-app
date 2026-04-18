"""Audit log helper — record user actions for accountability."""

from database.db import get_session
from database.models import AuditLog


def log_action(user_id: int | None, action: str, target: str, target_id: int | None = None, details: str | None = None):
    """Write an audit entry. Safe to call from anywhere — never raises."""
    try:
        session = get_session()
        try:
            entry = AuditLog(
                user_id=user_id,
                action=action,
                target=target,
                target_id=target_id,
                details=details,
            )
            session.add(entry)
            session.commit()
        finally:
            session.close()
    except Exception:
        pass  # Audit should never break the app
