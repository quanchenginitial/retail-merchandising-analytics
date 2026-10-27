# 当前一步：导入销量原始宽表

更新日期：2026-10-27（Australia/Sydney）。

你的最新截图中，日历详细检查 17 项全部 PASS，source_only_rows 和 table_only_rows 均为 0。日历导入与当前 CSV 的完整对账已经通过。

## 先理解一行代表什么

sales_train_evaluation.csv 的一行是一个“商品 × 门店”的历史销量序列。前 6 列是 id、item_id、dept_id、cat_id、store_id、state_id；后面 d_1 到 d_1941 是每天的销量。

所以它有 30,490 行、1,947 列，而不是 59,181,090 行。后一个数字是 30,490 × 1,941 个日销量单元格；后续转成长表时才会变成对应的日记录。这里的记录不代表单笔交易。

原始层先保留宽表，所有列按 VARCHAR 读取，便于追溯原值；后续在清洗层统一转换销量类型。当前不拼接 sales_train_validation.csv，因为其历史日期与 evaluation 文件重叠。

## 本次只执行这一份脚本

1. 打开 [04_import_sales.sql](../sql/04_import_sales.sql)，复制全部内容。
2. 在 DBeaver 确认当前连接仍是 retail_merchandising，把内容粘贴到 SQL 编辑器。
3. 使用“执行 SQL 脚本”（默认 Alt+X）运行整份脚本一次，等待完成后查看最后的结果表。

脚本将建立 raw.m5_sales_wide，然后显示 14 行基础检查。源文件约 122 MB，这次处理量比日历大，等待执行结束即可，不要重复点击运行。

## 预期结果

所有 14 行的 status 都应为 PASS。

| check_name | actual / expected |
| --- | ---: |
| row_count | 30490 |
| column_count | 1947 |
| varchar_column_count | 1947 |
| identifier_column_count | 6 |
| day_column_count | 1941 |
| day_column_sequence_errors | 0 |
| distinct_series_ids | 30490 |
| distinct_item_store_keys | 30490 |
| distinct_items | 3049 |
| distinct_stores | 10 |
| distinct_states | 3 |
| distinct_departments | 7 |
| distinct_categories | 3 |
| missing_identifier_rows | 0 |

请发回这 14 行结果的截图。如果提示表已存在，不需要删表：只执行脚本中 BASIC CHECKS 注释之后的 WITH 查询即可。若有其他报错或 FAIL，保留原状并发回结果。

## 助手预验证与下一步

助手已在独立临时数据库中执行本脚本，14 项基础检查全部通过，导入与检查合计约 12.3 秒；实际耗时因环境而异。源文件 SHA-256 与先前登记一致，且验证前后未变。详见 [销量导入验证说明](SALES_IMPORT_VALIDATION.md)。助手没有操作你的持久数据库，因此用户导入仍待上述实际结果。

这一步只验收导入结构与标识的基本完整性，不代表全部销量值已经对账。通过后，下一步再检查销量值、总量和来源一致性；价格文件及宽转长仍待后续操作。
