# Agent-for-qqbot 1.0

原生 DSH + NapCat 的 QQ Agent：角色/行动协作、场景记忆、便签、原生 Web 与真实发送回执。

> **1.0.0 是原生 DSH 架构迁移主线，尚未发布。** 旧 Hermes / 0.x 系列停止维护，历史 tag 不改写。
> Windows / WSL 已通过独立实例安装、原生 Web 和双脑本地模型短回合验收；真实 NapCat→QQ 接入本轮跳过。
> 不把旧版的验证记录当作 1.0 通过证明，也不将源码候选称为完整离线安装包。

> **当前 GitHub 仅更新首页说明，1.0 源码尚未上传。** 公开代码的 `VERSION` 仍为旧版 `0.14.16`，该系列已停更。
> 下文是 1.0 源码候选的入口与部署说明，**不能拿旧下载包按此安装 1.0**；尚无 1.0 tag、Release 或成品安装包。

仓库：<https://github.com/jixiong398-blip/Agent-for-qqbot>。

**公开产品统称 Bot，不内置固定人物。** 角色名、别名、性格与背景由使用者自行填写；
全部公开配置 / 人格示例集中在 `templates/`，旧模板路径只保留指引。模型、账号和凭据不从作者环境继承。

## 新入口

| 操作 | Windows | Linux / WSL |
|---|---|---|
| 安装原生依赖 | `install.bat` | `sh install.sh` |
| 配置模型 / QQ / 人格 | `配置API.bat`（本机 Web 向导） | `sh configure.sh`（命令行） |
| 一键启动控制台、原生 Web（QQ 按配置开启） | `start.bat` | `sh start.sh` |
| 停止本实例进程 | `Stop-All.bat` | `sh stop.sh` |
| 安装当前源码的新运行时 | `update.bat` | `python3 extras/scripts/bootstrap.py update` |

这些入口现在都调用 `extras/scripts/bootstrap.py` → `soyo.app`；不启动旧 Hermes。
安装/升级只构建并选择运行时，不自动启动 QQ，不覆盖另一个运行目录。

## 前置条件

- Python **3.12+**、Git、Node.js/npm；Node 要求 **22.19+ 的 22.x 或 24+**，以 `application.toml` 为准。
- 固定 DSH fork 需要构建原生模块及 Web。Linux / WSL 需要 C/C++ 工具链（如 `build-essential`）及 Node 开发头文件；
  官方 Node 完整发行包含头文件。Windows 优先使用依赖提供的预编译模块，缺少匹配版本时须准备其构建工具。
- 完整源码构建建议至少 **8 GiB RAM + swap/pagefile 容量**；低于 6 GiB 会提前拒绝，避免编译器使小内存 WSL 退出。
  这不包含本地大模型所需的显存/内存；模型与构建可分别进行。安装器不会擅改 WSL 配额或系统 swap。
- 首装需要网络访问 Python/npm registry 与固定上游源码；**不再假称旧离线压缩包足够**。
  已有旧版 portable Node 不满足最低版本时必须换用兼容版本。
- **先体验 Web 不需要 NapCat 或 QQ。** 接入 QQ 时再独立安装 NapCat 并由用户扫码登录；登录信息不随源码打包。
- Live2D 可选，需要 Electron 与桌面图形环境；无桌面的 Linux 不启动此模块。

可用 `AGENT_QQBOT_PYTHON`（POSIX wrapper）、`AGENT_QQBOT_NODE`、`AGENT_QQBOT_NPM`
或私有 `executables` 指定工具位置。Windows wrapper 自动发现 Python；Node 优先使用系统 PATH。

## 配置与数据

默认实例目录是用户主目录下的 `.agent-for-qqbot`；可通过 **`AGENT_QQBOT_HOME`** 覆盖。
必须是源码目录以外、非链接的新私有目录，不能指向已有 Hermes home。

1. 安装后打开向导；默认本机直接进入，控制台与聊天**不再显示 Key 登录页**。
   模型 API Key / OneBot Token 是独立配置，不受 UI 免 Key 影响。
2. 填写角色模型的 API 地址、ID、协议、上下文上限与输出预算；行动脑可一键复用同一模型，也可独立配置。
   云端用 API Key；免鉴权本地服务明确选择“本地免 Key”（仅允许回环）。不扫描其他部署的凭据。
   保存后可读取供应商的模型列表；保存命名方案后可快捷切换自定义供应商，密钥不会回显。
