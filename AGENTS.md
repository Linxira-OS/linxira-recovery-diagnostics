# linxira-recovery-diagnostics · Agent 开发规范

> **档位**:A · 系统源仓
> **本仓职责**:面向已安装 Linxira 系统与 Linxira/Arch live 环境的只读证据采集与修复规划;
> 可生成经隐私过滤的支持包。
> 通用约束见工作区总纲 `f:\Linxira-OS\AGENTS.md` 与发布规范 `linxira-os/docs/RELEASE_STANDARD.md`;
> 本文只写本仓特有内容。

## 职责与边界

- Pacman 锁诊断与 live-chroot 就绪检查可通过 root 所属的 Linxira 系统事务服务确认并执行;
  **所有修复操作保持禁用**。
- 证据路径**编译进应用本体**;仅将 `/` 与 `/mnt` 作为系统根检查。
- 外部进程使用精确 argv 允许列表:`findmnt`、`lsblk`、Timeshift 列表,以及只读的
  `systemctl is-enabled` / `is-active` 查询;**没有 shell 执行**、mount/chroot、包变更、服务变更、
  任意路径选项或快照标识符输入。
- 仅两个固定的只读诊断使用系统 D-Bus 服务;快照、回滚、密钥环修复、chroot 修复计划一律报告
  `apply-backend-not-ready`。
- Pacman 锁处理**仅为诊断,锁永不被删除**。
- 支持包:显示清单、递归脱敏,不含 journal / dmesg / 原始进程命令行 / 上传行为,且**不接受输出路径参数**;
  计划与支持包以生成文件名写入 `$XDG_STATE_HOME/linxira-recovery-diagnostics`(或 `~/.local/state/...`)。

## 目录布局

- `src/linxira_recovery_diagnostics/`:`__init__.py`、`cli.py`、`gui.py`、`plans.py`、`collector.py`、
  `system.py`、`backend.py`、`commands.py`、`support.py`、`about.py`
- `tests/`:`test_collector.py`、`test_plans.py`、`test_gui.py`、`test_backend.py`、`test_support.py`、
  `test_security.py`、`test_workspace_guard.py`、`test_about_metadata.py`、`conftest.py`
- `data/`:`org.linxira.RecoveryDiagnostics.desktop`、`.metainfo.xml`、`.svg`

## 本地校验

CI(矩阵 python 3.11/3.12/3.13,`QT_QPA_PLATFORM=offscreen`,需 `libegl1`)执行:

```sh
python -m pip install ".[test]"
pytest
python -m compileall -q src
python -m build
python -c "import xml.etree.ElementTree as E; E.parse('data/org.linxira.RecoveryDiagnostics.metainfo.xml')"
```

CLI 自检:

```sh
linxira-recovery-diagnostics            # GUI
linxira-recovery-diagnostics --report-json
linxira-recovery-diagnostics --plan org.linxira.recovery.keyring-repair.v1
linxira-recovery-diagnostics --support-bundle
```

## 版本与发布

- 版本唯一来源是本仓根 `VERSION`(当前 `0.3.0`);`pyproject.toml` 的 `version` 必须同步。
- 改 `VERSION` 触发 `.github/workflows/release.yml`(分支 `main`)自动建 Release,进入 `[linxira]` 全自动链。**禁止手工 bump**。

## 禁区

- 保持只读边界:不得新增 shell 执行、mount/chroot、包/服务变更、任意路径或快照 ID 输入;
  不得删除 pacman 锁;不得让计划 apply 绕过 `apply-backend-not-ready`。
- 支持包不得包含 journal / dmesg / 原始命令行,不得新增上传行为或接受输出路径参数。
- 不引入 `cachyos` / `aur` / `seafoam`;不直接 `sudo`/`su`/`doas`/`run0`。
- 不 `git add -A`(勿带入 `dist/`、`.pytest_cache/` 等产物)。