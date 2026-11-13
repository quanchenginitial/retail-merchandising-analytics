# 当前一步：核对候选篮子中的商品对计数

更新日期：2026-11-13（Australia/Sydney）。

**这一步为了什么：在分析“哪些商品经常一起出现”之前，先确认同一候选篮子内的商品对只计一次，并核对总数，给后续共同购买分析建立正确的计数和总体口径。**

## SQL79 已验收

截图 **21 行 × 5 列、105 个字段完整匹配，21 项全部 PASS、无 NULL**。rr_mart.transaction_basket_items 已有 **22,323 个商品成员、17,672 个候选篮子**，source_event_rows 合计 **22,457**。123 个成员出现多次，共多出 134 次出现；这些是事件次数，不是已核实的购买件数。见 [验收记录](../data/retailrocket_transaction_basket_items_learner_acceptance.json)。

候选篮子包括 **15,029 个单商品组和 2,643 个多商品组**，最大 31 个不同商品。本步从这张已建立的表继续，不再执行 SQL79 建表部分。

## SQL80 怎么计数

只读取成员表的 **visitorid、transactionid、itemid**。同一候选篮子要求前两个编号都相同；商品对要求 item_a < item_b，因此 A–B 与 B–A 合并为一对，也不会产生 A–A。每个篮子内每对最多计一次，不使用 source_event_rows 加权。

例如，一个篮子包含 A、B、C，会产生 A–B、A–C、B–C 三对；只有 A 的篮子产生零对。对含 k 个不同商品的篮子，应有 k×(k−1)/2 对；SQL80 用这个公式核对总数。**全部 17,672 个候选篮子仍是后续支持度的总体**，不能把单商品组从分母中排除。本步尚不计算支持度、置信度或提升度。

## 现在执行 SQL80

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [80_analyze_retailrocket_basket_pair_counts.sql](../sql/80_analyze_retailrocket_basket_pair_counts.sql)，完整执行这条只读查询。无需建表或重新导入 CSV。
3. 提供 **15 行、5 列完整结果**，列为 check_order、check_name、actual、expected、status；请拉宽 check_name。若拆图，保留检查序号和名称，并让相邻截图有重叠行。

正常结果应有 **十项 PASS、五项 INFO，且无 FAIL/BLOCKED**。八项来源控制核对商品成员与篮子数量、键类型、有效性和唯一性；末两项控制核对商品对合计及频次分区。中间五项 INFO 展示新发现的商品对出现总次数、独立商品对数、只出现一次或至少两次的商品对数、单对最多出现的篮子数。它们的 **expected=NULL 表示没有预设探索值，不是失败**；请保留这些 NULL。

助手预检已通过，用户执行和截图验收仍待完成；见 [验证说明](RETAILROCKET_BASKET_PAIR_COUNTS_VALIDATION.md)。

## 验证和解释范围

助手单次解析 **events.csv** 重建六字段商品成员输入，匹配 SQL79 已验收的完整成员流哈希，再独立核对全部商品对聚合计数。此前原始五字段来源验证继续作为证据，本步不重跑该整套排序核验，也不重跑属性历史、UTC、类别层级或旧分析。

这里使用全部 transaction 事件形成的候选篮子，不沿用类别 1613 或 7 天漏斗的限制。候选篮子只是约定的分析单位，未证明真实订单或同时购买；共同出现也不证明推荐效果。公开保存汇总检查，不上传原始编号或商品对明细。RF 分群、共同购买规则及 Power BI 仍未完成。
