from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    from database.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in settings.DATABASE_URL:
            def _migrate(sync_conn):
                def cols(table):
                    return [r[1] for r in sync_conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()]
                bc = cols("bookings")
                for col, sql in [
                    ("payment_photo_file_id", "ALTER TABLE bookings ADD COLUMN payment_photo_file_id VARCHAR(255)"),
                    ("calendar_event_id", "ALTER TABLE bookings ADD COLUMN calendar_event_id VARCHAR(255)"),
                    ("surcharge", "ALTER TABLE bookings ADD COLUMN surcharge FLOAT DEFAULT 0"),
                    ("payment_note", "ALTER TABLE bookings ADD COLUMN payment_note VARCHAR(255)"),
                    ("day_confirm_sent", "ALTER TABLE bookings ADD COLUMN day_confirm_sent BOOLEAN DEFAULT 0"),
                    ("day_confirm_status", "ALTER TABLE bookings ADD COLUMN day_confirm_status VARCHAR(20)"),
                    ("reschedule_count", "ALTER TABLE bookings ADD COLUMN reschedule_count INTEGER DEFAULT 0"),
                    ("last_reschedule_at", "ALTER TABLE bookings ADD COLUMN last_reschedule_at DATETIME"),
                    ("media_items", "ALTER TABLE content_blocks ADD COLUMN media_items JSON"),
                ]:
                    if col not in bc:
                        try:
                            sync_conn.exec_driver_sql(sql)
                        except Exception:
                            pass
                uc = cols("users")
                for col, sql in [
                    ("completed_count", "ALTER TABLE users ADD COLUMN completed_count INTEGER DEFAULT 0"),
                    ("is_blacklisted", "ALTER TABLE users ADD COLUMN is_blacklisted BOOLEAN DEFAULT 0"),
                ]:
                    if col not in uc:
                        try:
                            sync_conn.exec_driver_sql(sql)
                        except Exception:
                            pass
                sc = cols("services")
                if "calendar_color_id" not in sc:
                    try:
                        sync_conn.exec_driver_sql("ALTER TABLE services ADD COLUMN calendar_color_id VARCHAR(5) DEFAULT '1'")
                    except Exception:
                        pass
                cc = cols("content_blocks")
                for col, sql in [
                    ("media_file_id", "ALTER TABLE content_blocks ADD COLUMN media_file_id VARCHAR(255)"),
                    ("media_type", "ALTER TABLE content_blocks ADD COLUMN media_type VARCHAR(20)"),
                ]:
                    if col not in cc:
                        try:
                            sync_conn.exec_driver_sql(sql)
                        except Exception:
                            pass
            await conn.run_sync(_migrate)
