from __future__ import annotations

import json
import os
from pathlib import Path

from taurus_core.config import Settings, get_settings
from taurus_core.logging import configure_logging
from taurus_core.ops.backup import create_backup


def backup_local(settings: Settings | None = None) -> dict[str, str]:
    settings = settings or get_settings()
    output_root = Path(os.environ.get("BACKUP_DIR", "backups"))
    return create_backup(settings, output_root=output_root).to_dict()


if __name__ == "__main__":
    configure_logging()
    print(json.dumps(backup_local(), sort_keys=True))
