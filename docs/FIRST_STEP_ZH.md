# 当前一步：导出 RF 汇总 CSV

更新日期：2026-11-15（Australia/Sydney）。

**这一步为了什么：把已验收的 16 行 RF 汇总保存为 CSV，作为后续 Power BI 导入的文件。**

SQL89 的五个表头及 100 个数据字段已核对，20 项全部 PASS，见 [验收](../data/retailrocket_rf_bi_summary_learner_acceptance.json)。rr_bi.rf_segment_summary 现有 **16 行、七列**，合计 **11,719 个访客编号、17,672 个候选篮子**。[RF 阶段发现](STAGE07_RF_FINDINGS.md) 保持原口径。

## 在 DBeaver 导出一次完整结果

1. 选中现有 retail_merchandising 连接，打开并运行只读 [90_select_retailrocket_rf_bi_export.sql](../sql/90_select_retailrocket_rf_bi_export.sql)。确认结果已加载全部 **16 行、七列**。
2. 在结果表格内右键，选择 **Export data → CSV**。导出全部行和全部列；取消仅导出选中行/列的选项。只有确认 16 行全部加载后，才使用 **Use fetched rows**。
3. 设置 **UTF-8** 编码、英文逗号分隔；表头选项为 **top / as is / label**（置顶、保持原样、使用列标签）。关闭 **Format numbers**，保留纯整数文本。
4. 保存到 **D:/database/retailrocket/rf_segment_summary.csv**。若同名文件已存在，使用新的文件名，并记下实际路径，不覆盖旧文件。
5. 完成前确认导出全部 16 条数据记录，第一行为下面七个字段名，顺序完全一致；再完成保存。

```text
reference_timestamp_ms,recency_order,recency_band,frequency_order,frequency_band,visitor_ids,candidate_baskets
```

各行参考时点均为 **1442545187788**；按 recency_order、frequency_order 排序，无 TOTAL 行。访客编号数与篮子数只在本次快照的互斥组合间加总。

操作依据：[DBeaver 官方数据导出说明](https://dbeaver.com/docs/dbeaver/Data-export/)（2026-11-15 核对）。助手的导出准备预检已通过，见 [验证说明](RETAILROCKET_RF_BI_EXPORT_VALIDATION.md)。

完成后回复 **“已导出”并附实际文件路径**。下一步会读取你导出的实际 CSV，逐字段核对表头、16 行内容与已验收结果，并记录文件字节及内容校验值。当前实际导出与文件核验尚未完成；Power BI 导入、类型、排序、模型和图表会在后续步骤处理。
