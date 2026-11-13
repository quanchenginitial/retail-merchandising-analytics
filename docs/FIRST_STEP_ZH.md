# 当前一步：组合最近交易间隔与频次

更新日期：2026-11-13（Australia/Sydney）。

**这一步为了什么：将 R（最近交易间隔）与 F（观察期内频次）一起查看，了解不同记录行为的分布，为后续调查和行动假设提供描述性分组。**

SQL86 截图的 **35 个字段完整匹配，五项全部 PASS、无 NULL**，见 [验收](../data/retailrocket_visitor_purchase_recency_learner_acceptance.json)。SQL87 沿用同一批 **11,719 个有交易记录编号**、原有区间和参考时点，不包含非交易编号。

## 如何读这张矩阵

四个 R 区间仍是小于 7、7 至小于 30、30 至小于 60、至少 60 天。参考时点固定为 **2015-09-18 02:59:47.788 UTC**，减去每编号全部成员中最后交易观测时间；分类按精确毫秒，不使用今天。

四个 F 区间仍是 1、2、3–4、至少 5 个不同候选篮子。R 与 F 组合成 **16 格，即使计数为零也保留，再加一行 TOTAL/TOTAL**；先按 R、再按 F 排序。

每格的 visitor_ids 是编号数；candidate_baskets 是这些编号**整个观察窗口的 F 合计**。例如“小于 7 天 × 至少 5 个篮子”表示最后交易记录接近终点、整个观察期至少出现五个篮子，**不表示最近七天发生了五次交易**。

visitor_share_pct 分母是全部 **11,719 个编号**；basket_share_pct 分母是全部 **17,672 个候选篮子**，不是各行或各列的小计。空格保留 0，两个占比显示六位小数。TOTAL 已汇总前 16 格，不要再次相加。

## 现在执行 SQL87

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [87_analyze_retailrocket_visitor_rf_segments.sql](../sql/87_analyze_retailrocket_visitor_rf_segments.sql)，完整执行只读查询。无需建表、导入 CSV 或重跑旧 SQL。
3. 提供 **17 行、七列完整结果，正常 17 行全部 PASS**；确保最右侧 check_status 可见。若需拆图，请保留两个区间标签并让相邻截图有重叠行。

七列依次为 recency_band、frequency_band、visitor_ids、visitor_share_pct、candidate_baskets、basket_share_pct、check_status。

助手预检已通过，用户执行和截图验收仍待完成，见 [验证说明](RETAILROCKET_VISITOR_RF_SEGMENTS_VALIDATION.md)。新增独立比较全部 **11,719 行、六字段** RF 记录，并用已验收 SQL85/86 汇总核对边际；不重跑旧查询。

此矩阵是固定区间的描述性 RF 基线，不是经过效果验证的高价值、流失或忠诚标签，也没有金额维度 M。不同编号的观察长度可能不同，编号不是已核实自然人，候选篮子也不是核实订单。独立时间验证、业务效果评估与 Power BI 仍未完成。
