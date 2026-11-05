# 交接协议

用 `python -X utf8 scripts/handoff.py build 已锁定的方案.json 交接目录`。交接目录必须是新目录；提交前运行 `python -X utf8 scripts/handoff.py inspect 交接目录`。依赖为 PyMuPDF、python-pptx；提交还用 requests。制作后实际渲染查看规划 PPTX，核对文字是否溢出、逐页安排是否可读。脚本不能代替人工审读材料、全文身份和客户答复。

## 方案输入

- `questions_locked: true` 只在关键问答完成时填写。`questions` 每项写 `question`、`answer`、`state`（`confirmed` 或 `delegated`）。`confirmed` 记录客户自行选择或明确采用推荐的结果，并在任务单保留出处。`delegated` 记录明确委托范围及所作选择。既有偏好注明出处。
- `timing` 为整数秒 `total`、`talk`、`qa` 和布尔 `includes_qa`。逐页 `seconds` 合计必须等于演讲时间。
- `pages` 按最终页序排列，每项写 `kind`、`title`、`story`、`evidence`、`visual`、`seconds`，可附章节编号、口播和转场。封面、目录等占正式页数。不再用一页方案概括多个成品页。只填写本次演示的内容和客户已确认的要求。
- `sources` 依序列 `title`、`path`。必用论文必须列齐，核验后设 `required_paper: true`、`fulltext_verified: true`。先匹配题名、作者和 DOI，再检查原文正文、图表、末页和出处；仅摘要、缺页或错文献一律先尝试合法下载。取不到才集中向客户索取具体 PDF。非 PDF 附原件，可另设 `readable_pdf` 指向可信渲染件。无外部附件且资料已充分时填 `original_request` 作为资料正文。
- 有原生参考时填 `template.path` 和 `template.picks`，每项写 `page`（源页码从 1 起）、`kind`、`style`（唯一）、目录项可加 `agenda_states`。全页审计后只留使用的代表页，目录仅一页。检查模板源与精简版的实际可见外观、字体及母版依赖。若用户要求仅复制可见部分，在临时副本中先清理明确隐藏或画布外的对象、无关源备注等，保留会影响可见外观的组、蒙版和依赖；复杂遮挡按视觉核对。截图或 PDF 参考先用可见画面做参考样页 PPTX，保持实际参考风格，并注明视觉参考与原生对象的区别。客户指定库模板时记录其编号。
- 每份原始文件入只读清单，记录路径、SHA-256、来源和授权。PDF 中的书签和嵌入索引给出 `material_start`、材料页段及规划/模板摘要，首页也打印资料起始页。问答可多页。制作端读取全部问答页；资料起始页必须与书签、索引和首页文字一致。

## 客户确认

交付当前规划 PPTX 供客户确认，同时列出待发送的 PDF、参考模板、各自页数和额度。收到明确的版本及提交额度确认后才生成 `approval.json`。字段为 `approved: true`、inspect 返回的完整 `sha256`、`credits`、`thread_id` 和 `customer_confirmation`（可核对的客户答复原文或消息编号）。改稿用新的交接目录，先修订受影响的问答或材料，再生成并重发确认。不得用本地 JSON 代替实际客户确认。