3. 填好角色名，导入 Markdown 或编辑人格正文。支持命名人格预设、快捷应用与旧文件备份。
   模板见源码候选的 `templates/README.md`。切换不删除历史；不同角色完全隔离时请使用不同实例目录。
4. **先保持 QQ 接入关闭，启动原生 Web。** 选择“角色名 · Owner”主会话体验双脑协作。
   普通新建 DSH 会话不会自动获得部署 owner 的双脑授权。
5. 需要 QQ 时，停止原生服务，在 NapCat WebUI 开启**带 Token、只绑定回环**的 HTTP/WS listener。
   填写账号配置目录后选择已登录账号，或手动填写对应 endpoint/Token 和 owner QQ。
   显式开启 QQ 接入并保存，再启动。启动器核对实际登录账号并等待通道新鲜就绪；失败不显示连接成功。

私有目录包含 `deployment.json`、`private/`、`persona/`、`profiles/`、`runtimes/`、
`memory/`、`logs/` 等。**不要上传整个实例目录或递归打包运行目录。**
Windows 用 DACL，POSIX 用所有权和私有权限；缺少权限支持时拒绝读取凭据，不跳过校验。

## 可选能力

- **知识库**：配置已有 Markdown/Obsidian vault。提供有界只读检索/读取，默认只有 owner 可读。
- **Live2D**：停止控制台后执行 `python extras/scripts/bootstrap.py install-live2d`
  （Linux 使用 `python3`），再在控制台启动。模型目录、下载源和端口可配置；
  角色选取不写死。开启 Live2D owner 授权后，行动脑可列模型、切换、表情、动作、视线及尺寸。
  现有模型不会被安装覆盖，素材权利仍由使用者核实。
- **语音识别**：私有 `speech` 可配置 OpenAI 兼容转写 endpoint/model/Key；默认关闭。
  不恢复旧 TTS/自动语音发送链路。
- **自动化**：`automation_jobs` 默认空。每个任务显式设置 `id/kind/cron`；没有生产任务 ID 或默认发帖时间。
  支持记忆维护、知识增量、Qzone、简报及控制告警；不追补错过的外部效果。
- **隔离开发**：默认禁用可执行候选。Windows/Linux 可配置 Docker（镜像必须固定 digest）；
  Linux 可显式选 bubblewrap。没有隔离后端就拒绝执行，绝不降级为直接运行候选代码。
- **Agent Line / 飞书告警 / 字体与媒体预算**：在私有 JSON 配置，均不从生产部署继承。

## 边界

- QQ 单 writer、群聊只由真实 self `@` 唤醒、仅最终内容出站；以平台 receipt 判断送达。
- 普通成员没有 owner 主机权限。`host.root` 是兼容的内部能力名，不代表自动获得系统 root。
  工具受当前用户、配置的 sandbox/权限模式和原任务授权限制。
- 停止服务按本实例的 PID/创建时间及进程树处理；Windows 另使用 Job Object。
  不按端口杀进程，不为注入 NapCat 强杀普通 QQ。
- 控制台 / 聊天默认绑定回环，也可显式绑定服务机 Tailscale IPv4；不允许 `0.0.0.0`、公网或普通 LAN 绑定。
  浏览器与服务不在同机时，在向导的“本机 / Tailscale 地址与端口”设置 `management_host` / `native_host`，
  重启后访问服务机 Tailscale 地址，不是浏览器机器的 `127.0.0.1`。
- 直接进入保留实际 TCP peer、Host / Origin / CSRF 与 DSH 签名 cookie / WebSocket 边界，不信转发头。
  **能访问控制台的人有实例控制权限，必须用 Tailscale ACL 限制访问者。** 这不是公网免认证方案。
  如需额外密码，可在私有配置显式开启 `management_require_key` / `native_require_key`。

候选内的 `UPGRADE.md` 说明更新/回滚，`MIGRATION.md` 说明源码改动与未验收项，
`VALIDATION.md` 记录本轮真实验证边界；这些 1.0 文档将随对应源码一起公开，不以远端旧同名文件替代。
各组件许可不同，发布前必须审查候选中的 `THIRD_PARTY_NOTICES.md`。
