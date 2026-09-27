# cell-plan｜研究计划安排助手

版本：1.1.0。给出题目、投稿目标和现有条件，由Skill完成20篇对标原始研究的全文阅读，直接确定一条研究主线，安排具体任务、顺序、方法与对照、前4周工作及后续阶段。

## 替换旧版

将本包中的整个 `cell-plan` 文件夹替换原技能文件夹；不要只替换SKILL.md。主文件、模板、参考细则和检查程序必须同时更新。解压后避免同名文件夹重复嵌套。

## 调用

```text
$cell-plan
研究题目：……
目标期刊或分数区间：……
已有数据与结果：……
能做的分析或实验：……
预算与完成时间：……
请直接安排研究路线、具体任务、先后顺序和时间。
```

已经提供的条件不重问。默认只使用当前宿主模型，进度仅显示“第1步”至“第6步”。最终只交付 `研究执行计划.md`，任务表和文献依据放在同一文件内；按用户指定格式另行导出时，先检查中间成稿。

## 本版工作规则

未读满规定全文或尚有未完成的Skill任务，不能作为正式成品交付。继续检索、阅读、核对方法和修正安排；不能把缺口改成研究者的后续阅读任务。真实外部阻塞单独简短说明，暂行稿与正式计划严格区分。

计划正文、附录和正常聊天收尾均不写自我免责、模型执行范围或工具能力说明。必要的审批、资源、质量控制和结果分支写在相关任务中。不通过删掉文字、伪造读取或降低篇数掩盖未完成工作。

## 内部检查

依赖Python标准库；检查日志只供内部使用。任务状态和证据放在该任务的 `_work/` 中，不写入已安装技能目录。

```bash
# 续做检查：返回成功也不能代表正式交付
python scripts/check_plan.py /path/to/task/_work/plan_state.json --mode draft

# 正式交付：检查状态、证据文件、引用和正文
python scripts/check_delivery.py /path/to/task/_work/plan_state.json /path/to/task/_work/研究执行计划.draft.md

# 回归测试
python -m unittest discover -s tests -v
```

正式检查返回0并且 `delivery_ready=true` 才可进入宿主的最后证据复核与文件交付。1表示需要继续处理，2表示输入或读取错误。检查程序不联网；真实阅读与科学判断由宿主执行，不在最终计划中复述这些技术说明。

## 包内文件

```text
cell-plan/
├── SKILL.md
├── agents/openai.yaml
├── assets/research-plan-template.md
├── references/reading-and-planning.md
├── scripts/check_plan.py
├── scripts/check_delivery.py
├── tests/test_check_plan.py
├── tests/test_check_delivery.py
└── README.md
```
