# 英文学术文本自然化流程

本流程减少模型化、模板化和宣传式英文，同时保留学术写作所需的中性、限定和专业结构。目标是让论文更像作者基于真实研究作出的表达，不是预测文本由谁撰写，也不是绕过 AI 检测或规避应有披露。

## 先建立保护清单

普通润色默认锁定以下内容：数值、正负号、范围、单位、样本量、P 值和区间；公式、符号、变量与代码；引文键、作者年份、DOI 和 URL；Figure/Table/Section/Appendix 编号；直接引语；数据集、材料、基因、蛋白、模型和方法的正式名称。

同时建立语义保护项：否定关系、比较对象、因果方向、时间顺序、适用人群、条件、例外、不确定性和作者明确立场。机械检查只能覆盖前一部分；后一部分必须逐句对照原文。

## 第一遍：从全文结构找模板痕迹

通读后再编辑，不从第一个命中词开始逐项替换。优先处理会明显损害可信度的模式：

1. **聊天残留**：`Great question`、`I hope this helps`、`Would you like me to` 等不属于论文的包装。
2. **铺垫代替陈述**：`In recent years`、`With the rapid development of`、`It is worth noting that` 后面才出现真正观点。
3. **虚构对立**：`not only X but Y`、`This is not X; it is Y` 的 X 并非读者真实持有的解释。真正需要纠正的对立必须保留。
4. **戏剧性收尾**：一行短句重复前文，或用 `This distinction matters`、`The implications are profound` 要求读者重视，却没有新增事实。
5. **意义膨胀**：`paves the way`、`opens new avenues`、`revolutionize`、`paradigm shift`、`of paramount importance`。把意义改成研究实际解决的具体缺口或约束。
6. **空泛贡献清单**：`a novel method, extensive experiments, and strong results`。每项贡献应指向真实方法、数据、幅度或边界。
7. **借来的权威**：`experts argue`、`studies have shown`、`the literature suggests` 没有可定位来源。已有引用则说明它支持什么；没有来源时不得编造。
8. **浅层 -ing 尾句**：在事实后追加 `highlighting`、`underscoring`、`showcasing` 来制造解释。只有来源确实支持该解释时保留。
9. **文档自我叙述**：反复写 `This section discusses`、`The table below presents`，却不直接陈述研究对象。必要的路线图和交叉引用不在此列。
10. **通用结尾**：泛泛的 future work、挑战与机遇或宏大意义段。用本研究真实限制和可检验的下一步替代；没有具体内容时删除。

## 第二遍：恢复作者节奏而不制造新的人设

检查段落和句群，而不是单个词：

- 连续句子是否以同一结构开头；所有段落是否机械地等长；句子是否长期保持同一长度和从句数量。
- 三项并列是否确有三项独立信息，还是为完整感凑成 rule of three。
- `Moreover/Furthermore/Additionally/In particular` 是否连续承担本应由内容表达的逻辑。
- 是否为避免术语重复而 synonym cycling，导致同一实体换名。
- 是否堆叠限定词，如 `could potentially possibly`；只保留证据需要的限定。
- 是否反复用 `serves as/functions as/stands as` 避开简单准确的 `is/has`。
- 是否用大量破折号、冒号、括号或短句碎片形成统一节拍。标点本身不是 AI 证据；按作者样本和目标期刊处理。

通过拆分、合并、删除冗余子句和恢复清楚主语来改变偶然的机械节奏。不得为了“burstiness”加入无意义短句、故意语病、口语或不规则标点，也不使用固定平均句长、句长标准差或标点配额。

## 学术写作不能被误删的内容

- Methods 中施事者不重要时，被动语态自然且常常更准确。
- `we` 是标准学术主体，不需要为显得客观全部移除。
- `suggests`、`may indicate`、`is consistent with` 等有证据依据的 hedging 必须保留。
- `robust`、`significant`、`association` 等词在统计或专业含义明确时不是禁词。
- 三个真实类别、平行研究目标、标准章节结构和必要路线图不因形式整齐而自动重写。
- 作者样本中稳定出现的破折号、括号、句长与过渡习惯属于声音证据；除非妨碍理解，按相近频率保留。

禁词表只能作为搜索入口。单个词、单个被动句、一个三项列表或一处破折号都不能独立证明问题；结合上下文、密度、功能和作者样本判断。

## 作者声音校准

有条件时读取作者本人已经发表或确认的 2–3 段同类英文，记录：句长变化、常用主语、主动/被动分布、限定词位置、段落开头、标点、术语和引用整合方式。只模仿反复出现且不影响准确性的特征。

不能给作者添加原文没有的经历、情绪、第一人称反应、幽默、观点或“反常识立场”。学术文本的作者声音通常表现为选择何种证据、如何限定判断和怎样组织解释，不等于口语化人格。

## 有界的两遍编辑

第一遍修改结构性模板痕迹和无信息表达；第二遍只修复仍然明显的问题、恢复作者节奏并做保真检查。没有合理问题时保持原文不变，不为了证明执行过流程继续改写。两遍后仍有需要作者事实才能解决的问题，保留并报告，不循环生成更多版本。

对完整文件或较长章节可运行非裁决性检查：

```bash
python scripts/academic_prose_lint.py manuscript.txt
python scripts/check_manuscript_preservation.py before.txt after.txt
```

前者只定位常见模板表达和模式簇，不判断作者身份；后者比较部分可机械保护的 token，不证明语义完全一致。最终仍须检查否定、因果、限定、归因和研究范围。

## 完成判断

最终稿应直接陈述研究事实和判断，具体意义来自数据或文献，不靠强调词；句式有内容驱动的变化，不呈现统一模板；作者原有的术语、限定和有效粗糙度仍在；所有修改都能回到原文信息或作者明确更正。

开源借鉴范围与许可证见 [开源来源记录](open-source-sources.md)。
