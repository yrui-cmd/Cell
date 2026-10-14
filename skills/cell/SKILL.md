---
name: cell
description: Cell 系列科研工作总入口。根据用户的科研任务，在科研选题、研究计划、顶刊综述、论文模拟审稿、论文 PDF 版式保留翻译、英文论文深度润色、审稿回复、投稿整理、Python/MATLAB 科研可视化代码、数据图复现、科研图重建、两阶段期刊图生成和 PowerPoint 原生对象编辑成员之间选择一个最匹配的 Skill，并直接执行对应流程。用户说“Cell 系列”“用 Cell 做”但未指定成员，或需要判断应使用哪个 Cell Skill 时使用。
metadata:
  version: "1.5.0"
  language: "zh-CN"
---

# Cell

本 Skill 只负责准确分流，不复制、缩短或改写成员 Skill 的业务规则。确定成员后，读取该成员的 `SKILL.md` 并完整执行。用户明确点名成员时直接使用该成员；已有输入不重复索要。

## 路由表

| 用户目标 | 成员 Skill |
| --- | --- |
| 从研究方向形成五个证据驱动的原始研究或综述选题 | `cell-brainstorm` |
| 根据题目、投稿目标和实际条件安排研究路线 | `cell-plan` |
| 按领域顶刊标准撰写完整 Word 文献综述 | `cell-review` |
| 以审稿人视角首次评审论文，或按原意见复审修订稿 | `cell-reviewer` |
| 将英文论文 PDF 指定页或全文翻译为保留版式的中文图片型 PDF | `cell-paper-translation` |
| 深度润色已有英文论文或综述稿，检查逻辑、证据强度与学术表达 | `cell-manuscript-editing` |
| 处理编辑和审稿意见并生成两阶段 Word 回复 | `cell-reviewer-response` |
| 把已完成论文整理为目标期刊投稿包 | `cell-submission` |
| 生成、重构或审核 Python/MATLAB 科研可视化代码 | `cell-visualization-code` |
| 用代码复现论文数据图，再替换为用户数据 | `cell-data-figure` |
| 把参考科研图重建为可编辑 PPT 或 Illustrator 图形 | `cell_su7` |
| 使用小描两阶段流程生成布局图与高级科研图 | `cell-cns-figure` |
| 快速编辑已打开 PowerPoint 中的原生对象 | `cell-ppt-edited` 插件 |

## 选择规则

1. 先同时判断 `deliverable_kind` 与 `action_mode`，再选择一个主成员。`deliverable_kind` 至少区分原始研究（`original_research`）、证据综合（`evidence_synthesis`）和已有成果（`existing_artifact`）；`action_mode` 至少区分新建（`create`）、修改（`revise`）、评价（`assess`）和只提方案（`propose`）。局部更新不得静默升级为从零重做；只有用户的目标确实横跨阶段时才按工作依赖依次调用多个成员。
2. 研究内容与可行性尚未定型时，先选题，再安排研究计划；已经有明确题目时直接进入研究计划。
3. 从零检索并写完整综述使用 `cell-review`；用户只给广方向但明确要求形成综述选题或完成综述时，先用 `cell-brainstorm` 的证据综合模式收敛中心问题与贡献，再进入 `cell-review`，不得把未来实验计划当成综述选题本身。对已有综述或实验性/原始研究稿件做模拟审稿、投稿前自审使用 `cell-reviewer`。把已发表或已有英文论文 PDF 翻译成保留版式的中文阅读版使用 `cell-paper-translation`；修改作者稿件的英文正文、逻辑或证据强度仍使用 `cell-manuscript-editing`，普通文字翻译和可编辑 Word 译稿不自动使用 PDF 翻译。正文定稿后需要投稿格式与材料时使用投稿整理；收到真实编辑或审稿意见后使用 `cell-reviewer-response`。翻译、写作、模拟审稿、润色、投稿整理和审稿回复不能互相代替。
4. `cell-visualization-code` 处理一般 Python/MATLAB 科研绘图代码规范、重构与验收；只有任务明确要求先复现参考论文图并通过门槛再换研究数据时才使用 `cell-data-figure`。`cell_su7` 处理参考图的可编辑重建；`cell-cns-figure` 根据研究文字生成期刊图；`cell-ppt-edited` 编辑现有 PPT 原生对象。
5. 成员要求余额确认、费用授权、软件环境或文件输入时，遵循成员自身规则。总入口不替用户确认收费，也不宣称未完成的安装、生成或交付已经成功。

用户明确点名成员时尊重选择；若输入与目标明显不匹配，说明具体冲突，只澄清会改变产物的部分，不静默换成员。跨阶段交接遵循 [最小交接合同](references/handoff-contract.md)，保留用户原始目标、已确认约束、当前成果路径与版本/哈希、中心问题与贡献状态，以及每项未决事实影响的主张、下一动作、当前允许范围和降格方案。下游不得把 `conditional` 自动解释成全部停工或已经解决：可以继续不依赖该问题的检索、试提纲和有边界初稿，只有依赖它的强结论受到限制。

用户已经明确授权的完整工作流可按依赖依次执行，不因成员切换重复索取相同输入或许可；未授权的新目标、付费服务、对外上传、公开发布和投稿不因上一步完成而自动获得授权。只要求方案时保持 `action_mode=propose`，不得据此修改 Skill 或执行方案。

## 完成

以成员 Skill 的完成条件为准。最终说明实际使用的成员，并链接真实产物；不把路由选择、程序通过、阶段编号或文件生成本身当作科学完成。跨阶段任务的本地记录保留实际读取的 Skill 版本和入口文件 SHA-256；没有历史快照时记为未知，不根据修改时间倒推旧规则。
