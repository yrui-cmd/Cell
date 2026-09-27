# cell-review

**版本：1.1.0**
**用途：** 将研究主题转化为一篇参考所属领域顶级期刊标准、具有综合判断且证据可追溯的完整文献综述。

默认是问题驱动的批判性叙述综述。运行时显示五个阶段，最终只交付包含至少 30 篇经核验有效引用的 Word（.docx）综述；内部证据材料仍保存在任务目录，便于复查和续写。

## 安装到 Codex

解压安装包，在解压后的文件夹内打开终端，执行：

```bash
python scripts/install_skill.py
```

脚本把完整目录复制到：

```text
Windows: %USERPROFILE%\.agents\skills\cell-review
macOS / Linux: ~/.agents/skills/cell-review
```

也可以手动把整个 `cell-review` 文件夹复制到上述 `skills` 目录，确保 `SKILL.md` 直接位于该文件夹中，而不是多嵌套一层。

安装脚本不下载、不联网、不安装 Python 包。已有同名 Skill 时默认拒绝覆盖。明确更新时执行：

```bash
python scripts/install_skill.py --replace
```

旧版本备份到 `.agents/skill-backups/`，不放在 Skill 扫描目录里。使用自定义技能根目录时传入 `--skills-root "实际路径"`。

Codex 没有显示新 Skill 时重新启动会话。上述本地目录与调用方式依据 OpenAI 官方技能文档；其他宿主按各自的 Skill 导入机制使用，不假定所有客户端都接受相同安装方式。

## 使用

在 Codex 中发送：

```text
$cell-review

请围绕“肿瘤相关成纤维细胞如何影响三阴性乳腺癌的化疗响应”
完成一篇中文文献综述，参考所属领域顶级期刊的真实标准和同类综述。

重点分析主要机制、相反证据、因果验证和适用边界。
运行时只显示当前步骤，最终只交付完整 Word（.docx）综述，正文实际引用至少 30 篇真实、相关、经核验且去重的学术文章。
```

这只是调用示例，不预设该主题的科学结论，也不会在安装时开始检索。换成自己的主题即可；也可以附上已有材料、目标期刊、语言或篇幅要求。完全没有主题时，Skill 会先要求提供主题。

## 固定工作流

```text
第1步：确定问题与顶刊参照
第2步：检索与筛选文献
第3步：提取与评价证据
第4步：综合论证与撰写
第5步：核验与交付
```

顶刊对标会区分官方要求、实读范文特点与本次编辑决策，不假造字数或图表要求。检索与原始证据由宿主实际执行，不把“DOI 存在”当成“正文主张已证实”。

## 交付内容

本次安装包包含 Skill 指令、期刊对标与证据规范、综述内容检查表、JSON 工作模板、本地初始化与审核脚本、非覆盖式安装脚本及测试。

**日后运行本 Skill 的唯一最终交付**是一篇可编辑的完整 Word（`.docx`）综述，至少实际引用 30 篇真实、相关、经核验且去重的学术文章。默认 `review.docx`，内部源稿 `_work/review.md` 不交付。不输出 PDF/Markdown 代替，不把不足 30 篇的稿件宣称为完成。内部 `_work/` 不自动作为一堆报告交给用户；正式综述必需的方法和附录仍应纳入主交付，不能隐藏。

## 能力边界

这是**宿主驱动型 Skill**，不是脱离大模型运行的独立文献综述服务。宿主负责真实搜索、读全文和图表、证据评价、主题综合及写作。需要宿主具备相应工具和权限；本地脚本本身不检索文献、不绕过付费墙、不调用额外模型。

Python 脚本只需 **Python 3.10+ 标准库**。具体测试环境见本版本测试报告。无需额外 API key 或第三方 Python 依赖。

强制 Word 最终交付和至少 30 篇有效引用，不强制生图、三个数据库、论文打分或多智能体。没有完成正式系统综述方法时，不把输出称为完成的系统综述；没有真实统计时不生成 Meta 分析数字。

内容台账预检 `RECORDS_CONSISTENT` 不是最终验收；必须再由 `delivery_gate.py` 检查 Word 文件及至少 30 篇有效引用。两者都不是科学正确或顶刊可录用认证。Word 导出与逐页预览使用宿主的实际文档工具，附带脚本不冒充文档渲染器。语义支持需要宿主回到来源核查；受访问限制时须按已有证据降低结论范围并披露限制。

## 开发者检查

```bash
python -m unittest discover -s tests -v
```

所有测试使用明确的合成记录，不冒充真实论文或数据库检索。`TEST_REPORT.md` 说明已测试与未测试内容。

## 主要文件

```text
SKILL.md
agents/openai.yaml
references/
  journal-benchmark.md
  evidence-workflow.md
  review-types.md
  writing-and-qa.md
  word-and-reference-gate.md
  data-contract.md
  sources.md
templates/
  protocol.json
  evidence.json
  review-outline.md
scripts/
  install_skill.py
  review_tools.py
  delivery_gate.py
tests/
  test_review_tools.py
  test_delivery_gate.py
  trigger-cases.json
README.md
TEST_REPORT.md
CHANGELOG.md
```

方法与官方格式来源见 `references/sources.md`。构建此 Skill 不等于已经为任何具体题目完成过一次文献综述。
