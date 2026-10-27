# 当前一步：逐个核对日销量值

更新日期：2026-10-27（Australia/Sydney）。

你的最新截图中，销量长表 14 项全部 PASS：59,181,090 行、40,241,819 个零销量、累计 66,927,173 件，商品门店的日编号完整且唯一，十家门店总量一致。该结果已记录在 [验收记录](../data/sales_daily_learner_acceptance.json)。

## 为什么还需要这一步

总量一致，不能单独证明每一天的值都正确。例如两天的销量从 0、1 变成 1、0，总量、零值个数和行数都不变，但每天的销量已经错位。

本次按数字日编号把每个商品门店的 1,941 天排好，再逐个比较长表的销量和原始宽表对应单元格。同时重新检查日期完整性、重复或缺失组合，防止“只比较到了部分数据”被误认为全部一致。比较的是完整值列表，不用总量或校验和替代精确比较。

## 本次只执行这一份脚本

1. 打开 [11_reconcile_sales_daily.sql](../sql/11_reconcile_sales_daily.sql)，复制全部内容。
2. 在 DBeaver 当前 retail_merchandising 连接中新建 SQL 编辑器，粘贴后选中全部并执行（默认 Ctrl+Enter）。这是一条只读查询，可以重复运行。
3. 等最终 15 行结果出现，把完整结果截图发回。

本步读取已存在的 raw.m5_sales_wide 与 stg.m5_sales_daily，不新建、覆盖或修改表。需要扫描完整长表，请等待结束，不重复点击。助手已在独立临时数据库完成全量预验证；运行耗时与资源记录见 [验证说明](SALES_RECONCILIATION_VALIDATION.md)。

## 预期结果

所有 15 行 status 均为 PASS。

| check_name | 预期 |
| --- | ---: |
| raw_series_rows | 30490 |
| raw_day_columns | 1941 |
| raw_day_sequence_errors | 0 |
| raw_key_error_rows | 0 |
| staging_rows | 59181090 |
| staging_series_count | 30490 |
| missing_core_rows | 0 |
| invalid_day_rows | 0 |
| series_row_count_errors | 0 |
| series_day_coverage_errors | 0 |
| raw_only_series | 0 |
| staging_only_series | 0 |
| compared_cells | 59181090 |
| value_mismatch_series | 0 |
| value_mismatch_cells | 0 |

最后三项表示：完整比较了 59,181,090 个单元格，存在销量差异的商品门店序列为 0，具体不一致的销量单元格为 0。若前 13 项有任何一项未通过，最后两项会显示 INCOMPLETE，表示尚不能接受完整对账结论。

若出现 FAIL、INCOMPLETE 或报错，保留现状并发回结果，不删除表或补 0。本步只对当前 raw 宽表进行来源核对，不重新认证历史下载文件。

## 通过后

逐格对账通过后，销量宽转长才完成完整验收。接下来进入维度建模，再逐步检查日期与价格关联；当前还没有日级价格覆盖结果或销售金额指标。
