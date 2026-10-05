# 内部数据契约（schema_version 1.0）

本契约用于可追溯记录和本地一致性检查。它不能证明记录来自真实检索；宿主必须只填实际完成的动作。空值使用 null，不能编造数值或把未读取标为已读取。

## protocol.json

由初始化模板生成。补充明确 question、scope、added_value、实际 last_search_date 和 evidence_cutoff。review_type 可选 `critical_narrative`、`scoping`、`systematic`、`meta_analysis`。

在进入正式写作前填写 `capabilities` 的显式布尔值及 `document_export` 能力列表，并完成 `article_count_feasibility`：status 为 `feasible`、`at_risk` 或 `insufficient`，同时记录真实 assessed_at 和判断依据。`null` 表示尚未检查，不能通过最终 audit；`insufficient` 表示不能按完成稿交付。

`load_bearing_questions` 是承重问题覆盖表：

```json
{
  "id": "LQ001",
  "question": "哪一个问题的答案会改变正文结论？",
  "needed_information": "作出判断实际需要的信息",
  "search_ids": ["Q001", "Q004"],
  "current_judgment": "基于当前证据的有限判断",
  "remaining_unknowns": ["仍无法确定的关键条件"],
  "impact_on_conclusion": "未知如何限制或改变结论",
  "status": "answerable_with_limits"
}
```

状态可为 `answerable`、`answerable_with_limits`、`unresolved_conflict`、`search_failed`、`no_eligible_evidence`、`material_unavailable`。每个 search_id 必须指向真实 searches 记录；尚未检查的承重问题不能通过最终 audit。

`citation_style` 默认 `numeric_draft`，正文使用 [1]、[1,2]、[1–3]，书目每项独立一行，以 `[1]` 开始，书目二级标题为“参考文献”或“References”。不支持脚注 `[^1]` 代替引用。内部源稿保持 `numeric_draft`，确保确定性核查。最终 Word 的引用样式用 `output_citation_style` 指定为 `numeric` 或 `custom`；后一种必须提供最终稿引用映射，不得以样式改变绕过实际引用核查。

## evidence.json

顶层必须有 searches、records、claims、benchmarks、issues 五个数组和 host_self_review 对象。以下是字段说明，不是真实研究数据。不要将例子当成文献证据。

### searches[]

```json
{
  "id": "Q001",
  "source": "实际使用的数据库或搜索工具名称",
  "query": "实际提交的完整查询式",
  "searched_at": "2026-09-27",
  "purpose": "supporting / counterevidence / methods / mapping / update",
  "status": "completed",
  "reported_count": null,
  "examined_count": null,
  "retrieved_count": null,
  "limits": "实际日期、语言、类型或截断限制；没有则写 none",
  "result_locator": "真实工具结果引用、可用URL或保存的文件定位"
}
```

status 可用 `completed`、`partial`、`failed`。三个 count 均为非负整数或 null；总量、实读量和实取量语义不同，不互相推算。失败的查询不支持“已覆盖某数据库”的结论。无可用检索时在 issues 披露原因；本地提供文献的内容核查仍可继续。

### records[]

```json
{
  "id": "R001",
  "study_id": "S001",
  "article_id": "A001",
  "citation_number": 1,
  "title": "实际核实的完整文献标题",
  "authors": ["实际作者或团体作者"],
  "year": 2024,
  "identifier": "真实 DOI、PMID、ISBN 或稳定来源定位",
  "publication_type": "original_research",
  "publication_status": "published",
  "screening_status": "included",
  "screening_reason": "根据预定标准纳入的实际理由",
  "reading": {
    "abstract_read": true,
    "full_text_read": true,
    "key_figures_checked": false,
    "supplements_checked": false
  },
  "metadata_check": {
    "status": "verified",
    "checked_at": "2026-09-27",
    "source": "实际检查的元数据出处",
    "fields_checked": ["title", "authors", "year", "identifier"]
  },
  "publication_check": {
    "status": "checked",
    "checked_at": "2026-09-27",
    "source": "实际核实版本和公告的出处",
    "outcome": "no_notice_found"
  },
  "extraction": {
    "question": "原研究问题",
    "object_and_conditions": "对象、模型和条件",
    "design": "研究设计",
    "independent_sample_unit": "独立样本单位",
    "sample_size": null,
    "key_results": [],
    "observed_result": "研究直接报告的观察，不混入解释",
    "author_interpretation": "原作者对观察结果的解释",
    "review_inference": "本综述基于多项证据作出的推断",
    "result_state": "observed_effect",
    "comparability": {
      "status": "comparable_with_limits",
      "dimensions": ["对象", "条件", "终点", "时间窗", "分析方法"],
      "limits": ["实际不可比或部分可比之处"]
    },
    "evidence_type": "association",
    "alternative_explanations": [],
    "limitations": [],
    "role_in_review": "对当前问题的支持、挑战或边界贡献"
  },
  "evidence_dependency": {
    "independence_status": "partly_overlapping",
    "related_record_ids": ["R002"],
    "basis": "共享队列、数据库、样本或二次分析的实际依据"
  }
}
```

