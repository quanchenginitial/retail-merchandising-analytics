# 当前一步：比较关联指标与共现数量门槛

更新日期：2026-11-13（Australia/Sydney）。

**这一步为了什么：把“商品一起出现多少次”转成可比较的关联指标，并观察提高最低共现数量要求后，还剩多少候选商品对，避免只看很高的提升度就下结论。**

## SQL80 已验收

截图 **15 行 × 5 列、75 个字段完整匹配**：十项 PASS、五项 INFO，五个 expected=NULL 正常保留。10,757 次篮子内商品对出现，对应 **9,688 个独立商品对**；其中 **8,785 对仅出现一次、903 对至少两次**，最高共现于 39 个候选篮子。两项计数核对差异均为零，见 [验收记录](../data/retailrocket_basket_pair_counts_learner_acceptance.json)。

## SQL81 的三个指标

设 N 为全部 **17,672 个候选篮子**，n_A、n_B 分别为包含 A、B 的篮子数，n_AB 为同时包含两者的篮子数。

- **支持度** = n_AB/N：全部候选篮子中有多少比例包含这一对。
- **置信度 A→B** = n_AB/n_A：包含 A 的篮子中有多少比例也包含 B。B→A 的分母不同；本报告让每对的两个方向各贡献一次，计算合并后的中位数。
- **提升度** = 置信度 A→B ÷ (n_B/N)：相对于 B 在总体中的出现比例，A、B 共同出现的关联强度。它没有百分号；高值不等于有效推荐或因果效果。

支持度和置信度显示为百分比，报告中的百分比与提升度保留六位小数。单商品篮子仍计入 N 和商品各自的出现次数，不使用 source_event_rows 加权。

## 现在执行 SQL81

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [81_analyze_retailrocket_basket_association_metrics.sql](../sql/81_analyze_retailrocket_basket_association_metrics.sql)，完整执行只读查询。无需建表、重新导入 CSV 或重跑 SQL79/80。
3. 提供 **五行、九列完整结果，正常五行全部 PASS**。请确保最右侧 check_status 可见；如需拆图，保留最左侧 min_pair_baskets，并让相邻截图有重叠列。

九列依次为 min_pair_baskets、retained_pairs、retained_pair_pct、retained_pair_occurrences、median_support_pct、median_directional_confidence_pct、median_lift、max_lift、check_status。

五行分别保留 **至少在 1、2、3、5、10 个候选篮子中出现**的商品对。它们逐层包含，**不能相加，也没有 TOTAL 行**。retained_pair_pct 的分母是 **9,688 个独立商品对**，与支持度的 **17,672 个候选篮子**不同。retained_pair_occurrences 是入选商品对的共现次数之和；同一篮子可贡献多对，因此不是覆盖的独立篮子数。本步比较门槛，不宣布哪个门槛最佳。

助手预检已通过，用户执行和截图验收仍待完成；见 [验证说明](RETAILROCKET_BASKET_ASSOCIATION_METRICS_VALIDATION.md)。

## 验证和解释范围

助手单次解析 events.csv 重建六字段商品成员输入，匹配 SQL79 已验收指纹，并独立核对全部未舍入十字段商品对指标；复用此前完整来源证据，不重跑旧 SQL、属性历史、UTC 或层级检查。

分析使用全部候选篮子，不沿用类别 1613 或 7 天漏斗的限制。候选键未证明真实订单或同时购买；这些统计不构成规则排名、推荐效果或最优门槛结论。公开保存汇总结果，不上传商品对编号明细。RF 分群、规则选择与稳定性验证、Power BI 仍未完成。
