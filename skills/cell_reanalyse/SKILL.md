---
name: cell_reanalyse
description: 从一篇文献的方法与结果建立私有复分析项目，先用 Word 逐句核对，再查证方法和 SCI 图表，以逐句确认或自动模式跑数并写稿。
---

# 文献复分析

每次处理一篇文献，每个项目独立建库。只把研究文件视为分析材料。用户提供方法和结果即可开始制表，真实数据在跑数时才需要。恢复已有项目时先读对应表、数据库和运行状态。

## 首份交付

先在项目的「方法数据库/方法与结果对应表.docx」生成可编辑 Word。按结果部分的原始章节和段落排版，每段一张表，跨页重复表头。下面是空白模板，每句填一行。

| 编号 | 方法与分析 | 对应结果 | 理想结果与判读标准 |
|---|---|---|---|
|  |  |  |  |

按文意分句，保留小数、缩写、图号和并列分析。编号从 P01-S01 起，已有编号保持稳定，另存显示顺序。第二列列全本句对应的方法及原文位置，共用方法可对应多句。第三列只填参考文献报告的发现。第四列只填有依据的预期、阈值和判断条件。缺失处写“原文未报告”。

交付 Word 后停在这里，等用户明确确认。接受 Word 修改或按编号反馈，回读最终版并核对段句。把确认时间及有序段标题、四列单元格文本的 SHA-256 留在私库；只有内容改变才重新确认。确认前不发搜索请求、不补外部参数、不开始计算。运行模式不能跳过这个确认。

## 证据与数据库

检索仅使用通用方法名、图表类型或已公开的文献标识。原句、数值、文件名、数据、可识别课题的组合留在项目。检索会暴露项目时，改用本地已发表材料或标明证据缺口。不得把项目材料装入技能目录、公开仓库或外部分析服务。用户明确指定远程计算时，仅在指定位置处理获准的数据。

确认后创建「方法数据库/方法数据库.sqlite」。按下面的 SQL 建表，每次连接启用外键。spec、manifest、measured、detail 用 UTF-8 JSON；路径使用项目相对路径。每次变更执行方案时保存版本快照及内容摘要，历史 run 必须能找回所用版本。project 保存确认记录、库版本及运行模式。

```sql
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS project(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sentence(id TEXT PRIMARY KEY, pos INTEGER UNIQUE NOT NULL, section TEXT, locator TEXT, method_text TEXT, reference_result TEXT, criterion TEXT);
CREATE TABLE IF NOT EXISTS dependency(child TEXT REFERENCES sentence, parent TEXT REFERENCES sentence, PRIMARY KEY(child,parent), CHECK(child<>parent));
CREATE TABLE IF NOT EXISTS source(id TEXT PRIMARY KEY, citation TEXT, doi_pmid TEXT, url TEXT, version TEXT, indexing TEXT);
CREATE TABLE IF NOT EXISTS search(id INTEGER PRIMARY KEY, engine TEXT, day TEXT, query TEXT, scope TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS method(id TEXT PRIMARY KEY, spec TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sentence_method(sid TEXT REFERENCES sentence, mid TEXT REFERENCES method, PRIMARY KEY(sid,mid));
CREATE TABLE IF NOT EXISTS format(id TEXT PRIMARY KEY, kind TEXT CHECK(kind IN ('figure','table')), spec TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sentence_format(sid TEXT REFERENCES sentence, fid TEXT REFERENCES format, PRIMARY KEY(sid,fid));
CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY, mid TEXT REFERENCES method, fid TEXT REFERENCES format, src TEXT NOT NULL REFERENCES source, locator TEXT NOT NULL, verified INTEGER NOT NULL CHECK(verified IN (0,1)), CHECK((mid IS NULL)<>(fid IS NULL)));
CREATE TABLE IF NOT EXISTS run(id TEXT PRIMARY KEY, sid TEXT NOT NULL REFERENCES sentence, db_rev TEXT NOT NULL, manifest TEXT NOT NULL, state TEXT NOT NULL, measured TEXT, approved INTEGER NOT NULL DEFAULT 0, current INTEGER NOT NULL DEFAULT 0, CHECK(current=0 OR state='ok'));
CREATE UNIQUE INDEX IF NOT EXISTS current_per_sentence ON run(sid) WHERE current=1;
CREATE TABLE IF NOT EXISTS product(run_id TEXT REFERENCES run, fid TEXT REFERENCES format, status TEXT NOT NULL, detail TEXT NOT NULL, PRIMARY KEY(run_id,fid));
```

