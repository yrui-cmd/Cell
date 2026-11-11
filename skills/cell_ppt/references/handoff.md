# 交接协议

用 `python -X utf8 scripts/handoff.py build 已锁定的方案.json 交接目录`。交接目录必须是新目录；提交前运行 `python -X utf8 scripts/handoff.py inspect 交接目录`。依赖为 PyMuPDF、python-pptx；提交还用 requests。制作后实际渲染查看规划 PPTX，核对文字是否溢出、逐页安排是否可读。脚本不能代替人工审读材料、全文身份和客户答复。

## 方案输入

- 新任务记录 `intake.mode`（`default` 或 `personalized`）和 `intake.response_source`（用户选择原文或消息编号）。两种模式都以 `questions_locked: true` 表示参数已齐备，`questions` 必须覆盖且不重复 `style`、`audience`、`page_count`、`language`、`aspect_ratio`、`template`、`duration`、`focus`、`outcome`、`scope`、`materials`。
- 默认模式每项含 `field`、`asked: false`、`answer` 和 `state`。拟定值记 `defaulted`，客户已提供的参数记 `provided` 并附 `response_source`。交接 PDF 按实际来源标记参数。
- 个性化和未记录模式的旧任务沿用实际问答记录。每项含 `field`、实际呈现的 `question`、`asked: true`、`answer`、`state`（`confirmed` 或该项真实授权的 `delegated`）及 `response_source`（用户答复原文或消息编号）。
- `design` 必填 `style`、`language`、`aspect_ratio`（推荐 `16:9`）、`palette` 和整数 `page_count`；页数等于 `pages` 长度，含首页、总目录、正文中的章节目录/导航页和感谢页，不含模板参考页。`template_notes` 必填，写名称/编号及使用说明，不用模板写“无模板”。
- `timing` 为整数秒 `total`、`talk`、`qa` 和布尔 `includes_qa`。逐页 `seconds` 合计必须等于演讲时间。
- `pages` 按最终页序排列，每项写 `kind`、`title`、`story`、`evidence`、`visual`、`content`（实际上屏完整正文）、`layout`（版式/位置/比例/配色要求）、`notes`（制作注释，不直接上屏）、`seconds`，新稿另写 `page_role`（`cover` / `overview` / `chapter` / `content` / `thanks`）、`story_guide`（问题、观察、结论、转场或结构页的讲述提示）和 `source_locator`（来源编号、原PDF物理页、图号及面板、段落/Methods检索关键词；自有资料用文件名、图编号、实验/样本说明）。旧稿缺这些字段时脚本回退到原有字段。可附章节编号、口播和转场。默认 `pages` 第一项为首页（`kind: cover`），第二项为总目录页（`kind: agenda`），最后一项为感谢页（`kind: thanks`）；中间安排正文及按需穿插的章节目录/导航页。章节目录也用 `kind: agenda`，不限制 `pages` 中的目录数量；在 `content` 写实际目录条目，在 `layout` 和 `notes` 写明当前章节高亮状态及插入目的。三类页面必须在 `outline.json`、规划 PPTX 和 PDF 的 PPT内容区逐页写全内容、排版与注释，不能只出现在模板参考区。三类页面都占正式页数，在确认总页数之内分配；目录内容对应实际章节。用户明确要求省略、合并或局部制作时，记录该要求并按其执行。不再用一页方案概括多个成品页。只填写本次演示的内容和客户已确认的要求。
- `sources` 依序列 `title`、`path`。必用论文必须列齐，核验后设 `required_paper: true`、`fulltext_verified: true`。先匹配题名、作者和 DOI，再检查原文正文、图表、末页和出处；仅摘要、缺页或错文献一律先尝试合法下载。取不到才集中向客户索取具体 PDF。非 PDF 附原件，可另设 `readable_pdf` 指向可信渲染件。无外部附件且资料已充分时填 `original_request` 作为资料正文。
- 有原生参考时填 `template.path` 和 `template.picks`，每项写 `page`（源页码从 1 起）、`kind`、`style`（唯一）、目录项可加 `agenda_states`。同时提供 `template.readable_pdf`（模板源文件完整、实际渲染的 PDF）及 `template.rendered_from_sha256`（对应源 PPTX 摘要）。脚本把所选代表页的预览并入 PDF 模板区。无实际文件、只选库模板编号时，用 `template_id` 和 `template_notes` 写清库编号与要求，不伪造模板预览。全页审计后只留使用的代表页；精简模板的目录参考样式仅保留一页，可在 `agenda_states` 记录各章节高亮状态。这仅是模板参考去重规则，不限制最终 PPT 或 `pages` 中总目录、章节目录与导航页的数量。检查模板源与精简版的实际可见外观、字体及母版依赖。若用户要求仅复制可见部分，在临时副本中先清理明确隐藏或画布外的对象、无关源备注等，保留会影响可见外观的组、蒙版和依赖；复杂遮挡按视觉核对。截图或 PDF 参考先用可见画面做参考样页 PPTX，保持实际参考风格，并注明视觉参考与原生对象的区别。客户指定库模板时记录其编号。
- PDF 固定顺序为 **问答 → 模板 → 资料 → PPT内容**。开头第一行写 `PPT 总页数：N 页`，随后写 `模板：名称/编号/无模板`；模板分区始终存在。N 是最终 PPT 内容页数，必须与内嵌索引的 page_count 一致，不能使用整份 PDF 的物理页数。每个 PPT 逻辑页另起一张 PDF 页，以 `# 第 N 页：标题` 开头，包含完整内容、排版和注释；太长时自动续页，续页不增加 PPT 页数。
- 构建输出 `outline.json`、逐页安排 PPTX、交接 PDF 及可选精简模板 PPTX。规划 PPTX 用醒目中文页型和独立的“本页内容 / 故事展开 / 资料定位”分栏供本地审阅，完整正文及排版注释以 PDF 的 PPT内容区和 outline 为准，不用生图；仅上传 PDF，不上传规划或模板 PPTX。
- 同时嵌入 `ppt-material-index.json`（兼容和分区定位）和 `cell-ppt-handoff.json`（本地兼容），两者必须一致。`page_count` 是 1–500 的整数目标 PPT 页数，与内容页清单和首页声明一致；网站以首页明确声明的目标 PPT 页数报价，不等于 PDF 总页数。PDF 索引 schema 2 记录四区页段、`material_start`、`content_start`、每个 PPT 逻辑页对应的 PDF 页段、规划/模板摘要。资料区不再延伸到 PDF 末尾。`inspect` 继续支持旧 schema 1，避免阻断原订单查询和领取；新任务统一生成 schema 2。
- 原始文件只读，保留附件、书签及 SHA-256。制作端依序阅读四区，参考资料与最终上屏内容明确分开。


