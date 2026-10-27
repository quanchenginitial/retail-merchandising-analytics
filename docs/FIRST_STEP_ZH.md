# 当前一步：将销量宽表展开为逐日长表

更新日期：2026-10-27（Australia/Sydney）。

你的最新截图中，价格清洗层 13 项全部 PASS。日历与价格的类型转换已验收；现在处理销量表的形状。

## 为什么要宽转长

目前每个商品门店占一行，d_1 到 d_1941 分别是每日销量列。展开后，每行只表示一个“商品 × 门店 × 日编号”的销量，便于以后连接日历、价格并按时间汇总。

例如某商品门店 d_1=0、d_2=2，展开后就是两行，各自保留对应日编号和销量。零销量行也必须保留。这是原有单元格换一种排列方式，不是新增交易。

新表 stg.m5_sales_daily 只有四列：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| item_id | VARCHAR | 商品编号 |
| store_id | VARCHAR | 门店编号 |
| d | VARCHAR | 来源日编号，例如 d_1 |
| units | INTEGER | 当日记录销量，允许 0 |

类别、部门、州及来源系列编号仍在 raw.m5_sales_wide 中，后续用于维度和追溯，不重复存储到全部 5,918 万行中。本次不连接日历或价格，因此还没有实际日期字段或销售金额。

## 本次只执行这一份脚本

1. 打开 [10_stage_sales_daily.sql](../sql/10_stage_sales_daily.sql)，复制全部内容。
2. 在 DBeaver 当前 retail_merchandising 连接中，按“执行 SQL 脚本”（默认 Alt+X）运行整份脚本一次。
3. 等待最终的 14 行检查结果，把截图发回。

这是首次创建 59,181,090 行的表，比前几步处理量大，请等待完成，不重复点击。助手在独立临时数据库中完成原始表加载、长表创建与检查合计约 75 秒；实际耗时因环境而异。

脚本不修改原始表。NULL 不会被悄悄跳过；缺失、小数、负数或超出 INTEGER 范围的销量会报错停止，而不是补 0 或舍入。

## 预期结果

所有 14 行 status 均为 PASS。

| check_name | 预期 |
| --- | ---: |
| staging_rows | 59181090 |
| column_count | 4 |
| schema_mismatch_count | 0 |
| missing_core_rows | 0 |
| negative_sales_rows | 0 |
| zero_sales_rows | 40241819 |
| total_units | 66927173 |
| max_daily_units | 763 |
| series_count | 30490 |
| series_row_count_errors | 0 |
| series_day_coverage_errors | 0 |
| invalid_day_rows | 0 |
| series_set_difference_rows | 0 |
| store_total_mismatches | 0 |

每个商品门店必须有 1,941 行，且 d_1 至 d_1941 每个日编号都出现。两项同时通过，就能证明该组合没有重复或漏掉日键。另有组合集合核对，以及十家门店分别对应的原始销量总量核对。

如果提示表已存在，不要删除，只运行 VALIDATION 注释之后的 WITH 查询。若有其他报错或 FAIL，保留现状并发回结果。

## 本步通过后还要做什么

本步验证结构、键完整性、零销量与汇总控制数；它还不能证明每个日期上的具体销量都未发生错位。完整的逐单元格来源对账安排在下一步。助手已验证 14/14 PASS 与 8 个针对性用例，详见 [验证说明](SALES_DAILY_VALIDATION.md)，其中包含一个总量不变但单格值移位的例子，用来明确这个检查边界。
