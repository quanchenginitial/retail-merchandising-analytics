# 当前一步：查看访客编号贡献集中度

更新日期：2026-11-13（Australia/Sydney）。

**这一步为了什么：检查商品对的共现是否分散在多个访客编号，还是由少数编号反复贡献，为判断这些关联证据的覆盖范围补充信息。**

## SQL82 已验收

截图 **十二行 × 九列、108 个字段完整匹配，十二项全部 PASS、无 NULL**。六处省略末尾零的指标显示精确归一化。全部十二个案例合计 **110 次商品对出现**，见 [验收记录](../data/retailrocket_basket_pair_cases_learner_acceptance.json)。这不是 110 个独立篮子。

SQL83 保留**同一批十二个案例及原顺序**，不重新选择门槛，也不改变 PAIR_01–PAIR_12 的当前快照对应关系。

## SQL83 怎么读

- **distinct_visitor_ids**：为该商品对贡献过共现篮子的不同访客编号数。
- **repeat_visitor_ids**：在该案例中贡献**至少两个**共现篮子的编号数。
- **max_baskets_one_visitor / top_visitor_share_pct**：贡献最多的一个编号提供多少篮子，以及它占本案例 n_ab 的比例。
- **repeat_visitor_basket_share_pct**：重复贡献编号所提供的**全部共现篮子**占本案例 n_ab 的比例，不只计算超过第一次的部分。

两个百分比的分母都是**这一行的 n_ab**，不是十二对合计 110。举例说明口径：三个编号分别贡献 3、1、1 个篮子，则不同编号为三个、重复编号为一个，最大编号占比和重复贡献占比均为 60%；后者计算全部三个篮子，而不是超过首次的两个。这只是计算示例，不是本次结果。每行属于不同商品对，跨行编号数不能相加当作独立人数。

## 现在执行 SQL83

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [83_analyze_retailrocket_pair_visitor_concentration.sql](../sql/83_analyze_retailrocket_pair_visitor_concentration.sql)，完整执行只读查询。无需建表、重新导入 CSV 或重跑 SQL79–82。
3. 提供 **十二行、八列完整结果，正常十二行全部 PASS**。请确保最右侧 check_status 可见；如需拆图，保留 case_label，并让相邻截图有重叠行或列。

八列依次为 case_label、n_ab、distinct_visitor_ids、repeat_visitor_ids、max_baskets_one_visitor、top_visitor_share_pct、repeat_visitor_basket_share_pct、check_status。

**集中度很高也可以是 PASS**：检查的是分组、数量和公式是否正确，不是要求结果达到某个业务标准。助手预检已通过，用户执行和截图验收仍待完成；见 [验证说明](RETAILROCKET_PAIR_VISITOR_CONCENTRATION_VALIDATION.md)。

## 验证和解释范围

本步只读取三个成员键，不读取日期或时间字段。助手核对重建的六字段成员输入，并对选中案例×访客编号分组做新的独立比较，最多 110 行 × 五个整数字段；此前全部和选中商品对的指标证据继续复用，不重验这些指标公式。

访客编号不等于已核实自然人；多个不同编号也不证明观测彼此独立。集中度不能单独证明数据错误或推荐效果。案例标签仅在当前快照成立，不公开原访客或商品编号。时间稳定性、规则效果验证、RF 分群及 Power BI 仍未完成。
