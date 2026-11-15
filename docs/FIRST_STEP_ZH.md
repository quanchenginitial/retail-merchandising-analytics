# 当前一步：检查 RF 组内篮子集中度

更新日期：2026-11-15（Australia/Sydney）。

**这一步为了什么：判断一个 RF 组的篮子贡献是否由许多编号共同产生，还是主要集中在少数高频编号上，为后续核查提供线索。**

SQL87 的 **119 个字段完整匹配，17 行全部 PASS、无 NULL**，见 [验收](../data/retailrocket_visitor_rf_segments_learner_acceptance.json)。SQL88 沿用相同的 16 个 RF 组合、11,719 个有交易记录编号与 17,672 个候选篮子；R/F 区间和历史参考终点保持不变。

## 如何读这一张表

每组按整个观察窗口的篮子频次 F 从高到低排列，频次相同时按编号升序确定顺序。top1_baskets 是第一名的篮子数，top5_baskets 是前五名的篮子合计；不足五个编号时取全部成员。并列顺序只是计算约定，不表示业务优先级。

两个占比的分母是**当前 RF 组的 candidate_baskets**。例如某组共有 1,000 个篮子、前五名贡献 700 个，其 top5_share_pct 为 70%。SQL87 的 basket_share_pct 使用全体 17,672 个篮子为分母，两者回答不同问题。

**TOTAL 从全部编号重新排名，再计算全局前一名和前五名。不能把各组的 top1_baskets 或 top5_baskets 相加当作 TOTAL。** 各组 basket 总量仍覆盖其成员整个观察窗口，并不限于最近 7/30/60 天。

全部 16 个组合都保留。若某组为空，计数是 0、两个占比是 NULL；若非空组至多五个编号，top5_share_pct 自然为 100%，应结合组规模阅读。

## 现在执行 SQL88

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [88_analyze_retailrocket_rf_basket_concentration.sql](../sql/88_analyze_retailrocket_rf_basket_concentration.sql)，完整执行只读查询。
3. 提供 **17 行、九列完整结果，正常 17 行全部 PASS**；保留最右侧 check_status。若拆图，请保留两个区间标签，并让相邻截图有重叠行。

九列依次为 recency_band、frequency_band、visitor_ids、candidate_baskets、top1_baskets、top1_share_pct、top5_baskets、top5_share_pct、check_status。

助手预检已通过，用户执行和截图验收仍待完成，见 [验证说明](RETAILROCKET_RF_BASKET_CONCENTRATION_VALIDATION.md)。新增独立比较全部 11,719 行、八字段的 RF 与组内/全局排名记录，复用已验收的 RF 指纹。

集中度本身不能证明欺诈、机器人、高价值或忠诚。编号不是已核实自然人，候选篮子不是核实订单，不同编号的观察长度也可能不同。独立时间验证、业务效果评估与 Power BI 仍未完成。
