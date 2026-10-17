# 原生 DSH 迁移与跨平台源码候选

## 状态

- 2026-10-16 接收核心来源 `bc74a98ac90d72f0292819605baa132a52621f83`，同步旧实现删除项。
- 2026-10-17 按后续授权重构安装、配置、一键启动、可选模块及部署参数。
- GitHub 同一仓库已改名为 **Agent-for-qqbot**，根 remote/产品链接已更新；没有新建替代仓库。
  LAN 源码 remote 不随 GitHub 改名改变。
- 现已按用户最新授权升为 **`1.0.0`**；旧 Hermes / 0.x 停更，历史 tag 不动。仍未 commit/push/tag/Release。
- 最新授权已覆盖此前“仅静态检查”的限制，现对源码外的新私有实例进行 Windows / WSL 安装、构建和本地模型验证。
  既有 DSH 配置、凭据及默认模型不改；真实 NapCat→QQ、Qzone/飞书发送不在本轮测试范围。
- 不重建已删除的旧测试 home，不把历史 Linux 成功记录当作新链路验收。

当前通过项和仍未验收项见 [VALIDATION.md](VALIDATION.md)。

## 本次移植

| 范围 | 源码实现 |
|---|---|
| 安装 / 更新 | 独立私有 venv、完整固定 fork 编译、上游锁文件/补丁、native portable closure；新快照成功后切换 |
| 配置 | 统一私有 JSON、双脑复用、命名供应商方案、本地免 Key、模型目录读取、人格导入/预设及 revision 冲突检测 |
| 启停 | 默认独立 Web；QQ 显式启用后顺序就绪；PID/创建时间进程树管理，Windows Job Object |
| 平台边界 | POSIX 权限/所有权与 Windows DACL；文件锁、目录同步、信号、UDS/鉴权回环适配 |
| 记忆与知识 | 原生场景/来源/回执记忆保留；Markdown vault 有界只读检索，不恢复旧引擎 |
| 可选桌面 | 独立 Live2D 依赖安装、私有状态、可配置端口/模型目录/下载源、控制鉴权、owner 动作接线 |
| 语音输入 | 显式转写模型/协议入口，未配置关闭；不宣称旧 TTS 自动发语音已迁入 |
| 计划 / Qzone / 简报 | 配置任务清单而非生产 job ID/时间；独立 effect fence、真实 receipt、无补发 |
| 工程执行 | Linux bubblewrap 或跨平台 Docker digest；缺后端拒绝，不直接跑候选 |
| 原生设置应用 | 独立 supervisor 静默检查、竞态重查、Web→Gateway 重载、回执与失败恢复 |
| 分发 | 插件 manifests、vendor 来源/hash、白名单源码 staging、Inno/NSIS 不打包运行目录 |

源码目录 `hermes/` 与 `soyo` 内部协议/namespace 暂保留，避免改坏已有记录契约；
实际 persona、模型和部署绑定来自私有配置，不因兼容名称固定为某个角色、GPT 型号或 root 账户。
公开产品及默认名称统一为 Bot；所有公开人格 / 云端 / 本地配置示例位于 `templates/`，
`hermes/templates/` 仅保留旧路径指引。界面和运行提示不预设人物，内部 `soyo_*` 工具 / 数据标识及第三方版权不改名。

## 硬编码分类

- 账号、路径、Token、供应源、模型/协议/预算、端口、owner 会话、工具位置、任务 ID/cron、
  字体、知识源、可选模块绑定均由实例配置/环境提供，默认不从旧部署采集。
- 产品默认端口、registry、项目链接与固定依赖来源集中在 `application.toml`，实例值可覆盖。
- 安全上限、回环限制、QQ/Qzone 协议域名、持久化字段、GPL 归属、依赖版本/SHA 及
  CVPKG 加密格式常量保留；它们不是应替换为任意输入的生产绑定。
- 旧 root/systemd 安装/设置脚本及旧 Hermes 配置/升级入口已由统一实现替换，兼容文件明确拒绝旧操作。

## 外部依赖与发布门禁

参考宿主是 `eamars/deepseek-harness` 的 `asuna/0.2.1-rc.2`，固定提交
`5713aab7963851d1a87482058c33c4af0e1c2ff8`。安装器必须构建整套 fork，而非只替换 UI。
上游 SDK closure 的 manifest-only 根依赖覆盖及前后 lock hash 会写入私有安装回执。
原生依赖与完整 fork 现已进入本机真实构建验证；部署根覆盖只修改 workspace importer，保留冻结的 registry 解析。
业务源码更新可复用同版本/平台/工具链的私有原生构建，为新业务快照重新复制插件，不混装其他宿主。

Windows / WSL 完整安装、真实双脑读取、Web / RPC / mux 与实际重启恢复已通过，详见验收记录。
以下仍是发布前条件，不能以“源码已改”或短回合验证替代：

- 真实 QQ 接入/单 writer、并发与负载、完整原生设置应用竞态和异常回滚验收；
- Docker/bubblewrap 隔离、Windows ACL/锁/Job Object、NTFS 原子替换与断电恢复实测；
- 生成资产可重现核对、完整依赖锁与源码/二进制对应关系；
- 组合 MIT/GPL 与素材/依赖分发权利、对应源码和完整 Git 历史隐私审查。

`extras/scripts/package_source.py` 仅产生显式确认的**源码候选 staging**，不表示上述门禁通过，
也不生成离线依赖包、不发布。GitHub 名称改变不意味着迁移代码已上传。

## 数据保护

本轮没有改写用户**原有**运行 home、配置、数据库及 sidecar、sessions、日志、媒体、
NapCat 登录状态或生产服务。源码覆盖前恢复包、原始导出、内部运维资料与改名回执留在公开工作区之外。
新运行时只面向独立实例；历史库只有用户显式配置的只读来源，不自动 schema/data migration。
