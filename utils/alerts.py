"""Count alert badges for sidebar indicators."""
from datetime import date, timedelta
from database.db import get_session
from database.models import Product, Order, OrderStatus, Service, ScheduleNotification
from config import EXPIRY_ALERT_DAYS


def get_inventory_alert_count() -> int:
    """Return total number of inventory alerts (low stock + expiring + expired)."""
    session = get_session()
    try:
        low = session.query(Product).filter(Product.stock <= Product.min_stock).count()
        alert_date = date.today() + timedelta(days=EXPIRY_ALERT_DAYS)
        expiring = session.query(Product).filter(
            Product.expiry_date.isnot(None),
            Product.expiry_date <= alert_date,
            Product.expiry_date >= date.today(),
        ).count()
        expired = session.query(Product).filter(
            Product.expiry_date.isnot(None),
            Product.expiry_date < date.today(),
        ).count()
        return low + expiring + expired
    finally:
        session.close()


def get_pending_orders_count() -> int:
    """Return number of pending orders."""
    session = get_session()
    try:
        return session.query(Order).filter(Order.status == OrderStatus.PENDING).count()
    finally:
        session.close()


def get_unpaid_services_count() -> int:
    """Return number of unpaid services."""
    session = get_session()
    try:
        return session.query(Service).filter(Service.is_paid == False).count()
    finally:
        session.close()


def get_schedule_notification_count(user_id: int) -> int:
    """Return number of unread schedule notifications for a worker."""
    session = get_session()
    try:
        return session.query(ScheduleNotification).filter_by(
            user_id=user_id, is_read=False
        ).count()
    finally:
        session.close()
