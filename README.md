# Agent-for-qqbot · Bot 1.0

原生 DSH + NapCat 的 QQ Bot：角色脑 / 行动脑协作、场景记忆、原生 Web 与真实发送回执。

> **1.0.0 是新架构主线，尚未发布。** 旧 Hermes / 0.x 停更，历史 tag 保留。
> GitHub 目前仅更新说明，公开代码的 `VERSION` 仍为 `0.14.16`；不要把旧下载包当成 1.0。
> 以下描述 1.0 预构建候选的交付方式，不代表已有公开下载或 QQ 验收通过。

**产品统称 Bot，没有固定人物。名字、别名、性格和背景由你自己决定。**

## 普通用户：解压 → 安装 → 原生 DSH 配置

1. 下载与系统匹配的 **Windows x64 / Linux x64 预构建包**，完整解压到独立目录。
   包含 Python、Node、固定版本 DSH / Web、原生模块和干净的 NapCat 组件；**不需要安装 Python、Node、Git，也不在用户机器编译。**
2. Windows 双击 `install.bat`；Linux 执行 `sh install.sh`。
   只做完整性检查、私有实例初始化与运行时装配，然后直接打开 **DSH 原生页面**。
3. 在 DSH 的 **Bot 配置 → 模型与脑区** 填供应商地址、模型 ID、协议和预算。
   云端填 API Key；本地免鉴权模型显式选择“本地免 Key”。行动脑可复用角色脑模型，也可分别配置。
4. 在 **角色设定** 自取名字，编辑或导入 Markdown 人格，点击 **保存并应用配置**。
   DSH 空闲时应用并重连；密钥不回显，不删除历史。
5. 点击 **Bot 主会话** 即可先体验 Web 聊天，**不需要 QQ 或 NapCat 登录**。

第一次尚未填模型时，DSH 也能先启动配置窗口；不会擅自使用其他部署的模型或凭据。

## 按需接入 QQ：仍在 DSH 内完成

打开 **NapCat / QQ** 窗口：

1. 点击 **启动 NapCat**，再点 **打开 NapCat 管理页面**，由你扫码登录。
2. 若管理页要求密码，可显式点击 **复制 NapCat 管理密码**；密码不放进 URL 或日志。
3. **刷新已登录账号 → 选择账号 → 配置此账号的本机连接**。
   为本实例生成带 Token 的回环 HTTP / WebSocket 参数，不覆盖其他已启用的监听器。
4. 按窗口提示重启**本实例** NapCat，填写 Owner QQ，勾选 **显式启用 QQ 接入**，保存并应用。
5. 查看新鲜连接状态。未登录、账号不符、Token 错误或通道未就绪，不会冒充连接成功；DSH 配置页仍可打开。

预构建候选固定 NapCat **4.18.38**，来源与 SHA-256 在 `application.toml`。
不打包作者的 QQ 登录、数据库、缓存或账号配置；不自动关闭普通 QQ。
Linux QQ 宿主 / 图形依赖仍须符合 NapCat 官方要求；包含 Shell 组件不等于所有发行版的 QQ 接入已验收。

**本轮仍跳过真实 NapCat→QQ、Qzone 和飞书发送，不能宣称 QQ 已验收。**

## 日常使用与数据

| 操作 | Windows | Linux / WSL |
|---|---|---|
| 安装并打开原生 DSH | `install.bat` | `sh install.sh` |
| 启动 | `start.bat` | `sh start.sh` |
| 配置 | DSH 内的 Bot 配置 / NapCat 窗口 | 同左 |
| 停止本实例 | `Stop-All.bat` | `sh stop.sh` |
| 使用已解压的新预构建运行时 | 停止后运行新包 `update.bat` | 停止后运行新包的更新入口 |

默认数据在用户目录的 `.agent-for-qqbot`，可用 `AGENT_QQBOT_HOME` 指定独立私有目录。
数据与程序分离；新包不覆盖人格、数据库或登录记录。不要指向旧 Hermes home，不要把私有实例上传或递归打包。
角色需要完全隔离时另建实例。多个实例需要独立端口与 NapCat 目录。

## 安全与边界

- 用户产品只绑定 **本机回环**，没有远程组网软件依赖或远程部署步骤。
  开发者的远程维护工具不属于安装包和用户配置。
- 默认没有额外 Bot Key 登录页；仍保留实际 TCP peer、Host / Origin / CSRF、DSH 签名 cookie 与 WebSocket 校验。
  模型 API Key、OneBot Token 与内部凭据独立保存，不因取消登录页而取消。
- 普通成员没有 owner 主机权限。工具受当前用户、权限模式与原任务授权限制；`host.root` 兼容标识不代表系统 root。
- QQ 单 writer，只以真实 self `@` 唤醒群聊，只发布最终内容；工具建议、排队与回合结束不是送达证明。
- 默认关闭外部自动化和隔离工程执行；无隔离后端时不降级为直接运行候选代码。
- Live2D、知识库与语音转写为可选能力，不恢复旧 TTS 自动发语音链路。

## 开发者：源码构建不是用户安装流程

源码构建需要 Python 3.12+、Git、兼容 Node/npm、原生编译工具和足够构建内存；由维护者完成。
`extras/scripts/build_portable.py` 从已构建的固定 fork、校验过的 Python / NapCat 资产生成独立预构建候选，
不复制运行 home；`package_source.py` 仅生成源码 staging，不冒充成品安装包。

公开模板在 `templates/`，旧 `hermes/templates/` 仅作兼容指引。
候选内的 `UPGRADE.md`、`MIGRATION.md`、`VALIDATION.md` 说明更新、迁移及验证边界。
发布前仍须完成 `THIRD_PARTY_NOTICES.md` 所列许可 / 素材权利与完整历史隐私审查。
