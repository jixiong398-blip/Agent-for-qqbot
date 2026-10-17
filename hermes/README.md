# Agent-for-qqbot — 原生 DSH 源码

当前是 1.0 原生 DSH QQ Agent 主线的未发布源码候选；旧 Hermes / 0.x 停更。
安装/配置/启动重构与未验证项见 [迁移说明](../MIGRATION.md)，使用入口见 [README](../README.md)。

## 源码入口

- `core/soyo/dsh/`：原生 Host、Web 适配、角色与行动协作。
- `core/soyo/app/`、`core/soyo/platform.py`：统一安装、配置、实例服务与跨平台边界。
- `core/soyo/qq/`：NapCat 通道、入站/出站、任务、真实回执与持久化。
- `core/soyo/memory/`、`core/soyo/social/`：独立记忆与社交状态。
- `core/tests/soyo/`：版本化回归与探针源码；最新实际验证范围见 [验收记录](../VALIDATION.md)。

QQ 使用单 writer、final-only 和真实 receipt；群聊仅 self `@` 唤醒。
普通成员没有 `host.root`。公开办事请求经持久便签、独立审阅与 owner 决定，
不因正文自称身份扩权；Hermes Gateway 不作为回退 writer。

根 bat/sh 已改为统一入口；不要直接运行退休的旧 Hermes/root 安装助手，不自动迁移旧数据库或配置。
各组件原始许可见 [第三方归属说明](../THIRD_PARTY_NOTICES.md)。
