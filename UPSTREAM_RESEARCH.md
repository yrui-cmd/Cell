# 开源上游调研与吸纳记录

本文件记录维护者如何筛选外部 Skill 项目。Star 只用于发现候选，不代表内容正确；正式吸纳还要检查许可证、来源可追溯性、与 Cell 的适配程度和可测试性。Star 数为 2026-09-28 的 GitHub API 近似快照，会随时间变化。

| 项目 | 当时 Star（约） | 许可证判断 | Cell 处理 |
| --- | ---: | --- | --- |
| [obra/superpowers](https://github.com/obra/superpowers) | 292,600 | MIT | 借鉴“先取得新鲜验证证据再声明完成”和 Skill 行为测试思路；不复制文本。 |
| [anthropics/skills](https://github.com/anthropics/skills) | 178,900 | 混合；部分文档类 Skill 为 source-available | 仅作为结构与生态参考；未把非开源内容并入 Cell。 |
| [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | 47,000 | MIT | 第一批吸收实验设计检查维度，并以 Cell 自有数据契约、中文流程和测试重新实现。调研提交：`065b734670d7d990627dbc06a05b5a99be33f1f1`。 |
| [sickn33/agentic-awesome-skills](https://github.com/sickn33/agentic-awesome-skills) | 47,100 | 聚合仓，内容涉及多个上游许可证 | 只用于发现候选，不直接复制聚合内容。 |
| [vercel-labs/skills](https://github.com/vercel-labs/skills) | 32,700 | MIT | 保留为安装、发现与分发体验的后续参考。 |
| [openai/plugins](https://github.com/openai/plugins) | 7,200 | 各插件可能不同，部分为专有许可 | 仅参考公开设计，不复制专有插件内容。 |

## 第一批已落地：cell-plan 研究设计审查

来源启发是 K-Dense 科研 Skill 中对随机化、区组、实验单位和伪重复的系统关注。Cell 没有复制其说明或代码，而是针对现有 `plan_state.json` 新增 `design_review` 契约、正式交付门槛、中文参考说明和本地回归测试。

验收重点：非实验项目必须明确说明不适用；实验或比较性项目必须关联实际任务，记录实验/观测/分析单位、分配方式、随机化记录或非随机依据、区组与混杂、盲法、生物与技术重复、批次顺序、样本量依据、主要结局及排除/停止规则。结构检查不冒充科学有效性判断。

## 第二批已落地：cell-review DOI 注册元数据探测

来源启发是 K-Dense 引文管理 Skill 的 Crossref/DataCite 双源核验方式。Cell 重新实现为仅使用 Python 标准库的只读脚本，并增加严格三态语义：`verified`、`not_found`、`unavailable`。网络失败、限流和无效响应绝不折算为成功；注册记录核对也不会冒充论文内容或撤稿/更正状态核验。所有测试使用合成 HTTP 响应，不依赖外网。

## 第三批已落地：cell-data-figure 可访问性与字体核验

来源启发是 K-Dense 科研可视化 Skill 对调色板、色觉可访问性和字体嵌入的检查维度。Cell 新增只读调色板诊断，报告背景对比及色觉缺陷模拟下的颜色距离，但明确禁止固定阈值自动放行；最终图还必须用标签、点形或线型提供冗余编码。PDF 审核会列出实际字体对象，并要求宿主在目标查看器核实文字搜索/复制和替换情况，不把对象存在误报为已正确嵌入。

## 第四批已落地：cell-brainstorm 关键假设闭环

K-Dense 科研头脑风暴 Skill 强调 idea、assumption、prediction、evidence 与 decision 的边界以及可追溯决策日志。Cell 原有 v2 流程已经覆盖这些主体，本轮只修补一个确定性缺口：`essential_assumption_ids` 现在必须逐项对应候选实际 `assumptions[].statement`，重复或脱离账本的“共同前提”会被拒绝，避免最终共同风险由临时标签构造。

## 第五批已落地：cell-submission 规则—文件追溯

来源启发是 K-Dense venue-templates 的强制时效规则：精确锁定 venue、文章类型和阶段，打开官方来源并记录核验日期，且不把通用脚手架当官方模板。Cell 将其改造成 manifest version 2：每条规则记录来源种类、定位、访问日期、适用文章类型/阶段、强制程度、解释和目标文件；每个期刊触发的交付文件必须通过 `rule_ids` 回链。脚本不设置通用“几天后过期”，但会拒绝未来日期、范围错配、未解决规则和无规则依据的文件。
