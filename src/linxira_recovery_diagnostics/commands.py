from __future__ import annotations

import subprocess
from dataclasses import dataclass


FINDMNT_ROOT = (
    "/usr/bin/findmnt", "--json", "--bytes", "--output",
    "TARGET,SOURCE,FSTYPE,OPTIONS,FSROOTS,AVAIL,USED,SIZE", "/",
)
FINDMNT_MNT = FINDMNT_ROOT[:-1] + ("/mnt",)
LSBLK = (
    "/usr/bin/lsblk", "--json", "--bytes", "--output",
    "NAME,PATH,TYPE,FSTYPE,FSVER,LABEL,UUID,MOUNTPOINTS,SIZE,FSAVAIL,FSUSE%,MODEL,SERIAL",
)
TIMESHIFT_LIST = ("/usr/bin/timeshift", "--list", "--scripted")
GRUB_BTRFS_ENABLED = ("/usr/bin/systemctl", "is-enabled", "grub-btrfsd.service")
GRUB_BTRFS_ACTIVE = ("/usr/bin/systemctl", "is-active", "grub-btrfsd.service")

ALLOWED_COMMANDS = frozenset(
    {FINDMNT_ROOT, FINDMNT_MNT, LSBLK, TIMESHIFT_LIST, GRUB_BTRFS_ENABLED, GRUB_BTRFS_ACTIVE}
)


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    warning: str | None = None


class FixedCommandRunner:
    def run(self, argv: tuple[str, ...], timeout: float = 5.0) -> CommandResult:
        if argv not in ALLOWED_COMMANDS:
            raise ValueError("command is not in the fixed evidence allowlist")
        try:
            completed = subprocess.run(
                list(argv),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
                stdin=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            )
        except FileNotFoundError:
            return CommandResult(argv, None, warning="executable-not-found")
        except subprocess.TimeoutExpired:
            return CommandResult(argv, None, warning="timeout")
        return CommandResult(
            argv,
            completed.returncode,
            completed.stdout[:1_000_000],
            completed.stderr[:4096],
            None if completed.returncode == 0 else "command-failed",
        )
