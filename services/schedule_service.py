from datetime import date, time, datetime, timedelta
from typing import List, Set, Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import ScheduleDay, Booking
from config import TZ
from utils.time_utils import parse_time


def all_possible_slots() -> List[str]:
    slots = []
    mins = 7 * 60
    while mins <= 22 * 60:
        h, m = divmod(mins, 60)
        slots.append(f"{h:02d}:{m:02d}")
        mins += 30
    return slots


def normalize_slots(raw: list) -> List[Dict[str, Any]]:
    """Приводит слоты к формату [{time, surcharge, label}]"""
    result = []
    if not raw:
        return result
    for item in raw:
        if isinstance(item, str):
            result.append({"time": item, "surcharge": 0, "label": ""})
        elif isinstance(item, dict) and "time" in item:
            result.append({
                "time": item["time"],
                "surcharge": float(item.get("surcharge") or 0),
                "label": item.get("label") or "",
            })
    result.sort(key=lambda x: x["time"])
    return result


def slot_times(raw: list) -> List[str]:
    return [s["time"] for s in normalize_slots(raw)]


class ScheduleService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_open_days(self, year: int, month: int) -> Set[date]:
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        result = await self.session.execute(
            select(ScheduleDay).where(
                ScheduleDay.day >= start,
                ScheduleDay.day < end,
                ScheduleDay.is_open == True
            )
        )
        days = result.scalars().all()
        return {d.day for d in days if slot_times(d.available_slots or [])}

    async def get_days_surcharge_map(self, year: int, month: int) -> Dict[date, float]:
        """Макс. доплата по дню (для метки в календаре)."""
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        result = await self.session.execute(
            select(ScheduleDay).where(
                ScheduleDay.day >= start,
                ScheduleDay.day < end,
                ScheduleDay.is_open == True
            )
        )
        out = {}
        for d in result.scalars().all():
            slots = normalize_slots(d.available_slots or [])
            if slots:
                out[d.day] = max(s["surcharge"] for s in slots)
        return out

    async def is_day_open(self, day: date) -> bool:
        result = await self.session.execute(select(ScheduleDay).where(ScheduleDay.day == day))
        record = result.scalar_one_or_none()
        if record is None:
            return False
        return record.is_open and bool(slot_times(record.available_slots or []))

    async def get_day_record(self, day: date) -> Optional[ScheduleDay]:
        result = await self.session.execute(select(ScheduleDay).where(ScheduleDay.day == day))
        return result.scalar_one_or_none()

    async def set_day_open(self, day: date, is_open: bool):
        record = await self.get_day_record(day)
        if record:
            record.is_open = is_open
            if not is_open:
                record.available_slots = []
        else:
            record = ScheduleDay(day=day, is_open=is_open, available_slots=[])
            self.session.add(record)
        await self.session.commit()

    async def set_day_slots(self, day: date, slots: List[Dict[str, Any]]):
        normalized = normalize_slots(slots)
        record = await self.get_day_record(day)
        if record:
            record.available_slots = normalized
            record.is_open = bool(normalized)
        else:
            record = ScheduleDay(day=day, is_open=bool(normalized), available_slots=normalized)
            self.session.add(record)
        await self.session.commit()

    async def toggle_slot(self, day: date, slot: str) -> List[Dict[str, Any]]:
        record = await self.get_day_record(day)
        current = normalize_slots(record.available_slots if record else [])
        times = [s["time"] for s in current]
        if slot in times:
            current = [s for s in current if s["time"] != slot]
        else:
            current.append({"time": slot, "surcharge": 0, "label": ""})
            current.sort(key=lambda x: x["time"])
        if record:
            record.available_slots = current
            record.is_open = bool(current)
        else:
            record = ScheduleDay(day=day, is_open=bool(current), available_slots=current)
            self.session.add(record)
        await self.session.commit()
        return current

    async def set_slot_surcharge(self, day: date, slot: str, surcharge: float, label: str = ""):
        record = await self.get_day_record(day)
        current = normalize_slots(record.available_slots if record else [])
        found = False
        for s in current:
            if s["time"] == slot:
                s["surcharge"] = surcharge
                s["label"] = label
                found = True
                break
        if not found:
            current.append({"time": slot, "surcharge": surcharge, "label": label})
            current.sort(key=lambda x: x["time"])
        if record:
            record.available_slots = current
            record.is_open = True
        else:
            record = ScheduleDay(day=day, is_open=True, available_slots=current)
            self.session.add(record)
        await self.session.commit()
        return current

    async def get_slot_info(self, day: date, slot_str: str) -> Dict[str, Any]:
        record = await self.get_day_record(day)
        for s in normalize_slots(record.available_slots if record else []):
            if s["time"] == slot_str:
                return s
        return {"time": slot_str, "surcharge": 0, "label": ""}

    async def get_available_slots(self, day: date, duration_minutes: int) -> List[Dict[str, Any]]:
        """Свободные слоты с доплатой."""
        if not await self.is_day_open(day):
            return []
        record = await self.get_day_record(day)
        if not record:
            return []
        slots = normalize_slots(record.available_slots or [])

        result = await self.session.execute(
            select(Booking).where(
                Booking.booking_date == day,
                Booking.status.in_(["confirmed", "pending_photo", "pending_payment"])
            )
        )
        occupied = [(b.start_time, b.end_time) for b in result.scalars().all()]
        free = []
        now = datetime.now(TZ)

        for s in slots:
            try:
                slot_start = parse_time(s["time"])
            except ValueError:
                continue
            slot_end = (datetime.combine(day, slot_start) + timedelta(minutes=duration_minutes)).time()
            conflict = any(not (slot_end <= o[0] or slot_start >= o[1]) for o in occupied)
            if conflict:
                continue
            slot_dt = TZ.localize(datetime.combine(day, slot_start))
            if slot_dt > now + timedelta(hours=1):
                free.append(s)
        return free
