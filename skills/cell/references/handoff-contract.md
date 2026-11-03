# 跨 Skill 最小交接合同

本合同只保存跨阶段继续工作必需的信息，不复制成员 Skill 的业务规则。简单任务可用 Markdown 或现有 manifest 表达；需要机器处理时可使用下列字段。未知值如实写 `unknown` 或 `null`，不得为让流程继续而补造。

## 必需字段

| 字段 | 含义 |
| --- | --- |
| `deliverable_kind` | `original_research`、`evidence_synthesis` 或 `existing_artifact`。 |
| `action_mode` | `create`、`revise`、`assess` 或 `propose`。 |
| `authorized_goal` | 用户已明确授权的目标、阶段范围和排除项；保留原意，不扩大为上传、付费或投稿授权。 |
| `current_artifact` | 当前成果路径、版本、SHA-256 和生成/检查状态；没有成果时为 `null`。 |
| `selected_question` | 当前中心问题；尚未确定时写明状态和下一项收敛动作。 |
| `contribution_status` | `confirmed`、`provisional`、`conditional`、`not_assessed` 或 `rejected`，并说明判断对象。 |
| `next_skill` | 下一成员 Skill；只提方案或流程结束时为 `null`。 |
| `open_items` | 每项未决事实及其影响、下一动作、当前允许动作和降格方案。 |
| `skill_snapshot` | 实际读取的 Skill 名称、版本和 `SKILL.md` SHA-256；历史版本不可得时记 `unknown`。 |

`open_items[]` 至少包含：

```json
{
  "issue": "尚未完成与最接近综述的实质比较",
  "status": "open",
  "affects": "不能声称整合框架本身为首次提出",
  "next_action": "阅读最接近综述中对应章节并比较其实际判断",
  "allowed_now": "定向检索、试提取和有边界的综合初稿",
  "fallback": "将贡献降为已证明有后果的批判性重评",
  "owner": "cell-review"
}
```

## 状态传递规则

1. `conditional` 限制依赖该问题的主张强度，不自动阻断整个下游阶段。下游先标出受影响主张，再决定补证、降格或改题。
2. `rejected` 只否定已说明的候选或主张，不自动否定同一方向的其他问题。
3. 下游新增证据改变中心问题、贡献或边界时，更新版本、哈希和相应 `open_items`；旧的“查新通过”或自查结果不得沿用。
4. 每项未决问题结束时标为 `resolved`、`bounded` 或 `redirected`，并记录依据。文件已生成、脚本返回零或阶段编号推进不能代替状态判断。
5. 用户已授权的全流程可以继续到下一成员；新产物目标、收费动作、外部发布或投稿仍需独立授权。

## 交接检查

- 下一成员能看出用户究竟要创建、修改、评价还是只要方案。
- 中心问题和贡献状态没有在交接中被增强。
- 每个开放问题都说明影响哪条主张，而不是只写“需更多研究”。
- 当前可做动作与交付强度分开：可开始检索不等于可以交付强新颖性结论。
- 用户已经确认的语言、篇数、期刊、文件和排除项不重复询问。
