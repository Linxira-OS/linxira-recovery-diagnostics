from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


class SystemReader:
    """Read-only access used by the collector; production paths are constants."""

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def stat(self, path: str) -> os.stat_result:
        return Path(path).stat()

    def read_text(self, path: str, limit: int = 1_000_000) -> str:
        with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)

    def entries(self, path: str) -> Iterable[str]:
        try:
            return tuple(item.name for item in Path(path).iterdir())
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            return ()


def package_version(reader: SystemReader, package: str, root: str = "") -> str | None:
    base = f"{root}/var/lib/pacman/local" if root else "/var/lib/pacman/local"
    prefix = package + "-"
    candidates = sorted(name for name in reader.entries(base) if name.startswith(prefix))
    for directory in reversed(candidates):
        desc_path = f"{base}/{directory}/desc"
        try:
            fields = reader.read_text(desc_path, 128_000).splitlines()
        except (OSError, ValueError):
            continue
        for index, line in enumerate(fields[:-1]):
            if line == "%VERSION%":
                return fields[index + 1]
    return None
