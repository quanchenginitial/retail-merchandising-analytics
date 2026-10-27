# 当前一步：导入价格原始表

更新日期：2026-10-27（Australia/Sydney）。

你的最新截图中，销量详细检查 15 项全部 PASS。59,181,090 个日销量单元格、累计 66,927,173 件和双向来源对账均符合预期；日历与销量原始表现已验收完成。

## 先理解价格表的一行

sell_prices.csv 每行是一件商品在一家门店、某个来源周的价格记录。四个字段依次为 store_id、item_id、wm_yr_wk、sell_price。其中 wm_yr_wk 用于以后与日历中的同名字段对应。

价格表的粒度是“商品 × 门店 × 周”，不是每天一行。所以这次要核对三个字段组合后的唯一键；不能只按商品编号连接价格，否则以后可能把一条日销量匹配到多条价格，放大计算结果。

## 本次只执行这一份脚本

1. 打开 [06_import_prices.sql](../sql/06_import_prices.sql)，复制全部内容。
2. 在 DBeaver 确认连接仍为 retail_merchandising，粘贴到 SQL 编辑器。
3. 使用“执行 SQL 脚本”（默认 Alt+X）运行整份脚本一次，等待最后的 12 行结果。

脚本会创建 raw.m5_prices，四列均先按 VARCHAR 保留原值，再检查结构、键和必要字段。当前不转换价格类型，也不连接销量表。源 CSV 约 203 MB，请等执行完成，不重复运行。

## 预期结果

所有 12 行 status 均为 PASS。

| check_name | 预期 |
| --- | ---: |
| row_count | 6841121 |
| column_count | 4 |
| varchar_column_count | 4 |
| expected_column_names | 4 |
| column_sequence_errors | 0 |
| distinct_item_store_week_keys | 6841121 |
| duplicate_key_rows | 0 |
| missing_required_rows | 0 |
| distinct_item_store_pairs | 30490 |
| distinct_items | 3049 |
| distinct_stores | 10 |
| distinct_weeks | 282 |

请把这 12 行结果截图发回。如果提示表已存在，不要删表，只执行 BASIC CHECKS 注释之后的 WITH 查询即可。若有其他报错或 FAIL，保留现状并发回结果。

## 这一小步的范围

助手已在独立临时数据库完成预验证，12 项全部通过，源文件 hash 与原登记一致且验证前后不变。这不是你当前数据库的执行结果；详见 [验证说明](PRICE_IMPORT_VALIDATION.md)。

本步通过只表示基础结构与键符合预期。下一步再检查价格数值与来源完整对账；之后建模时再检验每天的销量是否有对应价格。商品门店组合数量相同，不代表每一天都已经匹配到价格，当前还不能据此计算完整销售金额。
