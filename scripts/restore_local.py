from __future__ import annotations

import json
import os
from pathlib import Path

from taurus_core.config import Settings, get_settings
from taurus_core.logging import configure_logging
from taurus_core.ops.backup import restore_backup


def restore_local(settings: Settings | None = None) -> dict[str, str | None]:
    settings = settings or get_settings()
    backup = os.environ.get("BACKUP")
    if not backup:
        raise ValueError("BACKUP=/path/to/backup is required.")
    confirm_postgres = os.environ.get("RESTORE_CONFIRM") == "I_UNDERSTAND"
    return restore_backup(
        settings,
        backup=Path(backup),
        confirm_postgres=confirm_postgres,
    ).to_dict()


if __name__ == "__main__":
    configure_logging()
    print(json.dumps(restore_local(), sort_keys=True))
