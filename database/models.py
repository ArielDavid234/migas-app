from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    ForeignKey, Text, Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


# ---------- Enums ----------

class UserRole(enum.Enum):
    ADMIN = "admin"
    WORKER = "worker"


class ShiftType(enum.Enum):
    MORNING = "morning"
    NIGHT = "night"


class RentStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"


class OrderStatus(enum.Enum):
    PENDING = "pending"
    RECEIVED = "received"


# ---------- Users & Auth ----------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), default=UserRole.WORKER, nullable=False)
    clock_code = Column(String(10), unique=True, nullable=False)
    hourly_rate = Column(Float, default=15.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    clock_records = relationship("ClockRecord", back_populates="user")
    reports = relationship("Report", back_populates="user")


class ClockRecord(Base):
    __tablename__ = "clock_records"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    clock_in = Column(DateTime, nullable=False, index=True)
    clock_out = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="clock_records")

    @property
    def hours_worked(self) -> float:
        if self.clock_out is None:
            return 0.0
        delta = self.clock_out - self.clock_in
        return round(delta.total_seconds() / 3600, 2)


# ---------- Inventory ----------

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    stock = Column(Integer, default=0)
    min_stock = Column(Integer, default=2)
    price = Column(Float, default=0.0)
    cost = Column(Float, default=0.0)
    expiry_date = Column(Date, nullable=True)
    arrival_date = Column(Date, nullable=True)
    supplier = Column(String(200), nullable=True)
    image_path = Column(String(500), nullable=True)
    is_consignment = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    category = relationship("Category", back_populates="products")


# ---------- Sales & Expenses ----------

class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, default=date.today, index=True)
    shift = Column(SAEnum(ShiftType), nullable=False)
    description = Column(String(300), nullable=True)
    amount = Column(Float, nullable=False)
    is_cafeteria = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.now)


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, default=date.today, index=True)
    description = Column(String(300), nullable=False)
    amount = Column(Float, nullable=False)
    is_merchandise = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)


# ---------- Reports ----------

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, default=date.today, index=True)
    shift = Column(SAEnum(ShiftType), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="reports")
    cigarette_counts = relationship("CigaretteCount", back_populates="report", cascade="all, delete-orphan")
    lottery_sales = relationship("LotterySale", back_populates="report", cascade="all, delete-orphan")
    checks = relationship("Check", back_populates="report", cascade="all, delete-orphan")
    tips = relationship("Tip", back_populates="report", cascade="all, delete-orphan")
    special_items = relationship("SpecialItemReport", back_populates="report", cascade="all, delete-orphan")


class CigaretteCount(Base):
    __tablename__ = "cigarette_counts"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False, index=True)
    brand = Column(String(100), nullable=False)
    boxes_start = Column(Integer, default=0)
    sold = Column(Integer, default=0)
    boxes_end = Column(Integer, default=0)

    report = relationship("Report", back_populates="cigarette_counts")


class LotterySale(Base):
    __tablename__ = "lottery_sales"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False, index=True)
    scratch_name = Column(String(100), nullable=False)
    amount = Column(Float, default=0.0)
    lotto_amount = Column(Float, default=0.0)

    report = relationship("Report", back_populates="lottery_sales")

    @property
    def total(self) -> float:
        return self.amount + self.lotto_amount


class Check(Base):
    __tablename__ = "checks"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False, index=True)
    description = Column(String(300), nullable=True)
    amount = Column(Float, nullable=False)

    report = relationship("Report", back_populates="checks")


class Tip(Base):
    __tablename__ = "tips"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)

    report = relationship("Report", back_populates="tips")


class SpecialItemReport(Base):
    __tablename__ = "special_item_reports"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False, index=True)
    item_name = Column(String(100), nullable=False)
    sold = Column(Integer, default=0)
    remaining = Column(Integer, default=0)

    report = relationship("Report", back_populates="special_items")


# ---------- Schedules ----------

class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    week_start = Column(Date, nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday ... 6=Sunday
    start_time = Column(String(5), nullable=False)  # "08:00"
    end_time = Column(String(5), nullable=False)    # "16:00"
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User")


# ---------- Rents ----------

class RentTenant(Base):
    """Personas o empresas a las que se les cobra renta."""
    __tablename__ = "rent_tenants"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    notes = Column(String(300), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class Rent(Base):
    __tablename__ = "rents"

    id = Column(Integer, primary_key=True)
    tenant = Column(String(100), nullable=False)
    month = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(SAEnum(RentStatus), default=RentStatus.PENDING)
    paid_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


# ---------- Services (agua, luz, basura) ----------

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)  # "Agua", "Corriente", "Basura"
    due_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=True)
    is_paid = Column(Boolean, default=False)
    paid_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


# ---------- Orders / Pedidos ----------

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    provider = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    amount = Column(Float, nullable=True)
    order_date = Column(Date, nullable=False)
    status = Column(SAEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

class FuelDelivery(Base):
    __tablename__ = "fuel_deliveries"

    id = Column(Integer, primary_key=True)
    delivery_date = Column(Date, nullable=False)
    gallons = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


# ---------- Monthly Salary Payments ----------

class MonthlySalaryPayment(Base):
    __tablename__ = "monthly_salary_payments"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    month = Column(Date, nullable=False, index=True)          # siempre el día 1 del mes
    hours_worked = Column(Float, nullable=False, default=0.0)
    hourly_rate = Column(Float, nullable=False, default=15.0)
    amount = Column(Float, nullable=False)         # hours_worked * hourly_rate
    is_paid = Column(Boolean, default=False)
    paid_date = Column(Date, nullable=True)
    notes = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User")


# ---------- Audit Log ----------

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False)       # CREATE, UPDATE, DELETE, LOGIN, LOGOUT, BACKUP
    target = Column(String(100), nullable=False)       # e.g. "Sale", "Product", "User"
    target_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User")


# ---------- Schedule Notifications ----------

class ScheduleNotification(Base):
    """Tracks unread schedule-published notifications for workers."""
    __tablename__ = "schedule_notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    week_start = Column(Date, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User")
