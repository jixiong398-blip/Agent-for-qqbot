# 第三方来源与许可边界

本文件记录来源，不替代各组件的完整许可证，也不是组合分发许可已通过的结论。

| 组件 | 来源/参考版本 | 保留的许可 |
|---|---|---|
| 原模板分发内容 | QQBot Contributors | 根级 `LICENSE`（MIT），仅适用于其覆盖的内容 |
| Hermes 衍生内容与历史归属 | Nous Research / Hermes Agent | `hermes/core/LICENSE`（MIT） |
| Soyo QQ channel | AsunaCognitionCore `@asuna/napcat-qq@0.2.0`，参考 commit `a89c945a8560e3d7bf702d0815ee91ed7b2a1363` | `hermes/core/soyo/qq/LICENSE`（GPL-3.0-only）及 `NOTICE.md` |
| Asuna UI 复用与适配 | AsunaCognitionCore commit `4b4ddfa0a56b288e85fb22dd9a2a6db80f532abc` | `hermes/core/soyo/dsh/asuna-ui/LICENSE`（GPL-3.0-only）；保留 vendor 源码与版权头 |
| Bot DSH Host 与 Dashboard 接缝（内部兼容 namespace 为 `soyo`） | 本地独立适配模块 | 各自目录 `LICENSE`（MIT） |
| 原生 DSH / Cordis / 上游 Web | `eamars/deepseek-harness` fork commit `5713aab7963851d1a87482058c33c4af0e1c2ff8` | 构建时保留完整源码、依赖与原始许可证；不得只用根 MIT 标签覆盖 |
| 预构建 Python | python-build-standalone CPython 3.12.15，20261013 | 随包保留 Python 发行物的原始许可；`application.toml` 固定资产与摘要 |
| 预构建 Node | 使用已验证固定 fork 构建的同平台运行时，版本写入 manifest | 须保留原始 Node 许可及其第三方通知 |
| 干净 NapCat 组件 | NapNeko/NapCatQQ 4.18.38 官方 Release | 固定 URL / SHA-256；依其原许可及附带 QQ 组件各自权利，不含维护者账号数据 |

AsunaCognitionCore 上游：<https://github.com/eamars/AsunaCognitionCore>。
DSH / Cordis 等外部运行依赖仍需各自的版本锁定、来源和原始许可；本次同步未导入完整
依赖树到公开工作区。安装器在私有实例中构建并记录固定源码、原始 lock 与部署根覆盖后的 lock 摘要；
实际安装/运行验证不代替组合许可及对应源码分发审查。
Live2D 的 Electron、PIXI/Cubism 与可选模型素材、NapCat/QQ 等继续适用各自归属；
源码 staging 不包含模型、QQ 登录状态或第三方离线二进制包，不能据此授予素材再分发权。
私有预构建候选包含运行依赖；保留 fork 对应源码归档和可取得的原许可，仍不等于组合分发 / QQ 二进制再分发审查通过。

不能用根级 MIT 标签覆盖 GPL 组件，也不能据此宣布整个历史项目重新许可。
公开打包前还需确认组合分发、对应源码、生成产物和依赖兼容义务。
