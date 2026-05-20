from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from taurus_core.config import Settings, _redact_url_password


@dataclass(frozen=True, slots=True)
class BackupResult:
    backup_dir: Path
    database_kind: str
    artifact_path: Path
    manifest_path: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "backup_dir": str(self.backup_dir),
            "database_kind": self.database_kind,
            "artifact_path": str(self.artifact_path),
            "manifest_path": str(self.manifest_path),
        }


@dataclass(frozen=True, slots=True)
class RestoreResult:
    database_kind: str
    restored_from: Path
    restored_to: str
    pre_restore_backup: Path | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "database_kind": self.database_kind,
            "restored_from": str(self.restored_from),
            "restored_to": self.restored_to,
            "pre_restore_backup": str(self.pre_restore_backup) if self.pre_restore_backup else None,
        }


def create_backup(settings: Settings, *, output_root: Path | None = None) -> BackupResult:
    output_root = output_root or Path("backups")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = output_root / f"taurus-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    url = make_url(settings.database_url)
    database_kind = _database_kind(url.drivername)
    if database_kind == "sqlite":
        artifact_path = _backup_sqlite(url.database, backup_dir)
    elif database_kind == "postgresql":
        artifact_path = _backup_postgres(settings.database_url, backup_dir)
    else:
        raise ValueError(f"Unsupported database for backup: {url.drivername}")

    manifest_path = backup_dir / "manifest.json"
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_kind": database_kind,
        "database_url": _redact_url_password(settings.database_url),
        "artifact": artifact_path.name,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return BackupResult(
        backup_dir=backup_dir,
        database_kind=database_kind,
        artifact_path=artifact_path,
        manifest_path=manifest_path,
    )


def restore_backup(
    settings: Settings,
    *,
    backup: Path,
    confirm_postgres: bool = False,
) -> RestoreResult:
    backup = backup.expanduser()
    manifest = _load_manifest(backup)
    database_kind = str(manifest["database_kind"])
    artifact_path = backup / str(manifest["artifact"]) if backup.is_dir() else backup

    if database_kind == "sqlite":
        target = _sqlite_path(make_url(settings.database_url).database)
        target.parent.mkdir(parents=True, exist_ok=True)
        pre_restore_backup = None
        if target.exists():
            pre_restore_backup = target.with_suffix(
                f"{target.suffix}.pre-restore-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            )
            shutil.copy2(target, pre_restore_backup)
        shutil.copy2(artifact_path, target)
        return RestoreResult(
            database_kind=database_kind,
            restored_from=artifact_path,
            restored_to=str(target),
            pre_restore_backup=pre_restore_backup,
        )

    if database_kind == "postgresql":
        if not confirm_postgres:
            raise ValueError("Postgres restore requires RESTORE_CONFIRM=I_UNDERSTAND.")
        _restore_postgres(settings.database_url, artifact_path)
        return RestoreResult(
            database_kind=database_kind,
            restored_from=artifact_path,
            restored_to=_redact_url_password(settings.database_url),
        )

    raise ValueError(f"Unsupported backup database kind: {database_kind}")


def _backup_sqlite(database: str | None, backup_dir: Path) -> Path:
    source = _sqlite_path(database)
    if not source.exists():
        raise FileNotFoundError(f"SQLite database not found: {source}")
    artifact_path = backup_dir / "taurus.sqlite3"
    shutil.copy2(source, artifact_path)
    return artifact_path


def _backup_postgres(database_url: str, backup_dir: Path) -> Path:
    artifact_path = backup_dir / "taurus-postgres.dump"
    url = _pg_cli_url(database_url)
    subprocess.run(
        ["pg_dump", "--format=custom", "--file", str(artifact_path), url],
        check=True,
    )
    return artifact_path


def _restore_postgres(database_url: str, artifact_path: Path) -> None:
    subprocess.run(
        [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--dbname",
            _pg_cli_url(database_url),
            str(artifact_path),
        ],
        check=True,
    )


def _load_manifest(backup: Path) -> dict[str, object]:
    manifest_path = backup / "manifest.json" if backup.is_dir() else backup.parent / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Backup manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _database_kind(drivername: str) -> str:
    if drivername.startswith("sqlite"):
        return "sqlite"
    if drivername.startswith("postgresql"):
        return "postgresql"
    return drivername


def _sqlite_path(database: str | None) -> Path:
    if not database or database == ":memory:":
        raise ValueError("File-backed SQLite database is required for backup and restore.")
    return Path(database).expanduser()


def _pg_cli_url(database_url: str) -> str:
    url = make_url(database_url)
    if "+" in url.drivername:
        url = url.set(drivername=url.drivername.split("+", 1)[0])
    return url.render_as_string(hide_password=False)
