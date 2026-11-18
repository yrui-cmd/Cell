# 返修项目状态与一致性审计

本规范在开始/恢复返修、核验新增结果和第二阶段定稿时使用。它补充证据和版本控制，不替代逐条审稿回复流程。项目事实保存在本次内部工作区，不写回通用 Skill。

## 1. 当前状态与权威来源

先识别并实际打开与当前任务有关的材料：decision letter/审稿意见、当前修订稿、上一版已提交稿、已有回复信、数据、代码、配置、结果、图表、补充材料和期刊要求。对每类材料记录 artifact ID、真实路径、SHA-256、版本/日期（已知时）、用途和最后核对时间。

权威来源由内容、作者最新明确指示和版本链共同确定，不由文件名、修改时间、旧对话或历史摘要单独决定。把内容区分为：

- 已完成且有当前版本证据；
- 拟议但尚未落实；
- 已存在但尚未核实；
- 已被新决定或新文件取代。

来源变化后，重置受影响的核验标记并重读；不能只更新哈希或页码。作者最新明确指示与经核验事实优先，发生冲突时保留冲突并请求决定。

## 2. 项目记忆

单次、材料简单的任务可直接使用 `ledger.json`。跨会话、多文件或多轮返修时，在内部工作区维护 `PROJECT_MEMORY.md`，至少包含：

```markdown
# Project Memory

## Current state — YYYY-MM-DD
- Project / venue / manuscript ID / revision round / deadline:
- Authoritative review source:
- Authoritative current manuscript:
- Previous submitted manuscript:
- Completed / unresolved / blockers:

## Source of truth
| Material | Artifact ID and path | Status | Last verified |
|---|---|---|---|

## Reviewer tracker
| Comment | Core concern | Action | Evidence | Manuscript change | Status |
|---|---|---|---|---|---|

## Terminology and claim boundaries
- Fixed definitions, symbols, metrics and assumptions:
- Permitted claims / claims to avoid:

## Decisions
- Date / decision / reason / affected material / supersedes / remaining issue:

## Audit state
- Response / manuscript / cross-document / quantitative / final-render audit:
```

记忆只帮助恢复状态，不是科学证据。具体稿号、数字、参数、服务器状态、页码和审稿人处理进度只写项目记忆，不写入本通用参考文件。不得声称拥有当前会话无法访问的记忆。

## 3. 证据类型与追溯

所有用于关闭问题的证据先标记 `evidence_kind`：

- `manuscript_text`：当前稿、图、表或补充材料中的可定位内容；
- `quantitative_result`：实验、分析、仿真、统计或计算输出；
- `theoretical_result`：定理、命题、推导或形式化性质；
- `literature`：已发表研究、标准或官方原始资料；
- `administrative`：期刊说明、编辑要求、伦理/数据声明等。

共同要求是来源 artifact、具体 locator、该证据实际支持的命题；直接引文必须能在可读取来源中找到。

### 定量结果

`quantitative_result` 必须登记：

1. 数据/输入版本；
2. 方法、模型、代码或实现版本；
3. 实验/分析配置和关键参数；
4. 实际评价集合、样本/时间范围、比较对象；
5. 指标、分母、单位和统计量定义；
6. 失败、缺失、未完成、排除案例，或明确说明没有及其核对依据；
7. 求解/分析状态、终止条件或运行完成状态。

不得静默删除不利结果。区分最优、可行、次优、失败和未完成，区分生成场景和真实历史，区分平均表现与逐案例/逐路径可行性。目标值接近不等于可靠性接近，平均通过率不能替代逐案例结论。

### 理论结果

`theoretical_result` 必须登记数学对象、必要假设、结论类型和容差条件。明确结论是关于可行性、最优性、终止性、近似性还是恢复性；区分有限近似与原始问题、零容差与数值容差、继承/适配与独立贡献。标准过程本身不能包装成新理论贡献。

### 文献依据

`literature` 必须核对原论文全文、标准或官方原始资料；记录其模型/系统/时间尺度/变量/指标范围及它具体支持的句子。摘要、二手描述和不确定记忆不能支撑正式理论结论。文献原式、本项目公式和解释性推导分别标明。

## 4. 手稿与回复交叉审计

定稿前分别检查：

1. 每项审稿要求和拆分子问题均被回答；
2. 回复信内部没有相互矛盾的动作、数字、术语或位置；
3. 手稿各章节使用一致的模型定义、符号、单位、指标、样本范围和结论边界；
4. 回复准确描述当前手稿，`Revised manuscript text` 与当前稿逐字一致；
5. 数值、分母、单位、比较集合、失败/排除案例和运行状态在正文、图、表、补充材料与回复中一致；
6. 公式、图、表、文献和位置在最终渲染稿中真实存在；
7. clean/marked 两版在被要求时实质一致，差别仅为修订标记；
8. 最终 DOCX/PDF 及被要求的投稿系统合并预览正常显示；
9. 无占位符、内部提示、过时文字或未核实的完成声明。

发现矛盾时回到来源修正，不以改写检查字段放行。最终位置来自实际渲染文件，不根据源码行号或旧页码猜测。只有权威版本、手稿内部一致性、回复—手稿一致性和定量一致性均实际核对后，才将对应 `checks` 设为 true。
