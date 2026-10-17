# 管理控制台 → 原生 DSH 接缝（MIT）

当前控制台由 `soyo.app.web` 提供，根 `modules/dashboard/server.py` 仅为兼容入口。
只监听实例配置的回环地址，要求私有密钥、Host/同源/CSRF；没有 Hermes backend 选择或 unit 默认值。

插件导航到显式配置的干净 URL，不 iframe、不向浏览器注入密钥；原生 DSH Web 有自己的认证。
固定 `0.2.1-rc.2` fork 的工具注册和客户端 module loader 用于接线。

`soyo_dashboard` 的会话白名单来自部署，不从模型参数/群昵称判断。默认安装仅授权明确的
本机 owner Session 读取绑定状态与控制台日志，`controlSessionIds` 为空，模型不能重启 supervisor。
UI 操作由实际登录操作者走控制台鉴权；QQ/Agent Line 不因自称 owner 获权。

API 固定回环、无环境代理/重定向/隐式重试，密钥从指定私有文件读取，不进入工具结果。
缺认证、错误 backend 或不确定响应均拒绝；接受安排不代表操作完成。

## 原生配置界面

`client.js` 在 DSH 侧栏注册 Bot 配置 / NapCat 入口，使用原生 `dialog`、分类导航、
卡片分组与固定保存栏。角色脑 / 行动脑分别用紫 / 蓝标签，高级模型预算默认折叠。
样式只作用于 `bqs-*` namespace，继承 DSH 明暗主题 token；窄屏改为顶部分类，尊重减少动态效果偏好。
不加载远程字体、图标、样式或 iframe，不改变后端凭据及 QQ 权限边界。
真实浏览器已覆盖三类页面、草稿保留、Markdown 导入、预设、保存重连及手机 / 深色模式；
不因界面验收启动 NapCat、调用推理或发送 QQ。完整边界见根 `VALIDATION.md`。
