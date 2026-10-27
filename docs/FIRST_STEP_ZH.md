# 当前一步：核对价格值、编号对应关系与来源一致性

更新日期：2026-10-27（Australia/Sydney）。

你的最新截图中，价格基础检查 12 项全部 PASS。三张 raw 原始表已经导入；日历和销量已完成详细审计，本步补齐价格表的详细验收。

## 为什么不能只看组合数量

30,490 个商品门店组合与销量表的组合数量相同，并不证明具体编号都对应。例如，少一个正确组合、多一个错误组合，总数仍然相同。这次要检查每个价格组合是否真实存在于销量表，以及每个价格周编号是否存在于日历。

价格还需要能够解析为有限正数，同时与原 CSV 的完整文本记录一致。这两件事分别检查；不会先把价格四舍五入成两位小数再比较。

## 本次只执行一条只读查询

1. 打开 [07_audit_prices.sql](../sql/07_audit_prices.sql)，复制全部内容。
2. 在 DBeaver 当前 retail_merchandising 连接中，粘贴并执行完整查询一次。
3. 等待最后的 15 行结果，再把截图发回。

本查询不建表、不修改原值、不计算销售金额。它会重新读取价格 CSV，对四个字段双向逐行对账，包含重复次数；处理量比基础计数大，请等待完成，不重复点击运行。

## 预期结果

所有 15 行 status 均为 PASS。

| check_name | 预期 |
| --- | ---: |
| source_rows、table_rows | 各 6841121 |
| missing_required_rows | 0 |
| duplicate_key_rows | 0 |
| valid_numeric_price_rows | 6841121 |
| invalid_price_rows | 0 |
| nonpositive_price_rows | 0 |
| minimum_price | 0.01 |
| maximum_price | 107.32 |
| invalid_week_code_rows | 0 |
| unknown_calendar_week_rows | 0 |
| orphan_item_store_rows | 0 |
| sales_pairs_without_any_price | 0 |
| source_only_rows、table_only_rows | 各 0 |

valid_numeric_price_rows 只表示可以解析为有限数值，是否大于 0 由 nonpositive_price_rows 单独检查。额外小数位不会被自动认定为非法；完整来源对账仍会发现价格文本变化。

orphan_item_store_rows 为 0，表示价格中的商品门店组合都存在于销量表。sales_pairs_without_any_price 为 0，表示销量表中的每个商品门店组合至少在某一周有价格记录。这不等于每天的销量都有对应价格；日级覆盖会在后续模型连接时单独核验。

最后两项均为 0，表示当前价格 CSV 与 raw 表的四字段完整记录一致。此 SQL 不重新计算历史来源快照 hash。

## 验收与下一步

助手已经在独立临时数据库中验证完整来源 15/15 PASS，并完成 12 个微型用例；详见 [验证说明](PRICE_AUDIT_VALIDATION.md)。这些结果不能替代你当前数据库的实际执行结果。如果出现 FAIL 或报错，保留现状并发回截图，不手动修价格或删记录。

本步通过后，三份原始表的导入与详细对账即可完成，再进入清洗层类型转换和后续建模。
