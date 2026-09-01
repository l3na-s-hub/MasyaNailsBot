from datetime import datetime, date, time
from typing import Optional, List
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Date, Time, Text, Float,
    ForeignKey, JSON, BigInteger, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # сколько завершённых визитов (для бонуса на 5-ю)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)

    bookings: Mapped[List["Booking"]] = relationship(back_populates="user")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    base_price: Mapped[float] = mapped_column(Float, default=0.0)
    # цвет Google Calendar: 1-11
    calendar_color_id: Mapped[str] = mapped_column(String(5), default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    has_complex_flow: Mapped[bool] = mapped_column(Boolean, default=False)

    parameters: Mapped[List["ServiceParameter"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )
    bookings: Mapped[List["Booking"]] = relationship(back_populates="service")


class ServiceParameter(Base):
    __tablename__ = "service_parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    step_code: Mapped[str] = mapped_column(String(50), nullable=False)
    step_title: Mapped[str] = mapped_column(String(255), nullable=False)
    option_code: Mapped[str] = mapped_column(String(100), nullable=False)
    option_text: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_modifier: Mapped[int] = mapped_column(Integer, default=0)
    price_modifier: Mapped[float] = mapped_column(Float, default=0.0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    requires_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    service: Mapped["Service"] = relationship(back_populates="parameters")

    __table_args__ = (
        UniqueConstraint("service_id", "step_code", "option_code", name="uq_service_param"),
    )


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)

    selected_params: Mapped[dict] = mapped_column(JSON, default=dict)

    total_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    surcharge: Mapped[float] = mapped_column(Float, default=0.0)  # доплата за слот

    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    # confirmed | pending_payment | pending_photo | cancelled | completed | no_show
    status: Mapped[str] = mapped_column(String(30), default="pending_payment")
    photo_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_photo_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # «от кого перевод»
    calendar_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    admin_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    day_confirm_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    day_confirm_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # yes/no/none
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reschedule_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="bookings")
    service: Mapped["Service"] = relationship(back_populates="bookings")


class ScheduleDay(Base):
    """День + список слотов. slots: [{"time":"10:00","surcharge":0,"label":""}, ...]"""
    __tablename__ = "schedule_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=False)
    # Новый формат: список объектов. Старый: список строк "HH:MM" — поддерживаем оба
    available_slots: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class ContentBlock(Base):
    __tablename__ = "content_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # медиа к блоку
    media_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # legacy single
    media_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # photo/video
    # несколько медиа: [{"file_id": "...", "type": "photo"|"video"}, ...]
    media_items: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdminLog(Base):
    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