`citation_number=null` 表示内部记录但不列入最终书目。`screening_status` 可为 included、excluded、awaiting_full_text、context_only。排除记录要有理由；只读摘要不应伪填全文状态。`study_id` 是报告关联，不自动意味着样本独立。

publication_status 可为 published、preprint、corrected、retracted、expression_of_concern、unknown。原始来源可能没有 DOI、确切年份或作者，保留真实不确定性，不补造。

metadata_check.status 可为 verified、pending、failed；引用文献必须完成身份核对。publication_check.status 可为 checked、limited、pending；limited 必须通过 issues 说明对稿件的影响。outcome 可为 no_notice_found、notice_found、unclear。“未发现公告”不是永远没有公告的保证。

`metadata_probe.py` 的 `verified/not_found/unavailable` 是 DOI 注册查询状态，不可直接等同于这里的 `metadata_check.status=verified`。只有宿主实际对照记录中的题名、作者、年份、标识符并保存来源后，才能把元数据核验记为完成；出版公告仍由 `publication_check` 单独记录。

`evidence_dependency.independence_status` 可为 independent、partly_overlapping、dependent、unclear。它不改变文章身份计数，却约束正文能否称为“独立复现”。`comparability.status` 由宿主如实定义和解释；若关键维度不可比，不得以形式字段把研究强行合并。阴性结果在 observed_result 中明确是未观察到、精度不足、等效/非劣成立还是方向相反。

`result_state` 可为 observed_effect、no_effect_observed、insufficient_precision、equivalence_or_noninferiority、opposite_direction、descriptive_or_not_applicable。所有实际引用记录都要填写 evidence_dependency；直接支持主张的记录必须填写三层证据、result_state 和 comparability，旧记录缺字段时进入待复核而不是默认通过。

### claims[]

```json
{
  "id": "C001",
  "text": "最终正文中实际出现的一句承重主张。",
  "kind": "association",
  "scope_note": "说明对象、条件、限制与不确定性",
  "content_checked": true,
  "links": [
    {
      "ref_id": "R001",
      "locator": "实际小节、页码、图或表号",
      "support": "direct",
      "check_level": "full_text",
      "checked": true
    }
  ]
}
```

kind：descriptive、association、intervention、mechanism、prediction、synthesis、hypothesis。support：direct、context、counter。check_level：abstract、full_text、figure、supplement。

字面 text 必须在最终正文出现；一个复合断言含多种证据时拆开登记。content_checked 只有实际回看原文后才设为 true。因果/干预、复杂机制断言不允许仅由摘要直接支撑；假说和整合解释必须明确身份。

check_level 对应各自阅读标记，图或补充材料需要真实视觉检查；locator 不能填虚构图号。对 retracted 文献，链接只能是明确状态的 context 或 counter，不能为正常事实提供 direct 支持。

### benchmarks[]

```json
{
  "journal": "实际匹配的目标或参照期刊",
  "article_type": "Review",
  "rationale": "为何与学科、问题和读者匹配",
  "official_guideline": {
    "status": "read",
    "source": "实际官方作者指南URL",
    "checked_at": "2026-09-27",
    "requirements": ["只记录已核实要求；不要猜测具体数字"]
  },
  "exemplars": [
    {
      "title": "实际参考综述标题",
      "identifier": "真实稳定标识",
      "read_level": "full_text",
      "lesson": "可借鉴的论证与组织方法，不复制文本"
    }
  ],
  "editorial_decisions": ["本次编辑选择，勿冒称期刊明文要求"]
}
```

指南 status：read、partial、unavailable。partial / unavailable 要创建限制记录；不强制让访问失败项“通过”。没有范文可读也记录限制。无主题时不能先造一份固定期刊清单。

