# 当前一步：创建 RF 的 BI 汇总来源

更新日期：2026-11-15（Australia/Sydney）。

**这一步为了什么：把已验收的 RF 分布保存为一张只有 16 行的小表，便于后续导入 Power BI，并避免把 TOTAL 与明细重复加总。**

SQL88 的 **153 个数据字段匹配、17 行全部 PASS、无 NULL**；末列状态表头被裁切，但完整 PASS 值均可见，见 [验收](../data/retailrocket_rf_basket_concentration_learner_acceptance.json)。SQL85–88 的描述性 RF 基线已整理为 [阶段发现](STAGE07_RF_FINDINGS.md)。

## 这张表保存什么

SQL89 一次性创建 **rr_bi.rf_segment_summary**。每行代表一个 RF 组合，四个 R × 四个 F 共 **16 行**，即使某个组合为零也保留。七个字段依次为：

- reference_timestamp_ms：固定历史参考时点。
- recency_order、recency_band：R 的排序与标签。
- frequency_order、frequency_band：F 的排序与标签。
- visitor_ids、candidate_baskets：访客编号数与这些编号在整个观察窗口内的篮子数。

表里没有 TOTAL 行。后续汇总 16 个互斥组合，仍应得到 **11,719 个访客编号、17,672 个候选篮子**。两个计数可以在同一快照的互斥组合之间相加；不代表可跨不同快照相加，也不是已核实人数。

百分比暂不保存，后续建立 Power BI 指标时明确筛选后的分母。top1/top5 集中度也不放入这张可加总表，因为跨组合汇总时需要重新排名，不能直接相加。

## 现在执行 SQL89

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [89_build_retailrocket_rf_bi_summary.sql](../sql/89_build_retailrocket_rf_bi_summary.sql)，首次完整执行建表与检查脚本。
3. 提供 **20 行、五列检查结果，正常 20 项全部 PASS**；五列为 check_order、check_name、actual、expected、status，请保留完整检查名与状态。

若提示目标表已存在，保留现有表，只运行文件 **-- CHECKS:** 标记下面的只读检查部分核对现有对象，并发送结果；不要删除或替换该表。建表成功后如只需再次查看检查结果，也可以单独运行这一检查部分。

助手预检已通过，用户建表和截图验收仍待完成，见 [验证说明](RETAILROCKET_RF_BI_SUMMARY_VALIDATION.md)。预检独立比较了全部 16 行、七字段的物化汇总内容，原始数据与既有表保持不变。

此步完成的是 BI 来源准备。Power BI 导入、模型、指标、图表和交互验证仍待后续实施；RF 时间稳定性和业务影响也尚未验证。
