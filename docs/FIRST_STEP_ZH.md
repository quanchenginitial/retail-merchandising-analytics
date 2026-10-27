# 当前一步：检查日销量的价格覆盖

更新日期：2026-10-27（Australia/Sydney）。

**这一步为了什么：确认每天的商品门店销量能否找到对应周价格，区分零销量缺价和正销量缺价，为后续估算销售额确定可计算范围。**

你的最新截图中，销量与三张维度表的完整关联 20 项全部 PASS：行数、销量、零销量行及门店汇总均保留，三类未匹配行均为 0。见 [验收记录](../data/dimension_joins_learner_acceptance.json)。

## 本次如何匹配价格

先通过 d 找到日历中的 wm_yr_wk，再同时使用 item_id、store_id、wm_yr_wk 匹配价格。一个商品在一家门店同一周内的多个日期可以共享该周价格。

覆盖率分开看三种：

| 指标 | 分母 | 回答的问题 |
| --- | --- | --- |
| 日记录覆盖率 | 全部商品门店日记录，包括零销量 | 有多少日记录能够匹配价格？ |
| 正销量记录覆盖率 | units 大于 0 的记录 | 实际卖出商品的日期是否都有价格？ |
| 销量件数覆盖率 | 全部销量件数 | 有多少件销量具有对应价格？ |

缺价仍保留为空。没有价格不能直接解释为缺货、未上市或下架；本步只核查覆盖，金额计算留到后续。

## 本次只执行这一份查询

1. 打开 [16_audit_price_coverage.sql](../sql/16_audit_price_coverage.sql)，复制全部内容。
2. 在 DBeaver 当前 retail_merchandising 连接中新建 SQL 编辑器，粘贴、全选后执行（默认 Ctrl+Enter）。这是一条可重复运行的只读查询。
3. 等最终 23 行结果出现，把完整结果截图发回；显示不全时可分两张。

助手在独立临时数据库完成全量预查，12 项机械检查、2 项正销量覆盖门槛和 15 个针对性用例通过，关联审计约 13 秒。实际耗时因环境而异，详见 [验证说明](PRICE_COVERAGE_VALIDATION.md)。这些价格观察值仍需你本地执行确认。

## 先看状态含义

- 第 1–12 行检查关联是否保留行数、销量和零销量，以及日历匹配和来源值是否有效。
- 第 13–14 行检查是否有正销量缺价；必须为 0，才能接受后续“覆盖全部正销量”的金额代理指标。
- 第 15–23 行标为 INFO，是覆盖情况的实测统计，不是失败，也不要求缺价日记录数为 0。

本快照预期为前 14 行 PASS、后 9 行 INFO。若前 12 行任一失败，覆盖结果会标为 INCOMPLETE；百分比分母为 0 时显示 N/A，不会伪报 100%。

## 预期校验结果

| check_name | 预期 |
| --- | ---: |
| price_rows | 6841121 |
| base_rows | 59181090 |
| joined_rows | 59181090 |
| row_count_difference | 0 |
| base_units | 66927173 |
| joined_units | 66927173 |
| units_difference | 0 |
| base_zero_rows | 40241819 |
| joined_zero_rows | 40241819 |
| missing_calendar_rows | 0 |
| invalid_sales_rows | 0 |
| store_control_mismatches | 0 |
| missing_price_positive_rows | 0 |
| missing_price_units | 0 |

## 助手预查观察值，等待你的结果复核

| check_name | 预查结果 | status |
| --- | ---: | --- |
| priced_daily_rows | 46881677 | INFO |
| missing_price_daily_rows | 12299413 | INFO |
| missing_price_zero_rows | 12299413 | INFO |
| positive_sales_rows | 18939271 | INFO |
| priced_positive_rows | 18939271 | INFO |
| priced_units | 66927173 | INFO |
| daily_row_coverage_pct | 79.2173 | INFO |
| positive_row_coverage_pct | 100.0000 | INFO |
| units_coverage_pct | 100.0000 | INFO |

这表示独立预查中，12,299,413 个缺价日记录的销量全部为 0；全部正销量记录及 66,927,173 件销量都有对应价格。日记录覆盖率和销量覆盖率使用不同分母，因此需要同时报告。

若出现 FAIL、INCOMPLETE、报错或观察值不同，保留结果发回。正销量缺价会影响完整金额代理指标的计算范围，但不自动意味着来源数据错误，也不妨碍继续分析销量。

## 通过后

下一步明确零销量缺价记录的金额处理口径，再建立保留价格覆盖标记的销量事实表。缺失价格保持空值，估算销售额使用来源周价格，不等同于已核实的交易收入或利润。