### issues[]

```json
{
  "id": "I001",
  "type": "full_text_unavailable",
  "status": "open",
  "impact": "scope",
  "detail": "真实存在的限制和影响",
  "manuscript_disclosure": "正文中实际出现的相应限制说明。"
}
```

status 为 open 或 resolved；impact 为 core、scope 或 internal。core：关键问题或关键方法仍未完成，禁止当成核验通过；scope：可在降低结论范围后交付，必须披露；internal：已替代的小故障或不影响稿件的运行事项，不要求写入正文。不能为通过校验而把关键缺口改成 internal。

type 可包括 benchmark_unavailable、exemplar_unavailable、search_unavailable、full_text_unavailable、publication_status_limited、methods_incomplete 等。对 scope/core 的 open 项，manuscript_disclosure 必须真实出现在正文中。

### host_self_review

使用模板中的十项自查。只有宿主实际检查后才能全设为 true。status 改为 completed，checked_at 为真实日期；用 `hash` 子命令获得内部 `_work/review.md` 的 SHA-256 后写入 `review_sha256`，用 `context-hash` 子命令获得当前问题、范围、证据、主张与开放问题的语义上下文哈希，写入 `semantic_context_sha256`，并保留模板中的 `context_hash_version`。脚本不自动把这些字段设为已完成。

该自查是当前宿主自查，不是独立评审。正文变化会使 review_sha256 失效；问题边界、检索语义、关键证据、提取、主张关系或开放问题变化会使 semantic_context_sha256 失效。纯运行日志和操作时间不参与语义哈希。旧任务没有语义哈希时进入待复核状态，不能默认沿用旧自查；无需为了哈希而把临时来源和隐私文本传到外部。

## v1.1.0 最终交付字段（向后兼容的数据契约扩展）

`protocol.output_format` 固定为 `docx`；`output_file` 为任务根目录下单个 `.docx` 文件名，不得包含目录跳转。`minimum_article_count` 默认 30，可以提高但不能低于 30。`output_citation_style` 为 `numeric` 或 `custom`。内部正文统一保存在 `_work/review.md`。

`records[].article_id` 将同一文章的预印本、正式版等版本关联，不能与 `study_id` 混淆。计数仍会用规范化稳定标识和标题交叉去重；不同 `article_id` 不能让同一文章重复计数。`publication_type` 使用真实类型；允许计数的值见最终门槛规范。文章应有明确相关性（`extraction.role_in_review`）和指向正文实际主张的已核验 `claims[].links`，不能仅附一个书目编号。

`delivery_review` 使用模板中的新对象。只有真实完成 Word 内容与排版复核后才能把 checks 标为 true；source_sha256 绑定当前内部稿，docx_sha256 绑定当前 Word。记录真实 checked_at、page_count、pages_inspected 和实际 preview_locator，预览所有页面而不是只看首页。`citation_map` 仅在最终样式非数值型时必需：每项包含 `ref_id`、`marker`、`body_excerpt`、`reference_excerpt`；后二者必须逐字存在于 Word 正文和参考文献部分，body_excerpt 包含真实 marker 和至少一句登记的主张；reference_excerpt 包含文章完整标题。详见 `word-and-reference-gate.md`。

文献数不足 30 的情形通过 issues 记录为 core（例如 `insufficient_articles`），并在稿件/交付语句明确未完成。不能靠删除问题记录让 final gate 放行；final gate 独立重数。

## v1.3.0 证据上下文与最终 Word 扩展

保持 `schema_version=1.0`，以兼容已有 JSON 读取器；新增字段是 1.3.0 的保守扩展。新建任务由模板直接生成，旧任务缺少承重问题、能力/篇数评估或语义上下文哈希时必须补做复核，不能静默当成已完成。

开放的 scope/core `issues[].manuscript_disclosure` 必须逐字存在于内部源稿和最终 Word 正文；只在源稿出现不算交付披露。core 问题即使已披露仍阻止完成交付。

自定义引用样式下，`delivery_review.citation_map[].marker` 不仅要出现在该记录的 `body_excerpt` 中，每个 `claims[].links[].word_excerpt` 还必须含其 `ref_id` 对应的自身 marker。一个含其他文章标记、但不含当前文章标记的片段不能证明当前链接实际进入最终 Word。
