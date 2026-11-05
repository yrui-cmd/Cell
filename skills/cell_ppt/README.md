# cell_ppt

整套 PPT 制作客户端，支持 Windows 与 macOS。需要 Python 3.11 或更新版本。源码按仓库根目录 MIT 许可发布；远端 PPT 制作服务不包含在此源码包内。

## 安装与配置

运行仓库的 `python install.py` 后，进入实际安装的 `cell_ppt` 目录，在运行 Skill 的 Python 环境中执行：

```bash
python -m pip install -r requirements.txt
python -X utf8 scripts/ppt_credentials.py setup
python -X utf8 scripts/ppt_credentials.py check
```

`setup` 隐藏输入自己的 PPT 客户端密钥。Windows 用 DPAPI 加密，macOS 使用系统钥匙串；不要分发 `config/`。`install.py --force` 会替换整个安装目录，更新前备份本机配置，更新后恢复到同一用户环境，或重新运行 setup。

## 使用

在 Codex 中说“使用 cell_ppt”并提供主题、论文、图片或参考模板。流程先检查 API，再逐项问答，准备逐页安排与资料包，确认版本及报价后才上传制作。完整规则见 [SKILL.md](SKILL.md)。

服务按规划 PPTX 与参考模板 PPTX 的实际页数计费，每页 1 个 PPT 页额度，PDF 不计费。进度面板展示估算时间和订单状态；重复查询及恢复沿用原订单。完成后下载并校验成品 PPTX。

元素预览需要桌面版 Microsoft PowerPoint，Windows 通过 PowerShell/COM、macOS 通过 AppleScript 控制独立预览副本。macOS 首次可能要求自动化授权。Linux 可用于部分离线工具，但不支持当前凭据配置及桌面预览流程。

代码依赖固定外部接口 `https://xiaomiao-ai.com/api/ppt/v1`，首次使用应持有该服务的 PPT 客户端密钥和足够页额度。开源不代表远端制作免费，也不包含 PowerPoint 软件许可。
