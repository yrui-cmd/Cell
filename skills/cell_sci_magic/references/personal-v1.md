# 出生四柱口径（沿用v1）

当前分析与主排序以analysis-v2.md为准。本文件只说明出生输入与四柱计算，v1固定印星奖励已撤销，不能回退成旧冲合推荐。

必要字段：calendar（solar/lunar）、birth_date（YYYY-MM-DD）、birth_time（当地HH:MM或HH:MM:SS）、birth_place（城市）、birth_timezone（IANA）、birth_longitude（东正西负）。建议提供birth_time_uncertainty_minutes；默认1分钟并另外保留太阳近似边界缓冲。完整分析另需yun_gender（male/female）或yun_direction（forward/backward）。

```json
{
  "calendar": "solar",
  "birth_date": "2005-12-23",
  "birth_time": "08:37",
  "birth_place": "测试地点，非客户真实资料",
  "birth_timezone": "Asia/Shanghai",
  "birth_longitude": 120.0,
  "birth_time_uncertainty_minutes": 1,
  "yun_gender": "male"
}
```

1901—2099且不能出生于未来。农历输入须leap_month=true/false，限定Asia/Shanghai；海外农历先核实公历日期。夏令时重复钟表时刻需birth_utc_offset，不存在的钟表时刻拒绝计算。出生时间不详不能补造时柱。

由lunar_python==1.4.8实际排盘。年/月依据真实UTC瞬间转北京时间，按立春/节令；日时按当地近似真太阳钟，sect=1，23点换日。太阳钟为UTC+4×出生地经度分钟+NOAA均时差近似；https://gml.noaa.gov/grad/solcalc/solareqns.PDF 。2分钟项目缓冲不是有保证的全球最大误差。城市中心经度近似、历史计时和记忆误差均应说明，接近边界不作唯一盘面。

四柱、日主、藏干及十神真实计算；当前地点与出生地点不能混用。候选日时同样按当前实际地点太阳钟划分；通书基础层继续使用固定北京时间通书，明确分栏。

不默认保存真实生辰。临时输入任务后移除；用户需要完整依据时才导出含出生派生字段的JSON。不得将客户数据加入安装包、测试或共享日志。
