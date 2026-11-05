# 配置 PPT API

在 Windows 或 macOS 上，启动 `cell_ppt` 的第一步是运行 `python -X utf8 scripts/ppt_credentials.py check`。已有凭据时从本 Skill 的固定位置读取并实时核验余额。查询不扣费。余额不足时保留当前资料，暂停付费提交。遇到网络问题先重试查询。缺少凭据或鉴权失败时先配置，再进入其他步骤。

- 用户已有 PPT 客户端 API 密钥时，提供一次本机安全输入。交互终端运行 `python -X utf8 scripts/ppt_credentials.py setup`，密钥以隐藏输入接收。自动化可以用 `setup --from-stdin` 通过标准输入传入。不要在命令参数、界面、日志、客户交付或发布包里显示密钥。
- Windows 用当前用户的 DPAPI 加密，保存到 `config/ppt-api-key.dpapi`。需要 Python 的 `pywin32`。
- macOS 将密钥保存在当前用户钥匙串 `com.cell-skills.cell-ppt`，在 Skill 内固定用 `config/ppt-api-key.keychain` 定位。首次读取时，系统可能提示授权访问钥匙串。
- 配置后确认检查成功再继续原任务。只接受 PPT 客户端密钥。分发 Skill 时排除本机 `config/` 目录。
