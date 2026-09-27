# 运行接口

本包是宿主驱动Skill。实际检索、原文阅读和单模型调用由当前宿主执行；脚本不联网、不生成科研事实、不自动进行实验，不另装模型。

## 进度
在RUN父目录已存在且将创建一个新运行目录时：
```bash
python scripts/session.py init --run-dir RUN --model-id ACTUAL_MODEL_ID --mode live --topic "研究方向"
python scripts/session.py progress --state RUN/session.json --step 1 --model-id ACTUAL_MODEL_ID
```
init成功不打印内容。首次进入第N步时progress只打印“第N步”；同一步或返工不重报，跳步和中途换模型报错。主持宿主只将这一行作为自己的进度消息；不要既打印脚本结果又额外重复同一消息。步骤进入记录不证明该步已经完成。
自动工具卡片、系统安全/权限提示无法由Skill隐藏，必要授权不能被静默跳过。

## 证据与产物
RUN使用独立新目录，文献内容遵守来源权限；秘密材料不随最终报告发布。阶段文件可以分开或同阶段合并。
```bash
python scripts/session.py record --state RUN/session.json --stage S05 --artifact RUN/evidence/evidence.json --model-id ACTUAL_MODEL_ID
```
记录只校验实际文件、哈希与模型声明，不保证科学语义。内部同一步最多两轮修复。源文件、审计和用户材料不被结果文件覆盖；回放保留旧证据版本。

## 输出
```bash
python scripts/quality_gate.py --input RUN/audit_bundle.json --output RUN/results/final_report.json
python scripts/weight_sensitivity.py --input RUN/audit_bundle.json --output RUN/results/weight_sensitivity.json
python scripts/render_report.py --input RUN/results/final_report.json --sensitivity RUN/results/weight_sensitivity.json --output RUN/results/final_report.md
python scripts/freeze_snapshot.py --directory RUN/evidence --output RUN/snapshot_manifest.json
```
以上默认成功静默；保留--quiet兼容参数。仅调试时用--verbose，调试文本写本地日志，不发送给用户。错误写stderr并非被吞掉，宿主应局部修复或诚实输出受限结果。
JSON保存评分和内部审计；Markdown为导师论证稿，只输出五题、依据、研究内容、方案、限制和文献。敏感性计算核对报告哈希，但结果默认不在正文展示。

## 合成演示
```bash
python scripts/quality_gate.py --input examples/synthetic_audit_bundle_v2.json --output RUN/results/demo.json
python scripts/render_report.py --input RUN/results/demo.json --output RUN/results/demo.md
```
示例全部明确标SYNTHETIC，仅测试结构。不要将example.invalid、TEST标识或虚构前提搬进真实报告。

## 降级与授权
没有联网时只能按已有证据探索，并在正文一句说明未完成当日查新；没有脚本时由宿主按合同核对，不谎报测试成功。资源未知继续形成有明确条件的候选；根本没有研究主题才问一句。不能自动购买、申请审批、访问未授权数据或执行实验。
