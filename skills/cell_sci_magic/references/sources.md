# 原始依据与基础计算资料

本文件只记录传统典籍和普通基础计算资料。不是运行时的阅读清单：本任务需要的业务方法、映射、公式、解释规则都已写入本包，择时无需再打开外部教程。

## S1
### 传统文书呈递的用事依据

《钦定协纪辨方书》卷十一的“上表章”条，采用维基文库所载四库全书文本作为核查入口：
https://zh.wikisource.org/wiki/欽定協紀辨方書_(四庫全書本)/卷11

该条提供传统文书呈递的宜忌语境。本包使用固定版本历书数据中的综合宜忌，不从一句古文外推出完整神煞算法。现代论文投稿、修回和基金提交到“上表章”的映射，是本包设计的类比；古籍没有现代投稿录用概率和百分制评分。

本包对原文作方法说明，不把现代口播或自定权重署为古籍原话。

## S2
### 日级历书计算资料

基础计算库版本：`cnlunar==0.2.5`。

发布记录与接口资料：
https://pypi.org/project/cnlunar/0.2.5/
https://github.com/OPN48/cnlunar

本地适配器使用 `Lunar`，固定参数 `godType='cnlunar'`、`year8Char='year'`、`yeargod='duty'`。读取最终宜忌、日值神、建除和日黄黑道。不能把另一个历书来源的同名字段静默换入评分。

使用字段：`goodThing`、`badThing`、`goodGodName`、`badGodName`、`todayLevelName`、`get_today12DayOfficer()`、农历年月日与 `day8Char`。

本包不包含此依赖的代码副本；依赖按其自身许可证安装与使用，不改其署名。

## S3
### 时级历法和交叉核对

基础计算库版本：`lunar_python==1.4.8`。

发布记录与接口资料：
https://pypi.org/project/lunar_python/1.4.8/
https://github.com/6tail/lunar-python

适配器使用 `Solar.fromYmdHms(...).getLunar()`；读取 `getYear()`、`getMonth()`、`getDay()`、`getDayInGanZhi()`、`getDayInGanZhiExact()`、`getTimeInGanZhi()`、`getTimeTianShen()` 和 `getTimeTianShenLuck()`。

农历日期、日干支用于与日级数据交叉核验；时值神和时吉凶用于时项。本版不拿该库另一套日宜忌覆盖S2的事件宜忌。

本包不包含此依赖的代码副本；依赖按其自身许可证安装与使用。

## S4
### 时区与边界

基础时区数据版本：`tzdata==2026.5`。
https://pypi.org/project/tzdata/2026.5/

引擎以固定UTC+8处理通书瞬间，以指定IANA时区显示用户可用窗口。固定版本的数据用于跨地区与夏令时换算，不以全年固定时差替代时区数据库。

## S5
### 历法人工复核入口

香港天文台公历与农历对照表：
https://www.hko.gov.hk/sc/gts/time/conversion.htm

仅支持历法事实核查，不支持择吉对投稿结果具有预测力。正常计算无需在线查询此页面；出现历法冲突时才使用原始历法资料复核。

## 本包自定部分

现代问事映射、60/15/25权重、09:00—21:00工作窗口、20分钟最小时长、截止前30分钟缓冲、并列排序与报告文风均是本包规则。依据见 `scoring-v1.md`、`method.md` 和 `../rules/submission-v1.json`，不需要外接知识或提示词。

本文件不是验证成功声明。真实安装与测试状态以 `validation.md` 为准。


## S6
### 方位、时干与五行对应

《礼记·月令》：https://zh.wikisource.org/wiki/禮記/月令

《五行大义》卷一、卷二：
https://zh.wikisource.org/wiki/五行大義/1
https://zh.wikisource.org/wiki/五行大義/2

2026-10-18核查。以上传统文本支持方位、干支和五行对应的知识背景，包内所需对照完整列于 `regions-v1.md` 和规则JSON。原典未把中国现代省份分成投稿区域，也没有地区投稿百分制。

## S7
### 五行关系及采用范围

《五行大义》卷二“第四论相生”“第十论相克”记有相生、相克循环；同卷另有扶抑、休王等不同语境，不能将之统统压成“生一定好、克一定坏”。

本包只内置五行关系对照。将这些关系用于地区与时干的2/1/0同分顺序，是本包默认采用的娱乐规则，不称原典公式、旺衰判断或个人命盘结论。

## S8
### 统一时间与显示

中国科学院关于国家授时中心的资料：
https://www.cas.cn/cm/202501/t20250102_5044028.shtml

香港天文台“本地时间”：
https://www.hko.gov.hk/sc/gts/time/basicterms-localtime.htm

以上供统一标准时与UTC+8背景核查。五方公开版明确采用北京时间UTC+8，不因地理区域改变钟点，也不把现代区域划分当作天文时区或真太阳时分区。运行只使用已固定的本地时区数据，不请求上述网页。
