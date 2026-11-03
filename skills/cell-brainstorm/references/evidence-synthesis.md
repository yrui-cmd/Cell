# 证据综合选题合同

本合同适用于综述、证据地图和其他以现有文献综合为主要产物的选题。它与 `original_research` 正交：主题可以讨论机制或因果，但交付仍是证据综合，不以先完成新实验为前提。

## 两类比较对象

每个候选分别建立：

- `nearest_reviews`：最接近的综述或综合，用于判断别人已经如何组织问题、得出什么结论和留下什么边界。若只读摘要，不能据此评价正文结构、完整证据范围或未讨论内容。
- `primary_evidence`：能够支撑、挑战或限制中心判断的原始研究。综述可导航，但不能代替承重原始证据的内容核查。

一次检索需要分开记录 `request_succeeded`、`screening_sufficient` 与 `novelty_complete`。工具成功返回不代表筛选足够，更不代表贡献比较完成。

## `synthesis_delta`

每题必须回答六项：

1. `prior_synthesis`：最接近综述已经给出的判断或组织方式。
2. `changed_judgment`：本题将改变、限定或重新连接的具体判断。
3. `synthesis_operation`：通过何种比较实现，例如按对象、时间、测量、条件或证据等级分层。
4. `visible_artifact`：读者能看到并使用的产物，如判别框架、证据矩阵、边界图或决策树；不能只写“更全面”。
5. `boundaries`：该综合适用和不适用的范围。
6. `negating_evidence`：什么已存在或新发现的证据会使该贡献不再成立。

只有“文献较少”“尚无统一结论”“首次整合”而没有实质比较，不构成合格差量。

## P0、P1、P2

- **P0 试综合**：用代表性最接近综述和少量承重原始研究，试验分类、提取字段、可比性和综合判断是否能成立。
- **P1 完整综合**：完成问题覆盖、反证路径、必要全文核查和跨研究比较，形成能够回答中心问题的正文或框架。
- **P2 可选扩展**：更新检索、扩大领域、正式定量合并，或建议未来原始研究。P2 不得成为 P1 能否完成的默认前提。

## 候选层级与条件性

用 `parallel`、`subtopic`、`overlap` 标记每题相对主候选的关系。五个位置可包含有价值的子题，但报告必须显式说明层级；不得仅靠换标题把一个主线的章节冒充五个平行构想。实质重叠候选合并或降为备选角度。

未决事项逐项写 `affects`、`allowed_now` 和 `fallback`。例如最接近综述仅能读取摘要，只限制结构比较和强新颖性声明；它不自动禁止继续原始证据提取或有边界的试综合。

## 本地门槛

新建 `synthesis_audit.json` 可从 `templates/synthesis-audit.json` 复制。运行：

```bash
python scripts/synthesis_gate.py RUN/synthesis_audit.json
```

`SYNTHESIS_CONTRACT_PASSED` 只说明实际候选及空位满足适用的结构字段、来源角色和边界记录，不证明检索穷尽、科学判断正确或期刊可接收。条件性候选可以通过结构门槛，但其限制必须保留到交接和最终报告。

## synthesis-1.1：可执行交付合同

新任务使用synthesis-1.1。`candidates`允许0—5个输入项；渲染器输出五个展示位置，缺额自动留空。也可显式记录`{"id":"VACANT-5","status":"vacant","reason":"可靠候选不足"}`，不为占位构造题目和论文。fail候选保留审计但不作为推荐题显示。

根字段增加`brief.research_content`与`sources`。sources每项含id、title、kind（review/original_research）、url，已核实时可记录article_id、doi。来源身份按source_id及已记录的article_id/DOI共同核对；最近综述与承重原始研究不得复用同一文章身份。两角色记录仍须包含实际读取access与原有比较字段。pass需角色证据齐全、三个search_status均为true且无open_items；未完成检索只能conditional并写清具体影响及可继续动作，或fail/vacant。

每个pass/conditional候选含`report_sections`四段：basis/question/plan/limitations，各为`{"text":"实际已核对的单段文字","source_ids":["实际来源ID"]}`。引文只能属于该候选登记的角色来源，basis应引用实际最近综述（若尚无综述则如实保留资料不足）。这些字段用于排版，不能引入新事实。conditional的open_items与子题/重叠关系会进入最终文稿。

live模式另记带时区的report_created_at和final_checked_at；最终复核需在成稿前24小时内才能标pass。未复核用null，候选保留conditional和具体open_items。offline/replay不声称当日查新。模板初始化仍是不完整记录，不是可直接交付的合成范文。

```bash
python scripts/synthesis_gate.py RUN/synthesis_audit.json
python scripts/render_report.py --input RUN/synthesis_audit.json --output RUN/final_report.md
```

原始研究2.0和旧回放1.1不变；旧synthesis-1.0可做结构回放，不能缺少文献登记而直接排版。结构通过不证明来源真实或科学判断正确。
