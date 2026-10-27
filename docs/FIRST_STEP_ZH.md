# 当前一步：核对销量值、总量与来源一致性

更新日期：2026-10-27（Australia/Sydney）。

你的最新截图中，销量基础检查 14 项全部 PASS。raw.m5_sales_wide 已通过结构与标识验收，不需要重新导入。

## 为什么还要检查销量值

上一份结果证明行数、列结构、唯一编号和商品门店数量符合预期，但没有逐个检查销量。例如，一件商品少记 1 件，另一件商品多记 1 件，总销量仍可能正确。因此，这一步同时检查全部日销量值、汇总控制数和完整来源记录。

## 本次只执行一条只读查询

1. 打开 [05_audit_sales.sql](../sql/05_audit_sales.sql)，复制全部内容。
2. 在 DBeaver 当前 retail_merchandising 连接中，粘贴并执行完整查询一次。
3. 等待最后的 15 行结果，再把结果截图发回。

查询会读取约 5,918 万个日销量单元格，并重新读取当前路径下的 CSV 进行对账，比上一份基础查询耗时更长。请等执行结束，不重复点击运行。查询中会临时展开日销量来统计，但不会创建长表、修改原表或重新导入数据。

## 预期结果

所有 15 行 status 均为 PASS。

| check_name | 预期 |
| --- | ---: |
| source_rows、table_rows | 各 30490 |
| daily_cells、valid_integer_sales_cells | 各 59181090 |
| missing_sales_cells | 0 |
| invalid_integer_sales_cells | 0 |
| negative_sales_cells | 0 |
| zero_sales_cells | 40241819 |
| total_units | 66927173 |
| max_daily_units | 763 |
| id_label_mismatches | 0 |
| inconsistent_product_mapping_keys | 0 |
| inconsistent_store_mapping_keys | 0 |
| source_only_rows、table_only_rows | 各 0 |

valid_integer_sales_cells 包括语法与范围均有效的整数，负数另由 negative_sales_cells 检查；两项一起通过，才说明这里的销量都是非负整数。缺失单元格不会被跳过，小数也不会被四舍五入成整数后接受。

zero_sales_cells 是记录为 0 的销量，不是 NULL，也不是错误数量。它表示对应商品门店当天记录销量为 0，不能仅据此判断缺货。total_units 是累计销售件数，不是销售金额；max_daily_units 是单个商品在单家门店单日的最大记录销量。

最后两项均为 0，表示当前 CSV 与原始表的完整记录一致，含字段名、文本值、NULL 和重复记录次数。这个比较不重新计算历史来源快照的 SHA-256。

如果出现 FAIL 或报错，保留现状并发回结果，不手工改销量。你当前数据库的实际 15 行结果仍待验收，助手的临时预验证不能替代它。详细方法与验证记录见 [销量审计说明](SALES_AUDIT_VALIDATION.md)。

本步通过后，再进入价格原始表的导入。