## 客户确认

发送到制作接口之前，先完成当前 PDF 的构建、inspect 和内容核对，再在原聊天展示以下确认清单；不能只给下载链接或只问是否使用额度。

1. 提供当前交接 PDF 与规划 PPTX 的可点击链接，写明文件版本、PDF 物理总页数、最终 PPT 内容页数和相应额度，明确仅上传交接 PDF。
2. 按 PDF 实际顺序列出“问答、模板、资料、PPT内容”各部分的物理页码范围及摘要。问答列实际制作参数；模板列名称/编号或无模板；资料列实际来源及对应页段，不重复粘贴全文。
3. 列出全篇章节大纲，再按最终页序逐页展示 PPT内容区。每页使用 `# 第 N 页：标题（页型；PDF 第 X–Y 页）`，列出实际正文/要点、故事主线、配图及资料定位、版式和制作注释。首页、总目录、章节导航及感谢页也逐一列出，不能合并成“其余页面类似”。内容以当前 PDF 为准，不用旧大纲或凭记忆概括；正文较长可分条展示，但不省略关键结论、数字、条件和限制。每页的 PDF 页段包括其正文续页，并区分 PPT 逻辑页码与 PDF 物理页码。
4. 清单必须先完整展示，再用用户提问工具简短询问：**“确认按以上大纲和每页内容制作 N 页 PPT，并使用 N 额度吗？确认后才发送 PDF。”** 选项为“确认，按此版制作并发送 PDF”和“先修改内容”；额度按实际报价填写，不硬编码。没有提问工具时直接在回复中询问并等待。默认模式、已确认需求、之前同意页数/额度，都不能代替对当前 PDF 内容的确认。
5. 等到真实肯定答复后才生成 `approval.json`，再允许上传、确认报价并入队。未答复或选择修改时保持未确认，不先上传再补问。字段沿用 `approved: true`、inspect 返回的 `sha256`（新单仅 `material` 的 PDF 摘要）、`credits`、`thread_id` 和 `customer_confirmation`（可核对的客户答复原文或消息编号）。另在 `approval-review.md` 留存实际展示的清单、当前 PDF SHA-256 和确认问题/答复出处，便于核对展示内容与提交版本一致；此记录不能代替真实答复。
6. 改稿使用新的交接目录，重新生成 PDF、核对页码及摘要，展示更新后的大纲与逐页清单并明确改动，再确认新版本。上传前再次核对 PDF 摘要与获批版本一致；确认后文件发生变化则不得沿用旧确认。对完全未变且已有上述真实确认的版本，恢复任务时不重复提问。



## 故事与配图定位

- 页型必须在可见页顶显示：首页 / 封面、总目录、章节导航、正文、感谢页；PDF每页标题也标注页型。总目录与章节导航用不同名称，导航注明当前章节。
- `content` 写上屏正文；`story_guide` 写便于作者续写的论证过程和转场；`source_locator` 给可检索的位置，不能只写“见论文”或模糊主题。研究结论与样本单位、原文限制对应，资料详细程度不受规划PPT摘要截取长度限制；完整内容保留在PDF和备注。
- 文献来源可设 `id: R1`、`source_type: literature`，逐页引用该编号、DOI、原文页码和图panel；参考文献或全文已经在后面提供时，不必把论文/文献图重复塞进每张规划页。只有图像有助于理解时才选放。保留供制作端阅读的已核验全文资料。
- 自有资料优先多保留相关原图、不同实验/视野、图注、条件与说明，集中放后面时列清每张图对应哪一页、支持哪项结论。不要为多而添加无关图、复制同图或伪造缺失图。
- 每页可加 `assets: [{"path": "原图.png", "caption": "图编号、内容、实验条件与本页关系", "source_id": "U1"}]`。当前脚本支持PNG/JPEG，将全部图片和图注按原比例附在PDF对应内容页后，并嵌入原件；这些资料续页不新增PPT页数或额度。集中在资料区的PNG/JPEG `sources` 也会显示图片并保留附件；用 `source_locator` 连接内容页。其他格式先生成可信的 `readable_pdf`，同时保留原件。
