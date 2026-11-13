# 当前一步：建立最近交易间隔 R 基线

更新日期：2026-11-13（Australia/Sydney）。

**这一步为了什么：补充“最后一次被记录的交易距统一观察终点多久”，建立 R（Recency，最近交易间隔），与已完成的频次 F 形成两个分别核验的维度。**

## SQL85 已验收

截图 **五行 × 七列、35 个字段完整匹配，五项全部 PASS、无 NULL**；见 [验收](../data/retailrocket_visitor_purchase_frequency_learner_acceptance.json)。F 表示每个有交易记录编号的不同候选篮子数。本步仍研究同一批 **11,719 个有交易记录的访客编号**，不含没有交易记录的编号。

## R 怎样计算

参考时点固定为 **2015-09-18 02:59:47.788 UTC**，即已验收数据中全体事件的观察终点。**不是今天，也不是最后一笔交易的时点。**

先对每个编号的所有商品成员取 last_timestamp_ms 最大值，得到该编号最后被记录的交易时间，再用参考时点减去它。一天按 86,400,000 毫秒计算；间隔越小，只表示最后交易记录越接近这个历史终点。

| recency_band | 精确间隔范围 |
| --- | --- |
| R_LT_7D | 小于 7 天 |
| R_7_TO_LT_30D | 至少 7 天、小于 30 天 |
| R_30_TO_LT_60D | 至少 30 天、小于 60 天 |
| R_GE_60D | 至少 60 天 |
| TOTAL | 全部 11,719 个有交易记录编号 |

四个区间互斥，按**未舍入的整数毫秒**分类。min_recency_days、median_recency_days、max_recency_days 是该区间的最小、中位、最大间隔，允许小数天，显示保留六位；显示值即使四舍五入后看起来落在边界，也不改变精确分类。

visitor_share_pct 的分母为 11,719。空区间计数和占比为 0，三个间隔统计为 NULL。TOTAL 是合计，不要和前四行再次相加。这些区间用于描述，不是流失、留存、忠诚度或客户价值标签。

## 现在执行 SQL86

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [86_analyze_retailrocket_visitor_purchase_recency.sql](../sql/86_analyze_retailrocket_visitor_purchase_recency.sql)，完整执行只读查询。无需建表、导入 CSV 或重跑旧 SQL。
3. 提供 **五行、七列完整结果，正常五行全部 PASS**；确保最右侧 check_status 可见。

七列依次为 recency_band、visitor_ids、visitor_share_pct、min_recency_days、median_recency_days、max_recency_days、check_status。

助手预检已通过，用户执行和截图验收仍待完成；见 [验证说明](RETAILROCKET_VISITOR_PURCHASE_RECENCY_VALIDATION.md)。

## 验证和解释范围

本步分析读取三个成员键与 last_timestamp_ms，不需要 first_timestamp_ms 或 F。助手核对重建的六字段成员输入，并独立比较 **全部 11,719 行、三字段**的编号/最后交易毫秒/间隔毫秒；展示统计使用精确计算核对，之前的来源和成员证据继续复用。

这是有限观察窗口内的交易记录间隔，不是终身交易历史；编号不是已核实自然人，交易事件也不自动等于核实订单。R 和 F 仍是分开核验的基线，组合 RF 分群、独立时间验证及 Power BI 尚未完成。
