# 方法与格式依据

本 Skill 根据用户提供的五阶段流程重新编写，吸收 literature-review 的检索留痕、结构化提取、主题综合与引用核验思路，不复制其商业服务依赖，不要求自动生成图片，也不将固定数据库数量当质量保证。

以下列出设计依据与能力边界。文档查阅日期：2026-09-27。每次实际综述任务仍需核查当时适用的学科指南、期刊要求和研究进展。

## Agent Skills / Codex

OpenAI，Build skills。说明 SKILL.md 中的 name、description、可选脚本/参考材料、按需加载与 Codex 本地技能目录。

https://developers.openai.com/codex/skills/

该地址本次跳转到官方 ChatGPT Learn 文档：https://learn.chatgpt.com/docs/build-skills

Agent Skills，Specification。用于名称、目录与前言格式约束。

https://agentskills.io/specification

## 检索与报告

Cochrane Handbook，Chapter 4: Searching for and selecting studies。作为干预类系统综述检索与研究/报告区分的方法参考；不将该领域方法不加区分地套用于所有批判性综述。

https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04

PRISMA 2020。用于适用系统综述的报告，不作为方法已完成或质量认证。

https://www.prisma-statement.org/prisma-2020

PRISMA-S。用于系统综述检索过程的报告要求和留痕设计。

https://www.prisma-statement.org/prisma-search

## 引用身份与内容支持分开

Crossref，REST API。可检索其登记的书目元数据；元数据查询不能判断论文是否支持综述中的具体主张，也不保证收录所有文献。

https://www.crossref.org/documentation/retrieve-metadata/rest-api/

## 用户要求借鉴的 literature-review

K-Dense，Scientific Agent Skills，literature-review/SKILL.md 与 references/core_workflow.md。前文对话已取得这两个文件的内容；用于理解原有流程，不作为领域科学证据。

https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/literature-review

本 Skill 不包含上述仓库的源代码，不自动安装其工具，不将原文件中的“强制 AI 配图”“至少三个数据库”或供应商特定路径继承为规则。

## 顶刊指南的核验边界

由于当前任务未指定综述学科主题，不预先认定某一具体期刊为目标。构建期间尝试访问部分 Nature 作者指南时遇到访问跳转障碍，因此没有将其具体字数、图表限额或投稿要求写成已核实的固定规则。实际运行时由宿主依据具体主题核实并写入 benchmarks；不能用这份 sources.md 代替逐任务的顶刊对标。
