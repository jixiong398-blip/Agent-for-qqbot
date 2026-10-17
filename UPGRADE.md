# 原生运行时更新与恢复

> 当前主线是未发布的 **1.0.0**。旧 Hermes / 0.x 已停更，历史 tag 保留不改。
> 新链路的验证边界见 [MIGRATION.md](MIGRATION.md)，旧版历史变更在 [CHANGELOG.md](CHANGELOG.md)。

## 从旧 Hermes 迁移

- 使用源码目录之外的**新私有实例目录**。不要把 `AGENT_QQBOT_HOME` 指向旧 home。
- 停止旧 QQ writer 后，按 README 配置新的 DSH + NapCat 链路；没有 Hermes fallback。
- 不自动导入旧 `.env`、YAML、数据库、sessions、日志、人格或生产计划任务。
  人格通过用户主动选择文件或向导正文保存；旧数据原样留存。
- 不执行历史 `UPGRADE_MAP`、旧脚本双写或复制整个 home 的流程。

## 更新源码与运行时

普通用户优先使用预构建包：停止本实例后完整解压新包，运行新包 `update.bat` 或
`runtime/python/bin/python3 extras/scripts/portable_launcher.py update`，再启动。
运行时选择不会编译 / 联网安装依赖，不自动登录 QQ；已有 NapCat 登录目录不在未审核的更新中原地覆盖。
以下源码流程仅供维护者，不是用户前置步骤。

1. 停止本实例控制台和自有服务。保留私有配置、数据及恢复备份。
2. 人工检查并更新源码目录；本工具不会 `git pull`、reset、覆盖本地补丁或自动下载 GitHub 最新版。
3. 执行 `update.bat` / `python3 extras/scripts/bootstrap.py update`。
4. 安装器在新的 `runtimes/<内容指纹>-<随机标识>` 内装配**整个固定 DSH fork**，
   用上游锁文件和依赖补丁装配 Host/Web/UI/原生模块，不混装官方宿主。
   相同 fork/平台/Node/插件依赖配方已成功构建时，可复用私有原生依赖，仅生成新业务快照；首次仍需完整构建。
   复用记录写入安装回执；不要手工删除仍被新快照引用的旧 runtime 目录。
5. 成功后通过可恢复的 profile 依赖链接切换；manifest、前一运行时和切换回执保留。
   安装/源码编译不等于功能验证，不会自动启服。

依赖首次安装可能联网并编译；旧离线 Node/Electron 包不被当作兼容性证据。
固定版本、SHA 与来源在 `application.toml`；实例自选 endpoint/model/账号/路径不写回源码。

## 回滚与故障

- `python extras/scripts/bootstrap.py rollback`（Linux 用 `python3`）：在所有自有服务停止后
  选择前一个已安装运行时，不启动它，不回退数据库/session schema，不撤销已经发生的 QQ/Qzone 效果。
  先核实数据格式兼容，不能把“切回代码”当成完整数据恢复。
- 依赖下载/编译失败保留诊断目录，未完成运行时不被选为活动版本。
- 断电等中断切换会保留 `private/runtime-switch.json`，启动器拒绝冒充切换完成；
  `recover-runtime` 命令只恢复回执中已知的依赖链接与 manifest，不扫描/删除其他路径。
- `doctor` 只读本地配置、工具版本和源码指纹，不建 home、不请求模型/QQ，也不是测试套件。
- `Stop-All.bat` 只请求本实例鉴权控制台停止自有进程；未运行的控制台或未知端口不会触发杀进程。

## 原生模型设置的保存与应用

DSH 设置页面“保存”仅保存草稿；“应用”排队给实例 supervisor。
supervisor 先核对工作静默及配置指纹，暂停 QQ 入口后再次检查，才重启 Web→Gateway。
新输入竞态时保留原任务；失败保留操作记录和配置备份，并尝试恢复前一配置。
新鲜 Host/通道就绪后才标记 applied，不通过 systemd/root oneshot 提权。

文件事务与实际服务验收的范围分开记录在 [VALIDATION.md](VALIDATION.md)；不沿用 Linux 历史生产记录作新链路的通过证据。
