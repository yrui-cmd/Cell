# 新增引用与全文引用的证据策略

在正式检索前，按研究问题与用户要求记录 `reference_composition_policy`：`experimental75` 用于实验主题或用户明确要求75%的任务，保留实验文献至少75%的门槛；`domain_specific` 用于理论、计算、观察等问题，记录实际适用的 `target_designs`，不强加实验比例；`prespecified` 用于正式系统综述、范围综述或Meta分析，按预定纳入标准记录目标设计，不为配比排除合格研究。新任务必须填写模式、依据 `basis` 与统计单位；非实验比例模式将 `minimum_experimental_percent` 设为null。不得在看到比例不足后为放行而改策略。问题、用户明确要求或纳入标准确实改变时，保存变更理由并重做受影响的证据选择与自查；用户明确配比与纳入标准冲突时先说明冲突，不擅自改变任一要求。各模式均保留去重、真实分类、主张支持与反证覆盖；无适用原始研究不能靠空书目通过。

补引或替换任务按新增且最终保留的去重学术文章统计；整篇重建参考文献时按全文最终实际引用统计。仅experimental75模式要求实验性研究至少占75%，最低篇数向上取整。原有文献再次引用或改编号仍是原有文献；替换为另一篇真实新文章算新增。单纯语言润色不触发检索，也不为比例删除作者原有引用。

实验性文章指实际开展实验或干预并报告原创结果的研究。细胞、动物、材料、现场实验与人体干预均按实际设计判断；观察性、纯计算或理论研究、综述、系统综述和Meta分析不自动计入。混合研究须核对本论文开展的相关实验部分。具体实验结论优先回溯原始论文，综述保留用于领域梳理和综合观点。分类从实际方法与结果取得，不能只看 original research 标签。

计数前核实文章身份、相关性与主张支持，并对照最终稿的正文引用和书目。同一篇的数据库记录、预印本和正式版只算一篇；研究家族关联不代表独立复现。无法核实的设计保留在分母，不计入实验分子。experimental75模式未达到75%时补检相关实验研究，不能以无关引用凑数或自行改阈值；仍不足则说明实际比例及缺口，不宣称补引完成。系统性综述继续遵守预定纳入标准，不为比例删去合格研究。

在任务内部保存 `reference-composition.json`，包含本次范围判断所需的最终引用文章；非文章类网页或软件说明不计入文章分母。字段示意如下，内容为空时保持待核实状态，不直接作为完成记录：

```json
{
  "scope": "added",
  "reference_composition_policy": {
    "mode": "domain_specific",
    "minimum_experimental_percent": null,
    "unit": "unique_eligible_articles_actually_cited",
    "target_designs": ["theoretical"],
    "basis": "示例：本任务研究问题是理论命题；实际使用时替换为本任务依据"
  },
  "records": [
    {
      "id": "R001",
      "article_id": "A001",
      "identifier": "实际 DOI 或其他稳定标识",
      "title": "实际完整题名",
      "publication_type": "original_research",
      "origin": "added",
      "final_cited": true,
      "study_design": {
        "category": "unverified",
        "verified": false,
        "basis": "",
        "locator": ""
      }
    }
  ]
}
```

`scope` 为 `added` 或 `all`；`origin` 为 `added` 或 `existing`。只将最终正文实际引用且书目对应的记录设为 `final_cited: true`；被删除的候选记为 false。新增范围应保留原有文章的身份与 origin，以免同一文章换版本或编号后被误算为新增。

`publication_type` 可为 original_research、research_article、review、systematic_review、scoping_review、meta_analysis、methods_article、conference_paper；会议论文须为完整文章。`study_design.category` 可为 experimental、observational、computational、theoretical、evidence_synthesis、other、unverified；真实核实后将 verified 设为 true，并填写设计依据 basis 和原文位置 locator。分类未知保持 false；实验性分类必须与原创文章类型相符。

第6步对照最终引用更新记录并运行：

```bash
python "<skill_dir>/scripts/reference_composition.py" "<task_dir>/reference-composition.json"
```

脚本合并确定的重复文章，再按所选范围统计；同题名但强标识冲突须先核实。experimental75模式要求 `4 × 实验文章数 >= 3 × 全部有效文章数`；其他模式检查记录的target_designs中至少有一篇已核验原创文章，并由宿主核对承重问题覆盖，不设置实验比例。新任务须在manifest填写reference_composition_policy；缺该字段的旧manifest仅按历史75%合同读取。experimental75模式不按四舍五入后的显示比例放行。无新增引用返回 `NOT_APPLICABLE`，不是100%。脚本只检查所登记身份、设计与计数，不代替宿主读源文或核对最终稿。比例或文献记录变化后重新执行，摘要和正文的信息价值仍由实际回读检查。
