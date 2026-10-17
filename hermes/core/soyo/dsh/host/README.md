# 原生 DSH Host 边界（MIT）

通过项目根目录的统一安装器装配，见 [主说明](../../../../../README.md) 与
[迁移状态](../../../../../MIGRATION.md)。本轮为已做 Windows/WSL 本地验证的源码候选，尚未发布；范围见 [验证边界](../../../../../VALIDATION.md)。

- 固定整套 Asuna DSH fork `0.2.1-rc.2` / `5713aab7963851d1a87482058c33c4af0e1c2ff8`，不只替换 UI 包。
- `index.mjs` 是独立本机回环入口，保留 DSH Host/Origin/cookie/API/mux admission。
  默认本机直接进入，无额外 Key 页面；远程维护软件不属于用户产品。
  检查实际 TCP peer，不相信转发头；原生签名 cookie、Host/Origin 和 WebSocket admission 仍保留。
  `setup-api.mjs` 仅把原生用户配置 RPC 接到固定私有 supervisor，不暴露为模型工具或任意 URL。
- `qq-native.mjs` 接收持久入站与单 writer 回执；只发布最终完成内容，不重放历史效果。
- `role-runtime.mjs` / `dual-brain.mjs` 分离角色与行动权限；正文不能伪造 owner grant。
  内部兼容能力名 `host.root` 不授予系统 root，实际由当前用户与配置 sandbox/权限模式限制。
- `platform.mjs` 处理 POSIX/Windows 私有文件、目录同步和鉴权 loopback/UDS；不在 Windows 跳过权限检查。
- `business-ui.mjs` 的设置保存和应用分开；应用交实例 supervisor 静默检查/重载/失败恢复，不运行 systemd/root helper。
- `gpt-reviews.mjs` 是兼容的独立审阅工位名，实际模型、wire 协议与 endpoint pin 来自显式行动路由。
  工位是新鲜无工具上下文，审阅意见不是执行效果。
- `automation.mjs` 仅安装配置的未来任务；Qzone/简报/告警有独立 effect fence，不恢复生产任务 ID 或时间。
- `live2d.mjs` 只调用当前实例鉴权桌面，需原 owner grant；`accepted` 不冒充动画已完成。
- `persona.mjs` 从私有 SOUL/BEHAVIOR 装载身份；兼容 namespace 不等于默认角色。

旧 `install_root.py`、`install_data.py`、`install_qq.py`、`prepare_profile.py`、`sync_models.py`
和 root 设置应用入口已退休。不要用它们补建生产服务、复制其他 home 或恢复 Hermes fallback。
可选外部效果与完整生产异常恢复仍须单独验收；静态语法和本地契约通过不能替代真实 QQ 或发布验收。
