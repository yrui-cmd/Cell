# 内部状态与执行约定

本文件面向运行 Skill 的宿主模型，不是交付给作者的研究报告。宿主负责读原始材料、判断科学含义、写作与视觉检查；Python 负责去重计数、来源版本核验、真实红色字体及阶段条件。不要向用户索要本文件的 JSON，让宿主从现有材料建立。

## 环境

Python 3.10+，依赖 `python-docx`。缺少依赖时在项目环境安装 `requirements.txt`；不要修改全局环境或删除用户文件。输出使用真实 `.docx`，不能把 Markdown/HTML 改后缀。

Word 渲染优先使用宿主现有文档能力；在配有 LibreOffice 的环境，可转 PDF 并以图像逐页检查。PDF 和页面图片留在内部工作区。未完成渲染不能声称已验证版式。当前包不绑定特定在线工具或绝对路径。

## 命令

在 skill 根目录执行，`work` 是本次内部工作目录：

```sh
python scripts/reviewer_docs.py check1 work/ledger.json
python scripts/reviewer_docs.py stage1 work/ledger.json --out work/01_审稿意见_Figure归类与解决方案.docx
python scripts/reviewer_docs.py fingerprint work/ledger.json
python scripts/reviewer_docs.py check2 work/ledger.json
python scripts/reviewer_docs.py stage2 work/ledger.json --out work/02_Response_to_Reviewers.docx
python scripts/test_reviewer_docs.py
```

`check2` 和 `stage2` 返回码 2 表示存在必须处理的问题，不得更改脚本绕过。失败时不会创建新的最终文件，也不会覆盖已有最终文件；更不能拿旧文件当作本轮完成结果。日志留内部。

## 状态结构

顶层字段为 `schema_version: 1`、`meta`、`artifacts`、`reviewers`、`comments`、`issues`、可选 `figure_map`、`checks`；第二阶段另需 `verification`。

### meta

- `title`、`manuscript_id`、`journal`：已知才填写。标题不详可空，不虚构作者/单位/编号。
- `original_comment_count`：完整提取到的父意见总数，不是拆分的问题数。必须与 `comments` 长度一致。
- `review_sources_complete`：所有来源是否完整读到，真实布尔值。为 false 时 `source_gaps` 必须指出具体缺页/缺审稿人/截断位置。第一阶段可继续，第二阶段不通过。
- `current_manuscript_id`：最终已核对稿件的 artifact ID；稿件修改定位均指向它。第一阶段尚未收到可留空。
- `opening`：第二份 Word 的简短开场；事实核对完成后填写。不要预填“全部建议均已采纳”。
- `signature`：可选，仅作者提供署名时使用，不要求为生成回复而查找个人身份。

### artifacts

每项包括 `id`、`path`、`sha256`，可增加 `kind`、`origin_id`、`provenance`、`version`。

`path` 为真实可访问路径，或相对于 ledger 的路径；不写猜测的挂载路径。`sha256` 由文件实际字节计算，不能是任意 64 位字符串。原文件改变后旧记录必须失败，宿主重读并更新所有受影响回复后才能重新存入新摘要。不要只刷新哈希而保留旧的事实核验状态。

审稿源文件为纯文本/Word 可直接核对原文。来自 PDF、图片、邮件或对话的评论，先通过可用读取工具完整读取，保存逐字转录的 UTF-8 文本作为核对来源；记录原始文件或消息的 `origin_id` 和来源位置。转录本不是新证据，不能省略不能读取的原始内容。PDF 有可提取文本时不先 OCR。

程序直接核对 TXT/MD/CSV/TSV/JSON/DOCX 内的原文与可选引文；图像/PDF等文件只核对可访问性和哈希，内容仍须由宿主实际查看。表格里的 Word 原文也可读取。不要把“有哈希”当成“科学结论正确”。

DOCX 的普通段落提取不能证明公式、图片、旧式绘图、文本框、嵌入对象或外部内容块已被读取。程序检测到这些对象时，第二阶段要求该 artifact 增加 `object_review`：`source_sha256` 必须等于当前文件摘要，`inspected_types` 覆盖程序报告的类型，`notes` 记录实际查看的位置和结果。该记录只证明宿主对当前版本做了对象级查看，不证明公式或图的科学内容正确；文件改变后必须重查。

计算文件摘要示例：

```python
from pathlib import Path
import hashlib
path = Path(actual_source_path)
digest = hashlib.sha256(path.read_bytes()).hexdigest()
```

### reviewers 与 comments

`reviewers` 中每位编辑/审稿人有 `id`、`label`、`kind`（editor/reviewer）、`order`、`comment_count`。原顺序使用显式整数，编号 10 不能排到 2 前。编辑的要求始终先于 reviewer；多个 editor 依原顺序。

每个 `comments` 项：

```json
{
  "id": "R1-C3",
  "reviewer_id": "R1",
  "order": 3,
  "original_label": "Comment 3",
  "original_text": "从实际来源逐字提取的完整原文",
  "source_artifact_id": "review-transcript",
  "source_locator": "Reviewer 1, Comment 3",
  "final_response": "第二阶段有证据后写入的完整正式答复",
  "final_issue_ids": ["R1-C3a", "R1-C3b"]
}
```

