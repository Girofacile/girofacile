"""One backup location for CLI, container volume and administration UI."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SUFFIXES = {".dump", ".sql", ".zip"}


def backup_directory():
    path = Path(os.getenv("BACKUP_DIR", "backups"))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def backup_directories():
    # Existing legacy backups remain downloadable after an upgrade.
    return list(dict.fromkeys([backup_directory(), (PROJECT_ROOT / "data" / "backups").resolve()]))


def backup_files():
    found = {}
    for folder in backup_directories():
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in BACKUP_SUFFIXES:
                found.setdefault(path.name, path)
    return sorted(found.values(), key=lambda p: p.stat().st_mtime, reverse=True)


def resolve_backup(filename):
    if not filename or '/' in filename or '\\' in filename or Path(filename).name != filename:
        raise ValueError("Nome backup non valido")
    for path in backup_files():
        if path.name == filename:
            return path
    raise ValueError("Backup non trovato")
