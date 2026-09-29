# 数据合同 v2.0

## 总体
schemas/audit-bundle.schema.json为机器合同，schema_version=2.0。以examples/synthetic_audit_bundle_v2.json了解字段，合成数据不得冒充真实来源或查新结果。旧1.1例子只用于回归和回放，不能绕过新任务的增强字段。
根字段：run、execution、brief、sources、constraints、candidates。candidates最多10（已进入深审），初始24以内的池与两轮种子另存RUN。

## 来源与记录
run保存实际as_of、report_created_at、final_checked_at、来源渠道、覆盖局限、日志引用和快照。时间戳含时区；截止日期不能以抓取时间代替发表时间。
execution只允许single_model_sequential、same_model_self_audit和independent_review=false；三个模型标识一致。same_context不称盲审。状态声明不证明平台实际调用。
sources保留标题、实际URL、study_id、首次公开/版本日期、访问范围、完整性、实际内容哈希等。authors/publication_year/venue/doi为可选核验字段，无资料不编。元数据、实际读取和语义支持是不同核验。hypothesis可以没有直接支持，但known/inference必须有来源及定位。
constraints：confirmed/path_identified/assumed/unknown/unavailable，证据引用可为来源ID、实际用户确认记录或已存在文件定位，不能是“常识上能取得”。

## 候选
基础候选沿用1.1合同：question_key、最近工作、差量、claims、design、resources、N/V/F/T/E及八项检查。enhancement包含类型对应answerability、why_now、assumptions、reframing、analogies、revision、constraint_ladder、P0/P1/P2、prediction_matrix、minimum_validation、premortem、decision_uncertainties、essential_assumption_ids、三道科学门。
revision.last_novelty_checked_version必须与version一致才能确认当前创新判断；变更的旧记录留档。score是排序辅助，不是科研价值真值。`essential_assumption_ids` 中的每一项必须与本候选 `assumptions[].statement` 的稳定表述完全一致，且不得重复；这样共同风险一定能回到实际假设账本，不能临时造一个未登记标签。

## 最终四段（新增必填）
report_sections含basis/question/plan/limitations；每段为{text, source_ids}。text是已经核对的短学术段落，source_ids是该候选内部来源集合的子集。basis至少引用一个实际最近工作（若最近工作缺失，必须写资料不足）；方法涉及的外部事实也需来源。
四段不是新的证据或第二次自由发挥。写作后同模型逐句核对原字段与来源，再运行本地检查；句意是否得到支持仍不是程序可证明的。结构检查会拒绝未知引用和宣传式模板用语；报告限制按确定性检查结果追加保守说明，不能靠漂亮段落把未知变成通过。
report_sections不存在则2.0校验失败，避免回退为冗长旧表。渲染只有排版和引用编号，不裁切文字、不调用新模型、不加入新机制。

## 私有审计与简洁正文
内部资料保存完整；final_report.md仅正文四段与数字引文、参考文献。原始查询、locator、得分、判定细节、权限记录等在RUN，不在正文打印。必要资料或执行限制照实保留；生成方案不是申请执行许可。
