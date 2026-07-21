from __future__ import annotations

import subprocess

import pytest

from linxira_recovery_diagnostics.cli import parser
from linxira_recovery_diagnostics.commands import ALLOWED_COMMANDS, FINDMNT_ROOT, FixedCommandRunner


def test_runner_uses_shell_false(monkeypatch):
    captured = {}
    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "{}", "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    FixedCommandRunner().run(FINDMNT_ROOT)
    assert captured["shell"] is False
    assert captured["stdin"] == subprocess.DEVNULL


def test_runner_rejects_non_allowlisted_command():
    with pytest.raises(ValueError):
        FixedCommandRunner().run(("/bin/sh", "-c", "id"))


@pytest.mark.parametrize("args", [
    ["--output", "/tmp/report"], ["--path", "/etc/shadow"],
    ["--snapshot", "123"], ["--plan", "/tmp/plan"], ["/tmp/input"],
])
def test_cli_rejects_arbitrary_paths_and_snapshot_ids(args):
    with pytest.raises(SystemExit):
        parser().parse_args(args)


def test_no_mutating_command_tokens():
    forbidden = {"sudo", "pkexec", "mount", "umount", "chroot", "-S", "-Syu", "enable", "start", "stop", "restart", "delete", "remove"}
    tokens = {token for argv in ALLOWED_COMMANDS for token in argv}
    assert tokens.isdisjoint(forbidden)
