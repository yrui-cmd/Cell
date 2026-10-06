# 开源来源记录

以下 Star 为 2026-09-28 通过 GitHub API 查询的快照，会随时间变化。仓库内容只作为参考资料；本 Skill 根据英文学术论文场景重新编写规则，没有复制上游检测器实现或完整规则表。

| 仓库 | Star 快照 | 许可证 | 吸收内容 | 未采用内容 |
| --- | ---: | --- | --- | --- |
| [blader/humanizer](https://github.com/blader/humanizer) | 52,755 | MIT | 先通读再改、staging/rhythm/inflation/chat residue 分类、保留事实、用作者样本校准声音 | 通用博客/营销口吻；破折号一律删除；先交草稿再交最终稿 |
| [conorbronsdon/avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing) | 4,763 | MIT | 检测不等于修改授权、保护区域、无问题时不改、两遍上限、前后版本保真检查、模式是信号而非作者身份结论 | 面向社交和营销的 profile、AI 分数门槛、庞大词表直接作为禁词表 |
| [Nanako0129/sepia](https://github.com/Nanako0129/sepia) | 2,906 | MIT | 关注同一文本内的句长变化，而不设平均句长目标；不把标点和段落长度当作稳定作者身份信号 | 小说叙事和平台文案规则；研究中未证实的固定节奏阈值 |
| [AIScientists-Dev/academic-humanizer](https://github.com/AIScientists-Dev/academic-humanizer) | 1,734 | 仓库内 MIT | 学术例外、claim-evidence discipline、作者与 venue 匹配、保留必要 hedging/被动语态/`we` | 基金申请分支；绝对删除 em dash；未经作者核实就把模糊结果改成具体数值 |
| [hanlulong/econ-writing-skill](https://github.com/hanlulong/econ-writing-skill) | 628 | MIT | 用简单具体的句子陈述精确主张，避免空泛元话语 | 固定句长目标、普遍禁用词和标点规则 |

另核对了 18,696 Star 的 [op7418/Humanizer-zh](https://github.com/op7418/Humanizer-zh)。它主要是 `blader/humanizer` 的中文化版本，而本 Skill 处理英文论文，因此不重复引入同一套规则。

## 适配原则

1. Star 只用于发现候选，不代替质量与许可证判断。
2. 通用 Humanizer 的规则必须经过学术例外过滤；论文不应被改成博客、营销文案或口语随笔。
3. 不以商业或开源 AI 检测分数作为交付门槛。模式检查用于提高可读性和作者声音，不能证明文本由 AI 或人类撰写。
4. 不为了通过模式检查制造错误、随机扰动、虚假个人经历或不自然的同义替换。
5. 期刊或机构要求披露 AI 使用时照实遵守；润色流程不得用于隐瞒需要披露的事实。
