# 当前一步：接入 Retailrocket 行为数据

更新日期：2026-11-02（Australia/Sydney）。

**这一步为了什么：补上 M5 缺少的浏览、加购和购买行为，并先确认数据来源、文件和每行记录的含义。**

## SQL53 已验收

截图中的 36 行、12 列、全部 432 个可见值及 36 个完整 PASS 匹配冻结私有参考；见 [聚合验收](../data/anomaly_case_histories_learner_acceptance.json)。实际案例值、选中键和截图未上传。公开仅保留覆盖及指纹，具体示例并不代表总体。

阶段 6 的价格关联、候选筛查、周度概览和示例历史复核已完成，并已形成 [调查证据框架](STAGE06_ANOMALY_REVIEW_FINDINGS.md)。持续零销量会使滚动均值下降，NONE 不等于恢复正常；窗口末端的变化没有后续观察；低基线可能使回升更容易触发规则。以上是规则与观测的解释，真实缺货、原因、识别准确率及干预收益仍未验证。

## 下一小步

按 [Retailrocket 接入说明](RETAILROCKET_INTAKE_ZH.md) 从发布者页面获取原始文件并保持原样。预期四份文件为 events.csv、item_properties_part1.csv、item_properties_part2.csv、category_tree.csv。记录实际保存位置，随后核对文件大小、SHA-256、表头及行数，再进入加载步骤。

当前未在 D:/database 搜索到上述 Retailrocket 文件。尚未下载、加载或实测审计本地 Retailrocket 数据；发布者统计与本地审计结果要分开记录。不要把文件导入 Excel 后另存，以免改变时间戳、编号或原始内容。

本模块与 M5 独立：两套数据不连接商品或用户编号；transaction 事件数不直接等于订单数；没有可核实金额字段时做 RF 行为分群，不称为货币 RFM。原始事件和属性明细保持本地，不上传 GitHub。

本步不运行新的 SQL。拿到来源文件后，先完成一次小范围来源审计，再决定类型化、去重、时点属性连接及分析口径。
