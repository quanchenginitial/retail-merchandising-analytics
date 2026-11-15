# 当前一步：在 Power Query 核对 RF 数据和类型

更新日期：2026-11-15（Australia/Sydney）。

**实际 CSV 已核验通过，Power BI Desktop 也已确认能够打开。现在只做导入预览和字段类型检查，停在 Power Query 等截图复核。**

D:/database/retailrocket/rf_segment_summary.csv 为 830 字节、UTF-8 无 BOM；16 行七列的全部 112 个值及顺序匹配，合计 11,719 个访客编号、17,672 个候选篮子，见 [实际文件验收](../data/retailrocket_rf_bi_export_file_acceptance.json)。无需重新查询或导出 CSV。

## 在新的空白报表中操作

1. 打开 Power BI Desktop，新建一个**空白报表**。
2. 选择 **Home（主页）→ Get data（获取数据）→ Text/CSV（文本/CSV）**，打开 D:/database/retailrocket/rf_segment_summary.csv。
3. 在预览窗口将文件原始格式设为 **65001: Unicode (UTF-8)**，分隔符选 **Comma（逗号）**，点击 **Transform Data（转换数据）**，进入 Power Query 编辑器。
4. 将查询名称设为 **rf_segment_summary**。确认有 **16 条数据、七列**；表头是下面的字段名，顺序一致，首行字段名不能成为第 17 条数据，也没有 TOTAL 行。
5. 点击各列表头旁的类型图标，按下表设置类型。不要只依赖自动推断。

| 字段（按顺序） | 类型 |
| --- | --- |
| reference_timestamp_ms | Whole Number（整数，Int64） |
| recency_order | Whole Number（整数，Int64） |
| recency_band | Text（文本） |
| frequency_order | Whole Number（整数，Int64） |
| frequency_band | Text（文本） |
| visitor_ids | Whole Number（整数，Int64） |
| candidate_baskets | Whole Number（整数，Int64） |

reference_timestamp_ms 保持每行 **1442545187788** 的整数值；它是固定历史参考时点的毫秒数，不是今天的日期。保留原值和行顺序；这一步不做日期转换、过滤、分组、标签排序、DAX、关系或图表。

**停在 Power Query 编辑器，不点 Close & Apply（关闭并应用），也先不保存报表。** 请发截图，包含查询名、全部 16 行、七个完整表头和类型图标，以及右侧 **Applied Steps（应用的步骤）**；一张放不下可分两张。复核后再进入下一步，当前不声称已加载模型或保存报表。

英文操作合同见 [Power BI RF 导入说明](POWER_BI_RF_IMPORT.md)。操作依据：[Microsoft Text/CSV 连接器](https://learn.microsoft.com/en-us/power-query/connectors/text-csv)与 [Power Query 数据类型](https://learn.microsoft.com/en-us/power-query/data-types)（2026-11-15 核对）。
