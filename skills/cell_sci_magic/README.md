# cell_sci_magic｜Cell 科研玄学与个人八字投稿分析

从出生资料实排四柱，分层分析旺衰估算、月令格局线索、扶抑喜用候选、起运和大运，再结合流年流月与现实安排比较投稿时窗。

复制填写：

> 用 cell_sci_magic，分析我的旺衰、格局和喜用候选、大运，再选未来七天投稿时间。我出生于【年月日、阳历/农历及闰月】【当地几点几分】，出生地【城市】，误差约【分钟】，采用【男/女传统排运，或明确顺行/逆行】，现在在【城市】。稿件【何时准备好】，最晚【日期、时刻、时区】提交。

无需姓名，缺出生时间或排运参数先补齐，不用通用结果冒充个人分析。具体命令与数据格式见SKILL.md、references/analysis-v2.md。

程序分别展示历法事实和解释模型，印星不再对所有命盘固定加分。格局、喜用与旺衰系数是公开取法的自动估算，复杂格局、合化、从格或用神不稳定时标存疑并停止自动推荐，不能宣传为覆盖所有流派的完整专家断命。民俗娱乐，不预测录用概率。

```bash
python -m pip install -r requirements.txt
python -X utf8 scripts/personal.py chart --profile 出生资料.json
python -X utf8 scripts/personal.py rank --profile 出生资料.json --timezone Asia/Shanghai --longitude 116.4 --days 7
python -X utf8 -m unittest discover -s tests
```

通书与五方大众功能继续保留并明确标注不含个人八字。规则默认启用，无需确认。


通用结果默认按“公历日期＋星期、时辰＋时间段、位置”逐日展示，位置口径为时喜神方。每次默认只出明天一天，可说：“给我明天通用投稿时间，按日期、星期、时辰、位置展示。”详细评分可加--report-style detailed；通用简版不改变个人八字分析报告。
