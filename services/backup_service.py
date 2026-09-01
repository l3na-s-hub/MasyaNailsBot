"""Резервное копирование и восстановление базы данных"""
import shutil
from datetime import datetime
from pathlib import Path
from config import DATA_DIR, BASE_DIR

BACKUP_DIR = DATA_DIR / "backups"
DB_FILE = DATA_DIR / "bot.db"


def ensure_backup_dir():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def create_backup() -> Path | None:
    """Создаёт копию bot.db с меткой времени. Возвращает путь к бэкапу."""
    ensure_backup_dir()
    if not DB_FILE.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"bot_{stamp}.db"
    shutil.copy2(DB_FILE, dest)
    # Оставляем только последние 20 бэкапов
    backups = sorted(BACKUP_DIR.glob("bot_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[20:]:
        old.unlink(missing_ok=True)
    return dest


def list_backups() -> list[Path]:
    ensure_backup_dir()
    return sorted(BACKUP_DIR.glob("bot_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)


def restore_backup(backup_path: Path) -> bool:
    """Восстанавливает базу из бэкапа."""
    if not backup_path.exists():
        return False
    # Сначала бэкап текущей
    if DB_FILE.exists():
        create_backup()
    shutil.copy2(backup_path, DB_FILE)
    return True
