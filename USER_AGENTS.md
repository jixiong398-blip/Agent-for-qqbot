# Agent-for-qqbot：用户 AI 操作指南

先读 [README.md](README.md)、[MIGRATION.md](MIGRATION.md) 与
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。当前是未发布的 **1.0.0** 原生 DSH 主线；旧 Hermes / 0.x 停更。

## 入口与数据边界

- 唯一统一入口：`extras/scripts/bootstrap.py` → `soyo.app`；根 bat/sh 是薄封装。
- 默认实例目录为用户主目录下 `.agent-for-qqbot`，可用 `AGENT_QQBOT_HOME` 指定源码目录之外的新目录。
- 不指向已有 Hermes home，不从其他部署猜账号、端口、供应商、模型、Key 或 persona。
- 普通用户使用预构建包：`install` 不装依赖、不编译，直接打开原生 DSH；模型、人格、NapCat 均在 DSH 内配置。
  只有维护者使用源码构建固定 fork。不要把编译 / 打包成功称为 QQ 或发布验收。
- 配置用私有 `deployment.json` 与 `persona/`，示例在 `templates/`；不要提交真实内容。
  模型可分脑配置或复用，支持私有命名供应商方案与人格预设；本地免 Key 必须显式选择且仅限回环。
- 产品默认称呼 Bot，名字与人格由使用者自取；不把内部 `soyo` 包 / 工具 ID 解释为默认人物。
  全部公开模板看 `templates/README.md`；旧 `hermes/templates/` 只保留指引，不自动导入。
- 用户产品只绑定本机回环，不依赖远程组网软件；维护者的远程管理不属于安装步骤。
  原生入口无额外 Bot Key 页，保留实际 TCP peer、Host / Origin / CSRF 及内部凭据隔离。
- 默认先只用 Web。仅在用户明确开启 QQ 后接入 NapCat；必须由用户扫码，OneBot listener 必须有 Token 且只绑定回环。

## 可以根据用户授权操作

`install`、`configure [--web]`、`start [--no-browser] [--no-autostart]`、`status`、`stop`、
`update`、`rollback`、`recover-runtime`、`install-live2d`、`doctor`。
Windows 通过相应 bat 或 bootstrap.ps1，Linux 通过 sh wrapper / Python 3.12+。
更新前停止实例；配置命令不会自动执行服务/模型探测。`doctor` 不是测试套件。

## 不要做

- 不恢复 Hermes/OneBot 旧实现作为 fallback，不启动第二个 QQ writer。
- 不运行已退休的 Linux root 安装器或旧 `UPGRADE_MAP` 双写流程。
- 不按端口或进程名杀 QQ；仅管理本实例明确捕获的进程身份。
- 不把内部 `host.root` 能力名解释为自动系统 root；默认是 workspace-write。
- 不在没有隔离后端时直接运行行动脑候选代码；Docker 必须使用显式镜像 digest。
- 不把旧记录、回合结束、建议、操作已接受或配置已保存当成平台效果/验收完成。
- 不把 venv、node_modules、NapCat 账号配置、数据库、日志、knowledge vault 或私有 home 打进源码包。

## 当前验收状态

新授权已覆盖此前仅静态检查的约束；Windows / WSL 独立实例安装、原生 Web、双脑本地模型回合和重启恢复已验证。
真实 QQ、外部发送和用户原有部署不在此次验证范围。具体通过项和未验证项以 MIGRATION 为准。
GitHub 仓库已改名为 Agent-for-qqbot；当前仅 README 获得文档更新授权，整套源码没有提交、推送、打 tag、Release 或部署授权。