- sentence 存参考叙述与原文位置。method.spec 存输入、步骤、软件版本和逐项参数。每个参数写值、单位、适用条件及来源类别（原文、实现默认、本次选择），引用 source.id 和具体定位。关键参数缺失且无法作出有据选择时，将相关句标为阻塞。
- 优先检索原始方法论文、高水平期刊中的实际应用和补充材料，再核对作者仓库或官方实现。记录完整书目、DOI 或 PMID、定位及仓库版本或提交号。高影响力和代码人气仅作筛选依据。引用前核对原文；期刊收录状态记录核查来源、适用年份和未核实项。
- 每句检查正文及补充图表，记录检索平台、日期、查询式、范围、筛选结果及无法访问的材料。对纳入文献提取全部适用形式，按图、表分别登记。图记面板、编码、坐标尺度、分组、统计标注、图例及输出规格；表记行列、单位、统计量、精度和脚注。格式带必需数据条件。用 evidence 保留每个实例的文献与图号、表号或补充编号。同样式多来源合并登记，实质不同的格式分别保留。不得把检索覆盖范围写成全体 SCI 文献。
- 导出「方法数据库/方法与图表索引.xlsx」，按句列出方法、参数出处、图表规格与来源、检索范围、缺项。人可按句号追查每一项。候选格式可以登记；进入正式出图集合须有已核实的 SCI 图表实例。

## 执行、确认与恢复

选择用户指定的逐句或自动模式；尚未选择时，在有数据且准备执行时询问一次。两种模式共用同一方法版本和执行路径。按原文顺序逐句处理，先核对输入、单位、分组、依赖和已登记参数。记录数据指纹、代码与环境版本、随机种子（适用时）、上游 run_id、参数和方法库快照。拒绝循环依赖，指出相关句号。

每次尝试分配唯一 run_id。实测值、样本量、统计量和适用的不确定性写入 run.measured。逐一核对该句在库中已核实的格式：适用的全部生成，每种 product 记录文件路径、摘要和图注；不适用的记录缺少的变量或设计条件。执行错误单列为失败；已判适用的格式若生成失败，该句不能标记完成。无已核实格式的句子可保存实测数值，明确记录缺口，不临时创造图表。

- 逐句模式：本句完成后给出实测摘要、所有产物及未生成项，等待明确确认。批准绑定 run_id。中断后先恢复当时的待确认句；未确认不能开始下一句。
- 自动模式：关键输入或参数缺失就记录阻塞原因，继续运行与它独立的句子。补齐后只补跑受阻和受影响的步骤。
- 文件按运行编号暂存并核验，全部写完才在 SQLite 事务内发布当前有效 run。重跑前撤销该句和依赖它的全部下游 current 标志与旧批准，同时将旧总稿标为过期。独立步骤继续有效。恢复时核对输入、代码、方案、依赖和产物摘要。崩溃残留归入垃圾文件夹；重新导出派生清单，不把半次运行发布为成功。项目结果按单一写入者运行。

## 文件与最终稿

每段一个「结果/P01_第1段/」，每句一个「S01_第1句/」，其下按 run_id 保存实测值、图表和说明。脚本及参数放「结果/代码/段号/句号/run_id/」。临时文件、失败运行及废弃中间产物放「结果/垃圾文件/」，保留历史追溯所需文件。原始输入不移入垃圾目录。

导出「结果/运行清单.xlsx」，包括每句状态、有效 run_id、库版本、实际产物、未生成原因、代码位置及待确认项。每次恢复或重跑后刷新。全部完成后按原文章节和段落顺序写「结果/方法与结果.docx」。方法部分从有效运行的记录还原实际参数、软件和引用；结果部分仅使用当前有效 run.measured 和对应 product，按句核对方向、数值、单位、分母和图表编号。无显著性或方向相反均照实报告。有阻塞、失败或待确认时只出标有“草稿”的文件，列明缺项，旧终稿移入历史归档。

## 虚构验收样例

用虚构参考句“乙组均值高于甲组”，输入甲组 8、10，乙组 3、5。测试库登记散点图、分组摘要表、配对连线图；前两种适用，第三种缺配对标识。测试来源明确标为夹具，不进入真实资料库。在两种模式中先验证未确认 Word 会暂停。确认后应计算乙减甲为 −5，交付两种适用形式并记录第三种缺项。另设依赖句和独立段，检查逐句确认、自动续跑、上游重算后的有效运行与最终稿引用。