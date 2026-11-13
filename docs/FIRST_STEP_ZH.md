# 当前一步：查看十二个案例的月份覆盖

更新日期：2026-11-13（Australia/Sydney）。

**这一步为了什么：看看同一批商品对的共现篮子分布在哪些月份，是否集中在少数月份，为理解此前的关联和编号集中度补充时间分布信息。**

## SQL83 已验收

截图 **十二行 × 八列、96 个字段完整匹配，十二项全部 PASS、无 NULL**。十九处百分比显示精确归一化，见 [验收记录](../data/retailrocket_pair_visitor_concentration_learner_acceptance.json)。各百分比仍用对应案例 n_ab 作分母，访客编号不等于已核实自然人。

SQL84 保留**同一批十二个案例及原顺序**，查看五月至九月的分布，不重新选择案例或门槛。

## 月份如何确定

先对一个候选篮子的**全部商品成员**取 first_timestamp_ms 最小值，再按该时刻的 **UTC 月份**归类。不只看当前商品对；这个时间表示篮子内最早被记录的事件，不是已核实的下单或付款时间。

每个案例有 may_baskets 至 sep_baskets 五个月份计数，**包括零值**；五个月合计应等于本行 n_ab。top_month_share_pct = 最大月份计数 ÷ 本行 n_ab × 100%，不是除以十二对合计 110。集中在一个月份也可以是 PASS，检查的是计算和核对是否正确。

## 现在执行 SQL84

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [84_analyze_retailrocket_pair_month_coverage.sql](../sql/84_analyze_retailrocket_pair_month_coverage.sql)，完整执行只读查询。无需建表、重新导入 CSV 或重跑 SQL79–83。
3. 提供 **十二行、九列完整结果，正常十二行全部 PASS**。请确保最右侧 check_status 可见；如需拆图，保留 case_label，并让相邻截图有重叠行或列。

九列依次为 case_label、n_ab、may_baskets、jun_baskets、jul_baskets、aug_baskets、sep_baskets、top_month_share_pct、check_status。

助手预检已通过，用户执行和截图验收仍待完成；见 [验证说明](RETAILROCKET_PAIR_MONTH_COVERAGE_VALIDATION.md)。

## 验证和解释范围

本步读取三个成员键及 first_timestamp_ms。助手核对重建的六字段成员输入，并独立比较 **十二个案例 × 五个月 = 六十行、三字段**的完整月份计数，包含零值；此前来源、指标和编号分组证据继续复用。

整体 UTC 事件观察窗口是 **2015-05-03 至 2015-09-18**，五月和九月不完整，月份长度也不同。案例又是在同一观察期内选出的，因此本步只能描述回顾性分布，不能据此判断月增长率、月度支持度/提升度或独立时间稳定性。RF 分群、独立验证、规则效果评估及 Power BI 仍未完成。