示例字段解释不是可直接用来生成用户文档的事实；真正运行时逐项替换为实际内容。无原编号时 `original_label` 留空，内部 ID 继续用于追踪；不能编造原编号。每条原文必须在来源中找到，允许读取时的换行/空格差异，不允许改写。

### issues

每个问题有：

- `id`、`comment_id`；后者只能对应一个父意见。
- `primary_group`：仅一个主归属，如 `Figure 2`、`Supplementary Figure S1`、`General / Methods`。
- `panel_refs`：原稿分图定位；`related_groups`：其他相关图或章节，不重复计数。
- `question`：该原子问题要回答什么。处理稿默认中文。
- `route`：reply_only / manuscript_edit / figure_fix / reanalysis / new_experiment / evidence_lookup / reasoned_disagreement。
- `status`：ready / open / resolved。
- `draft_response`：第一阶段拟回复，能写好的先写；未来结果依赖部分明确待补，不写伪造完成时。
- `evidence`：现有证据引用列表。
- `plan`：未解决时必填六个内容，见下。
- `resolution`：已经完成实质处理时填写，见下。

`ready` 只用于 reply_only 且有现有证据、没有待实施修改；`open` 为待解决，第一份中真实标红；`resolved` 要有实际处理结果。不采纳建议使用 reasoned_disagreement 路线，只有科学理由充分、必要正文修改落实才为 resolved。

`plan` 的六个非空字段：

| 字段 | 要写什么 |
| --- | --- |
| action | 具体处理动作 |
| inputs | 最少必需材料或数据；已有材料直接指明 |
| design | 分析/实验设计或文字/图形修改的具体方法，不强行套实验模板 |
| output | 要产生的结果、目标分图/章节/图注 |
| acceptance | 回答审稿问题的核对标准，不把 P<0.05 当成统一标准 |
| fallback | 结果不支持原说法或方案不可行时如何如实调整 |

证据引用结构：

```json
{
  "artifact_id": "actual-source-id",
  "locator": "Methods, paragraph 3; Figure 2c legend",
  "supports": "该位置能够支持的具体事实",
  "excerpt": "可选：必须在源文件中能逐字找到的引文"
}
```

`resolution` 结构：

```json
{
  "disposition": "implemented",
  "summary": "实际做了什么，以及怎样回应审稿问题",
  "evidence": [],
  "changes": [],
  "no_change_reason": "仅在无需修改稿件时填写具体理由"
}
```

`disposition` 只能为 implemented / clarified / reasoned_disagreement；`evidence` 非空。`changes` 是引用最终稿真实修改位置的证据对象列表，由脚本汇总进对应父意见的正式回复。无稿件修改时明确理由，不为满足字段制造修改。`changes` 使用当前稿的 artifact ID；页码、行号和图号是否准确由宿主核对。

`final_response` 的覆盖列表必须包含该父意见所有子问题 ID，不能拿“其他地方已回复”代替当前 reviewer 的完整答复。脚本检查集合相同；宿主仍须逐句检查实际文字是否确实覆盖。

### figure_map

发生重编号时记录 `original`、`revised`、`evidence`，例如旧 Figure 2d 对应新 Figure 3b。不得根据编号顺序猜映射。最终答复正文要使用新编号，并保留必要的旧图对应说明。程序保留并核对映射证据，不擅自全局字符串替换正文。

### checks

第二阶段必须全部为 true：`coverage`、`evidence`、`locations`、`figures`、`humanizer`、`facts_after_humanizer`。这些字段是宿主实际完成相应核对后的记录，不能一开始全填 true。

任何来源、正文、结果、图号、回复发生实质变动，先把受影响核验项重置为 false。检查失败处理原问题，不修改校验规则。图表未发生变化也要核对引用一致性，不能跳过 `figures`。

全部核对完成后运行 `fingerprint`，把返回的 `content_sha256` 与真实核对日期写入：

```json
"verification": {
  "checked_at": "YYYY-MM-DD",
  "content_sha256": "fingerprint 命令返回的 64 位摘要"
}
```

摘要绑定当前 artifacts 哈希、稿件元信息、审稿人顺序、原文、问题、解决证据、正式回复和图号映射；不包含 `checks` 自身。任何被绑定内容变化都会使第二阶段失败，必须重新核对后生成新摘要。机械刷新摘要不能代替重新阅读。

## 文档交付检查

第一阶段必须看见红色待处理条目及具体方案；无待处理条目时不强行标红。第二阶段不能有作者待办、占位符、内部任务 ID、工作日志或虚构修改位置。审稿人原文中的问题或占位符是原始证据，不能被清理规则擅自改写。

将脚本生成的文件用宿主 Word 工具渲染，检查每一页；必要的字体/段落微调之后重新检查。Word 生成成功与科学核验通过是不同环节，二者均实际执行。

所有测试数据与输出仅为实现验证，默认不发给用户。一次会话第一阶段结束只交第一份；成功完成第二阶段只交第二份。
