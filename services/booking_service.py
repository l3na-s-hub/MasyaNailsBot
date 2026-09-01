from datetime import date, time, datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from database.models import User, Booking, Service
from config import TZ


class BookingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(self, telegram_id: int, username: str | None, full_name: str | None) -> User:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=telegram_id, username=username, full_name=full_name)
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
        else:
            changed = False
            if username and user.username != username:
                user.username = username
                changed = True
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                changed = True
            if changed:
                await self.session.commit()
        return user

    async def is_blacklisted(self, telegram_id: int) -> bool:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        return bool(user and user.is_blacklisted)

    async def set_blacklist(self, telegram_id: int, value: bool) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            return None
        user.is_blacklisted = value
        await self.session.commit()
        return user

    async def create_booking(
        self, user, service, selected_params, duration, price,
        booking_date, start_time, photo_file_id=None, status="pending_payment",
        surcharge=0.0, payment_note=None, payment_photo_file_id=None,
    ) -> Booking:
        end_dt = datetime.combine(booking_date, start_time) + timedelta(minutes=duration)
        booking = Booking(
            user_id=user.id,
            service_id=service.id,
            selected_params=selected_params,
            total_duration_minutes=duration,
            total_price=price + surcharge,
            surcharge=surcharge,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_dt.time(),
            status=status,
            photo_file_id=photo_file_id,
            payment_note=payment_note,
            payment_photo_file_id=payment_photo_file_id,
        )
        self.session.add(booking)
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    async def get_user_active_bookings(self, user_id: int) -> List[Booking]:
        today = datetime.now(TZ).date()
        result = await self.session.execute(
            select(Booking)
            .options(selectinload(Booking.service))
            .where(
                Booking.user_id == user_id,
                Booking.booking_date >= today,
                Booking.status.in_(["confirmed", "pending_payment", "pending_photo"])
            )
            .order_by(Booking.booking_date, Booking.start_time)
        )
        return list(result.scalars().all())

    async def get_user_archive(self, user_id: int) -> List[Booking]:
        result = await self.session.execute(
            select(Booking)
            .options(selectinload(Booking.service))
            .where(Booking.user_id == user_id)
            .order_by(Booking.booking_date.desc(), Booking.start_time.desc())
        )
        return list(result.scalars().all())

    async def get_booking_by_id(self, booking_id: int) -> Optional[Booking]:
        result = await self.session.execute(
            select(Booking)
            .options(selectinload(Booking.service), selectinload(Booking.user))
            .where(Booking.id == booking_id)
        )
        return result.scalar_one_or_none()

    async def cancel_booking(self, booking_id: int) -> bool:
        booking = await self.get_booking_by_id(booking_id)
        if not booking or booking.status not in ("confirmed", "pending_photo", "pending_payment"):
            return False
        if booking.calendar_event_id:
            try:
                from services.google_calendar import delete_event
                delete_event(booking.calendar_event_id)
            except Exception:
                pass
            booking.calendar_event_id = None
        booking.status = "cancelled"
        await self.session.commit()
        return True


    async def expire_unpaid_pending(self, minutes: int = 20) -> list:
        """Отменяет pending_payment без скрина/заметки старше N минут. Возвращает список отменённых."""
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        result = await self.session.execute(
            select(Booking)
            .options(selectinload(Booking.service), selectinload(Booking.user))
            .where(
                Booking.status == "pending_payment",
                Booking.updated_at < cutoff,
            )
        )
        expired = []
        for b in result.scalars().all():
            # если уже прислали скрин или «от кого» — не трогаем (ждёт админа)
            if b.payment_photo_file_id or (b.payment_note and str(b.payment_note).strip()):
                continue
            b.status = "cancelled"
            if b.calendar_event_id:
                try:
                    from services.google_calendar import delete_event
                    delete_event(b.calendar_event_id)
                except Exception:
                    pass
                b.calendar_event_id = None
            expired.append(b)
        if expired:
            await self.session.commit()
        return expired

    async def mark_completed(self, booking_id: int):
        booking = await self.get_booking_by_id(booking_id)
        if booking and booking.status == "confirmed":
            booking.status = "completed"
            booking.user.completed_count = (booking.user.completed_count or 0) + 1
            await self.session.commit()

    def hours_until(self, booking: Booking) -> float:
        dt = TZ.localize(datetime.combine(booking.booking_date, booking.start_time))
        return (dt - datetime.now(TZ)).total_seconds() / 3600

    async def get_upcoming_for_reminder(self, hours_before: int = 3) -> List[Booking]:
        now = datetime.now(TZ)
        result = await self.session.execute(
            select(Booking)
            .options(selectinload(Booking.user), selectinload(Booking.service))
            .where(Booking.status == "confirmed", Booking.reminder_sent == False)
        )
        out = []
        for b in result.scalars().all():
            booking_dt = TZ.localize(datetime.combine(b.booking_date, b.start_time))
            diff_h = (booking_dt - now).total_seconds() / 3600
            if hours_before - 0.3 <= diff_h <= hours_before + 0.3:
                out.append(b)
        return out

    async def get_for_day_confirm(self) -> List[Booking]:
        """Записи примерно через 24 часа, ещё без day_confirm."""
        now = datetime.now(TZ)
        result = await self.session.execute(
            select(Booking)
            .options(selectinload(Booking.user), selectinload(Booking.service))
            .where(
                Booking.status == "confirmed",
                Booking.day_confirm_sent == False
            )
        )
        out = []
        for b in result.scalars().all():
            booking_dt = TZ.localize(datetime.combine(b.booking_date, b.start_time))
            diff_h = (booking_dt - now).total_seconds() / 3600
            if 23 <= diff_h <= 25:
                out.append(b)
        return out

    async def mark_reminder_sent(self, booking_id: int):
        booking = await self.get_booking_by_id(booking_id)
        if booking:
            booking.reminder_sent = True
            await self.session.commit()

    async def mark_day_confirm_sent(self, booking_id: int):
        booking = await self.get_booking_by_id(booking_id)
        if booking:
            booking.day_confirm_sent = True
            await self.session.commit()
