# 交接协议

用 `python -X utf8 scripts/handoff.py build 已锁定的方案.json 交接目录`。交接目录必须是新目录；提交前运行 `python -X utf8 scripts/handoff.py inspect 交接目录`。依赖为 PyMuPDF、python-pptx；提交还用 requests。制作后实际渲染查看规划 PPTX，核对文字是否溢出、逐页安排是否可读。脚本不能代替人工审读材料、全文身份和客户答复。

## 方案输入

- 新任务记录 `intake.mode`（`default` 或 `personalized`）和 `intake.response_source`（用户选择原文或消息编号）。两种模式都以 `questions_locked: true` 表示参数已齐备，`questions` 必须覆盖且不重复 `style`、`audience`、`page_count`、`language`、`aspect_ratio`、`template`、`duration`、`focus`、`outcome`、`scope`、`materials`。
- 默认模式每项含 `field`、`asked: false`、`answer` 和 `state`。拟定值记 `defaulted`，客户已提供的参数记 `provided` 并附 `response_source`。交接 PDF 按实际来源标记参数。
- 个性化和未记录模式的旧任务沿用实际问答记录。每项含 `field`、实际呈现的 `question`、`asked: true`、`answer`、`state`（`confirmed` 或该项真实授权的 `delegated`）及 `response_source`（用户答复原文或消息编号）。
- `design` 必填 `style`、`language`、`aspect_ratio`（推荐 `16:9`）、`palette` 和整数 `page_count`；页数等于 `pages` 长度，含首页、目录页和感谢页，不含模板参考页。`template_notes` 必填，写名称/编号及使用说明，不用模板写“无模板”。
- `timing` 为整数秒 `total`、`talk`、`qa` 和布尔 `includes_qa`。逐页 `seconds` 合计必须等于演讲时间。
- `pages` 按最终页序排列，每项写 `kind`、`title`、`story`、`evidence`、`visual`、`content`（实际上屏完整正文）、`layout`（版式/位置/比例/配色要求）、`notes`（制作注释，不直接上屏）、`seconds`，可附章节编号、口播和转场。默认 `pages` 第一项为首页（`kind: cover`），第二项为目录页（`kind: agenda`），最后一项为感谢页（`kind: thanks`）；中间放实际正文。三类页面必须在 `outline.json`、规划 PPTX 和 PDF 的 PPT内容区逐页写全内容、排版与注释，不能只出现在模板参考区。三类页面都占正式页数，在确认总页数之内分配；目录内容对应实际章节。用户明确要求省略、合并或局部制作时，记录该要求并按其执行。不再用一页方案概括多个成品页。只填写本次演示的内容和客户已确认的要求。
- `sources` 依序列 `title`、`path`。必用论文必须列齐，核验后设 `required_paper: true`、`fulltext_verified: true`。先匹配题名、作者和 DOI，再检查原文正文、图表、末页和出处；仅摘要、缺页或错文献一律先尝试合法下载。取不到才集中向客户索取具体 PDF。非 PDF 附原件，可另设 `readable_pdf` 指向可信渲染件。无外部附件且资料已充分时填 `original_request` 作为资料正文。
- 有原生参考时填 `template.path` 和 `template.picks`，每项写 `page`（源页码从 1 起）、`kind`、`style`（唯一）、目录项可加 `agenda_states`。同时提供 `template.readable_pdf`（模板源文件完整、实际渲染的 PDF）及 `template.rendered_from_sha256`（对应源 PPTX 摘要）。脚本把所选代表页的预览并入 PDF 模板区。无实际文件、只选库模板编号时，用 `template_id` 和 `template_notes` 写清库编号与要求，不伪造模板预览。全页审计后只留使用的代表页，目录仅一页。检查模板源与精简版的实际可见外观、字体及母版依赖。若用户要求仅复制可见部分，在临时副本中先清理明确隐藏或画布外的对象、无关源备注等，保留会影响可见外观的组、蒙版和依赖；复杂遮挡按视觉核对。截图或 PDF 参考先用可见画面做参考样页 PPTX，保持实际参考风格，并注明视觉参考与原生对象的区别。客户指定库模板时记录其编号。
- PDF 固定顺序为 **问答 → 模板 → 资料 → PPT内容**。开头第一行写 `PPT 总页数：N 页`，随后写 `模板：名称/编号/无模板`；模板分区始终存在。N 是最终 PPT 内容页数，必须与内嵌索引的 page_count 一致，不能使用整份 PDF 的物理页数。每个 PPT 逻辑页另起一张 PDF 页，以 `# 第 N 页：标题` 开头，包含完整内容、排版和注释；太长时自动续页，续页不增加 PPT 页数。
- 构建输出 `outline.json`、逐页安排 PPTX、交接 PDF 及可选精简模板 PPTX。规划 PPTX 是本地审阅摘要，完整正文及排版注释以 PDF 的 PPT内容区和 outline 为准，不用生图；仅上传 PDF，不上传规划或模板 PPTX。
- 同时嵌入 `ppt-material-index.json`（兼容和分区定位）和 `cell-ppt-handoff.json`（本地兼容），两者必须一致。`page_count` 是 1–500 的整数目标 PPT 页数，与内容页清单和首页声明一致；网站以首页明确声明的目标 PPT 页数报价，不等于 PDF 总页数。PDF 索引 schema 2 记录四区页段、`material_start`、`content_start`、每个 PPT 逻辑页对应的 PDF 页段、规划/模板摘要。资料区不再延伸到 PDF 末尾。`inspect` 继续支持旧 schema 1，避免阻断原订单查询和领取；新任务统一生成 schema 2。
- 原始文件只读，保留附件、书签及 SHA-256。制作端依序阅读四区，参考资料与最终上屏内容明确分开。


## 客户确认

交付当前规划 PPTX 供本地审阅，明确只有交接 PDF 会上传，列出 PDF 总页数、最终 PPT 内容页数和相应额度，模板预览已包含在 PDF 内。收到明确的版本及提交额度确认后才生成 `approval.json`。字段为 `approved: true`、inspect 返回的 `sha256`（新单仅 `material` 的 PDF 摘要）、`credits`、`thread_id` 和 `customer_confirmation`（可核对的客户答复原文或消息编号）。改稿用新的交接目录，先修订受影响的问答或材料，再生成并重发确认。不得用本地 JSON 代替实际客户确认。

