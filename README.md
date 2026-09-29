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

---

## 简体中文

Linxira Recovery Diagnostics 是面向已安装 Linxira 系统与 Linxira/Arch live 环境的只读证据采集与修复规划应用。Pacman 锁诊断与 live-chroot 就绪检查可通过 root 所属的 Linxira 系统事务服务确认并执行；所有修复操作保持禁用。

## 安全边界

- 证据路径编译进应用本体。仅将 `/` 与 `/mnt` 作为系统根进行检查。
- 外部进程对 `findmnt`、`lsblk`、Timeshift 列表以及只读的 `systemctl is-enabled`/`is-active` 查询使用精确的 argv 允许列表。
- 没有 shell 执行、mount/chroot 操作、软件包变更、服务变更、任意路径选项或快照标识符输入。
- 仅两个固定的只读诊断使用系统 D-Bus 服务。快照、回滚、密钥环修复与 chroot 修复计划报告 `apply-backend-not-ready`。
- Pacman 锁处理仅为诊断。锁永远不会被删除。

## 用法

启动图形界面：

```bash
linxira-recovery-diagnostics
```

输出稳定的 schema-v1 报告或创建一个固定计划：

```bash
linxira-recovery-diagnostics --report-json
linxira-recovery-diagnostics --plan org.linxira.recovery.keyring-repair.v1
```

创建经隐私过滤的支持包：

```bash
linxira-recovery-diagnostics --support-bundle
```

计划与支持包以生成的文件名写入 `$XDG_STATE_HOME/linxira-recovery-diagnostics`（或 `~/.local/state/linxira-recovery-diagnostics`）之下。支持包创建会显示清单、执行递归脱敏，不包含 journal、dmesg、原始进程命令行或上传行为，且不接受输出路径参数。

## 开发

需要 Python 3.11 或更新版本。

```bash
python -m pip install -e ".[test]"
pytest
python -m compileall -q src
python -m build
```
