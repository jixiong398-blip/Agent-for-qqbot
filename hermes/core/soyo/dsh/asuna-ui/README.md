# Asuna 原生控件的适配（GPL-3.0-only）

来源 `eamars/AsunaCognitionCore` commit `4b4ddfa0a56b288e85fb22dd9a2a6db80f532abc`。
固定客户端与许可证保留在 `vendor/` 和 `LICENSE`；来源/hash 在 `vendor/source.json`。
该文件同时记录上游原始字节和接收副本摘要；接收副本仅有换行与两处空白行尾空格差异，无实现变更。

- 复用 CollabThread、InlineWork/WorkFragment、RoleToolRow、BrainMeters 等控件。
- Memory/Settings/Trigger 等的类别、revision、模型路由和原生来源有独立适配，不安装整套 Asuna 人格或 Mongo 后端。
- 行动线程、工具次数、报告、认知详情与发送状态读取实际 native session/ledger，不在打开页面时唤醒模型。
- 默认角色/行动标签由私有人格与配置提供。历史兼容 namespace/审阅工位名不保证实际模型就是 GPT。
- 设置“保存”是草稿，“应用”交实例 supervisor，保留工作静默/竞态重查/配置指纹/回滚证据。
  不要求 root，不自动运行 systemd；不把 applied、回合结束或审阅意见当成平台送达。

`build_client.py` 先核对 vendor 原始字节摘要，再统一换行并与 `adapter.js` 生成客户端及 manifest。
适配片段不是可独立执行的 JS 模块，须用最终生成的 `client.js` 验证。
当前实际构建与浏览器验证范围见根目录 `VALIDATION.md`；生成 hash 不代替完整 UI / 许可验收。

宿主要求完整固定 fork `0.2.1-rc.2` / `5713aab7963851d1a87482058c33c4af0e1c2ff8`。
统一安装器装配本地 manifests 与 client roster，不混装官方 npm 宿主与局部 fork UI。
