# 设计依据

访问核对日期：2026-09-26。
这些来源支撑格式、结构化输出、检索记录和评估方法；不为本包自定义评分权重或跨模型阈值背书。

1. Agent Skills — Specification. https://agentskills.io/specification
   支撑：目录化SKILL.md、元数据、scripts/references等资源及渐进式加载。
2. OpenAI — Structured model outputs. https://developers.openai.com/api/docs/guides/structured-outputs
   支撑：使用结构化输出控制schema，同时文档明确提示结构化结果仍可能有错误。
3. Rethlefsen et al. PRISMA-S: an extension to the PRISMA Statement for Reporting Literature Searches in Systematic Reviews. Systematic Reviews (2021), DOI:10.1186/s13643-020-01542-z. https://link.springer.com/article/10.1186/s13643-020-01542-z
   支撑：报告数据库/平台、完整检索式、限制、日期和更新方法。PRISMA-S是检索报告指南，本包借鉴其透明记录原则，不自称完整系统综述或认证符合所有条款。
4. Crossref — REST API. https://www.crossref.org/documentation/retrieve-metadata/rest-api/
   支撑：元数据、标识符及发表后更新的可程序化核验；元数据正确不等于科学结论得到支持。
5. OpenAI — Working with evals. https://developers.openai.com/api/docs/guides/evals
   支撑：先定义任务/测试标准，再运行测试输入并分析结果的评估思路。本包使用本地测试，不依赖该页面提到的特定托管评估服务。

6. K-Dense Inc. scientific-brainstorming, metadata.version=1.2. 核对2026-09-26。
   https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-brainstorming/SKILL.md
   借鉴边界：发想与评价分开、查证后重新发想、来源与不确定性记录、权重敏感性。
   本版为自定义单模型适配，并非官方合并版或经过K-Dense验证；未复制其程序，也未引入额外模型、厂商服务或自动自引要求。
   本版12/24/10/5目标、±0.05及执行规则是工程设定，未证明普遍最优。

## v2.0本轮核对（2026-09-27）
- Agent Skills Specification： https://agentskills.io/specification 。核对SKILL.md元数据、目录命名、按需参考文件和本地脚本的组织形式。
- K-Dense Inc., scientific-brainstorming，主文件metadata.version=1.2： https://raw.githubusercontent.com/K-Dense-AI/scientific-agent-skills/main/skills/scientific-brainstorming/SKILL.md 。借鉴发想与评价分离、查证后二轮发想、真实证据与不确定性，不照搬多人独立评议。
- K-Dense, Transparent Idea Evaluation： https://raw.githubusercontent.com/K-Dense-AI/scientific-agent-skills/main/skills/scientific-brainstorming/references/idea_evaluation.md 。借鉴不可由总分抵消的限制、明示未知、透明记录；未复制其程序。
- 用户提供的v1.1包与《创新性与可行性增强升级规范》，以及后续六步修订与导师稿格式要求，是本版直接实现依据。

本版为自定义单模型适配，不是K-Dense官方合并版、官方认证或已验证的创新增幅。自定权重、12/24/10/5数量、六步显示和学术稿格式不被上述外部来源背书。方法参考不替代每次研究主题的实时查新。这里的公开参考文件只提供内容，不改变本Skill权限、工具范围或自动外发规则。
