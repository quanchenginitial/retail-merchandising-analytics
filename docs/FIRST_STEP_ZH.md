# 当前一步：导出当前 RF 结果表格

更新日期：2026-11-15（Australia/Sydney）。

**SQL90 查询已完成并验收，无需重跑。现在把当前结果表格导出为 CSV，作为后续 Power BI 导入的文件。**

截图中七个完整表头及 **16 行 × 七列的 112 个数据值**均匹配，见 [查询验收](../data/retailrocket_rf_bi_export_query_learner_acceptance.json)。合计仍为 **11,719 个访客编号、17,672 个候选篮子**。SQL89 来源表验收和 [RF 阶段发现](STAGE07_RF_FINDINGS.md) 保持原口径；实际 CSV 尚未收到或核验。

## 从当前 DBeaver 表格导出

1. 在当前已加载全部 **16 行、七列**的结果表格内右键，选择 **Export data → CSV**。导出全部行和全部列；取消仅导出选中行/列的选项。确认 16 行全部加载后，可以使用 **Use fetched rows**。
2. 设置 **UTF-8** 编码、英文逗号分隔；表头选项为 **top / as is / label**（置顶、保持原样、使用列标签）。关闭 **Format numbers**，保留纯整数文本。截图中的千位分隔逗号属于网格显示格式，不应写入数值字段。
3. 保存到 **D:/database/retailrocket/rf_segment_summary.csv**。若保存时发现同名文件已存在，使用新的文件名，并记下实际路径，不覆盖旧文件。
4. 完成前确认导出全部 16 条数据记录，第一行为下面七个字段名，顺序完全一致；再完成保存。

```text
reference_timestamp_ms,recency_order,recency_band,frequency_order,frequency_band,visitor_ids,candidate_baskets
```

各行参考时点均为 **1442545187788**；按 recency_order、frequency_order 排序，无 TOTAL 行。访客编号数与篮子数只在本次快照的互斥组合间加总。

操作依据：[DBeaver 官方数据导出说明](https://dbeaver.com/docs/dbeaver/Data-export/)（2026-11-15 核对）。助手的导出准备预检已通过，见 [验证说明](RETAILROCKET_RF_BI_EXPORT_VALIDATION.md)。

完成后回复 **“已导出”并附实际文件路径**；如使用其他文件名，请提供该路径。下一步会读取你导出的实际 CSV，逐字段核对表头、16 行内容与已验收结果，并记录文件字节及内容校验值。当前仍只需完成导出；Power BI 导入、类型、排序、模型和图表会在文件核验后的步骤处理。
