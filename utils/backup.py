"""Database backup utilities — copy SQLite file with timestamp."""
import os
import shutil
from datetime import datetime
from config import DB_PATH, DATA_DIR

BACKUP_DIR = os.path.join(DATA_DIR, "backups")


def _ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def create_backup(label: str = "") -> str:
    """Create a timestamped backup of the database file.
    Returns the path to the backup file.
    """
    _ensure_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    backup_name = f"migasapp_{timestamp}{suffix}.db"
    dest = os.path.join(BACKUP_DIR, backup_name)
    shutil.copy2(DB_PATH, dest)
    _cleanup_old_backups()
    return dest


def _cleanup_old_backups(keep: int = 10):
    """Keep only the most recent `keep` backups."""
    _ensure_backup_dir()
    files = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".db")],
        reverse=True,
    )
    for old in files[keep:]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old))
        except OSError:
            pass


def list_backups() -> list[dict]:
    """Return list of backups with name and size."""
    _ensure_backup_dir()
    result = []
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if f.endswith(".db"):
            path = os.path.join(BACKUP_DIR, f)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            result.append({"name": f, "path": path, "size_mb": round(size_mb, 2)})
    return result


def restore_backup(backup_path: str):
    """Replace current DB with a backup file."""
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup not found: {backup_path}")
    # Safety: backup current before restoring
    create_backup(label="pre_restore")
    shutil.copy2(backup_path, DB_PATH)
