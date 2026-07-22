# Linxira Recovery Diagnostics

Linxira Recovery Diagnostics is a read-only evidence and repair-planning application for installed Linxira systems and Linxira/Arch live environments. Pacman-lock diagnosis and live-chroot readiness can be confirmed and executed through the root-owned Linxira system transaction service; all repair operations remain disabled.

## Safety boundary

- Evidence paths are compiled into the application. Only `/` and `/mnt` are inspected as system roots.
- External processes use exact argv allowlists for `findmnt`, `lsblk`, Timeshift listing, and read-only `systemctl is-enabled`/`is-active` queries.
- There is no shell execution, mount/chroot operation, package mutation, service mutation, arbitrary path option, or snapshot identifier input.
- Only two fixed read-only diagnostics use the system D-Bus service. Snapshot, rollback, keyring repair, and chroot repair plans report `apply-backend-not-ready`.
- Pacman lock handling is diagnosis only. The lock is never deleted.

## Usage

Run the GUI:

```bash
linxira-recovery-diagnostics
```

Print the stable schema-v1 report or create one fixed plan:

```bash
linxira-recovery-diagnostics --report-json
linxira-recovery-diagnostics --plan org.linxira.recovery.keyring-repair.v1
```

Create a privacy-filtered support bundle:

```bash
linxira-recovery-diagnostics --support-bundle
```

Plans and bundles are written with generated names below `$XDG_STATE_HOME/linxira-recovery-diagnostics`, or `~/.local/state/linxira-recovery-diagnostics`. Bundle creation shows a manifest, performs recursive redaction, includes no journal, dmesg, raw process command line, or upload behavior, and does not accept an output path.

## Development

Python 3.11 or newer is required.

```bash
python -m pip install -e ".[test]"
pytest
python -m compileall -q src
python -m build
```
