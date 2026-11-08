# cell_ppt

用于做pptx。

## 安装与配置

需要 Python 3.11 或更新版本。将本仓库克隆到 Codex 的 Skills 目录，文件夹名保持为 `cell_ppt`，例如：

```bash
git clone https://github.com/yrui-cmd/cell_ppt.git ~/.codex/skills/cell_ppt
cd ~/.codex/skills/cell_ppt
```

如设置了 `CODEX_HOME`，请改用其下的 `skills/cell_ppt`。在实际运行 Skill 的 Python 环境中执行：

```bash
python -m pip install -r requirements.txt
python -X utf8 scripts/ppt_credentials.py setup
python -X utf8 scripts/ppt_credentials.py check
```

`setup` 隐藏输入自己的 PPT 客户端密钥。Windows 用 DPAPI 加密，macOS 使用系统钥匙串；不要分发 `config/`。更新时在本仓库目录执行 `git pull --ff-only`。本机 `config/` 已加入忽略规则，不会上传到 GitHub。

## 使用

安装后重启 Codex 并新建聊天。本仓库可独立使用，无需安装 Cell 总入口。源码采用 [MIT 许可](LICENSE)。

在 Codex 中说“使用 cell_ppt”并提供主题、论文、图片或参考模板。流程先检查 API，并提醒尽量提供相关图片。选择「默认」会直接拟定逐页安排，选择「个性化」才逐项确认。确认版本及报价后上传制作。完整规则见 [SKILL.md](SKILL.md)。

新接口只上传一份交接 PDF。PDF 第一行写 `PPT 总页数：N 页`，服务按这一声明识别最终 PPT 内容页数，每页 1 个 PPT 页额度；内嵌索引与首页保持一致。模板、问答、资料和正文续页不另计费。规划及模板 PPTX 留在本地审阅。进度面板展示估算时间和订单状态；重复查询及恢复沿用原订单。上传确认入队并打开进度面板后，聊天立即停止，只保留进度入口；后台接收并校验成品，Python 收到并校验后一次性唤醒原聊天，不创建定时任务，先询问是否录屏；按选择录制整个 PowerPoint 软件窗口或直接输出，全部完成后在原聊天提供文件并致谢。

元素预览需要桌面版 Microsoft PowerPoint，Windows 通过 PowerShell/COM、macOS 通过 AppleScript 控制独立预览副本。macOS 首次可能要求自动化授权。Linux 可用于部分离线工具，但不支持当前凭据配置及桌面预览流程。

代码依赖固定外部接口 `https://xiaomiao-ai.com/api/ppt/v1`，首次使用应持有该服务的 PPT 客户端密钥和足够页额度。开源不代表远端制作免费，也不包含 PowerPoint 软件许可。

## 逐页内容规划

规划稿明确标注首页、总目录、章节导航、正文和感谢页。每页分列实际内容、故事展开和资料定位，方便按问题、观察、结论和转场继续写讲稿。文献图标明参考编号、原PDF页码及图号/面板，全文已附时不重复堆放；自有资料尽量完整附相关原图、图注和逐页对应关系，可放对应内容页后或集中资料区，资料续页不增加PPT页数或额度。

默认模式沿用已给要求，其余参数按主题和资料拟定。个性化模式逐项确认风格、受众、页数、语言、比例、模板、时间、重点、范围和资料。两种模式都整理 `outline.json` 供审阅。每页包含实际正文、排版、素材依据和制作注释。交接 PDF 按“问答 → 模板 → 资料 → PPT内容”排列，开头标明 PPT 总页数和模板，每页内容以 `# 第 N 页：标题` 开头。文件版本与额度确认后，沿用原有上传和后台进度流程。
