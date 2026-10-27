# 当前一步：建立日销量事实表

更新日期：2026-10-27（Australia/Sydney）。

**这一步为了什么：把已验证的销量、日期和周价格保存到一张可直接分析的表，为后续商品贡献、门店对比和销售趋势提供统一输入。**

你的价格覆盖截图已验收：14 PASS、9 INFO。12,299,413 个缺价日记录全部为零销量；正销量记录和销量件数的价格覆盖率均为 100%。日记录价格覆盖率 79.2173% 使用包括零销量在内的分母，与前两者并不矛盾。见 [验收记录](../data/price_coverage_learner_acceptance.json)。

## 这张表每一行代表什么

新建 `mart.m5_sales_daily`，每行仍然是一件商品 × 一家门店 × 一个已观察日期。共保留 59,181,090 行，不聚合、不删零销量，也不增加日历最后 28 天的未来销量。

| 字段 | 作用 |
| --- | --- |
| item_id、store_id | 商品和门店标识；后续关联小型维度表获取类别、部门和州 |
| d、date、wm_yr_wk | 保留来源日编号、真实日期和来源周编号 |
| units | 原有日销量，INTEGER |
| sell_price | 对应商品门店周的价格，DECIMAL(18,2)，缺失时仍为空 |
| has_price | 是否成功匹配周价格，BOOLEAN |
| estimated_sales_value | 按以下约定计算的估算销售额，DECIMAL(28,2) |

它仍是长表。与上一步“只查询连接结果”相比，本次把结果保存下来，供后续分析反复使用。

## 金额口径

- `units = 0`：估算销售额为 `0.00`，即使没有价格；缺失的价格本身仍为 NULL，has_price=false。
- `units > 0`：使用销量乘以对应周价格；找不到价格就停止建表，避免把不完整金额当作完整总额。
- 金额是**估算销售额（美元代理指标）**。周价格不能证明每笔交易成交额，也无法据此计算净收入、利润或毛利。

零销量金额记为 0 是本项目的明确计算约定，不代表缺价原因、库存状况或未满足需求已知。计算使用精确小数类型，避免浮点误差。

## 本次执行这一份脚本

1. 打开 [17_build_sales_fact.sql](../sql/17_build_sales_fact.sql)，复制全部内容。
2. 在 DBeaver 的 **retail_merchandising** 连接中新建 SQL 编辑器，粘贴后选择 **Execute SQL Script / 执行 SQL 脚本**（默认 **Alt+X**）。本文件包含建 schema、建表和验收查询，要执行整个脚本；不要只执行光标所在的单条语句。
3. 等最后的 **21 行检查结果**出现，再将完整结果截图发回；一张放不下可分两张。

助手已在独立临时数据库验证全部数据，建表约 49 秒，最终对账约 38 秒；这是本次环境的实测时间，你的 DBeaver 耗时可能不同。建表会新增一个大型事实表，完成前请等待查询结束。无需重新导入来源文件。

如果提示表已经存在，不要删除或重复创建：只选择文件中 `-- VALIDATION:` 下面的完整 WITH 查询执行即可。若出现 FAIL、INCOMPLETE 或报错，保留结果发回，该步保持未验收。

## 预期结果

前 20 行应为 PASS，第 21 行为 INFO。INFO 是金额汇总观察值；若前面的必要检查失败，它会显示 INCOMPLETE，不能作为已验收金额使用。

| check_name | 助手全量预查结果 | status |
| --- | ---: | --- |
| fact_rows | 59181090 | PASS |
| column_count | 9 | PASS |
| schema_mismatch_count | 0 | PASS |
| total_units | 66927173 | PASS |
| zero_sales_rows | 40241819 | PASS |
| priced_daily_rows | 46881677 | PASS |
| missing_price_zero_rows | 12299413 | PASS |
| missing_price_positive_rows | 0 | PASS |
| missing_core_rows | 0 | PASS |
| invalid_fact_rows | 0 | PASS |
| fact_series_count | 30490 | PASS |
| fact_key_coverage_errors | 0 | PASS |
| source_key_coverage_errors | 0 | PASS |
| series_set_difference_rows | 0 | PASS |
| units_mismatch_series | 0 | PASS |
| dimension_key_errors | 0 | PASS |
| calendar_field_mismatches | 0 | PASS |
| price_field_mismatches | 0 | PASS |
| coverage_flag_mismatches | 0 | PASS |
| amount_mismatches | 0 | PASS |
| total_estimated_sales_value | 191577546.04 | INFO |

验收不仅看总销量是否相同：每个商品门店组合的 1,941 天都会检查完整性并逐值核对；日期、周、价格、覆盖标记和金额也重新从来源映射计算后比较。详见 [验证说明](SALES_FACT_VALIDATION.md)。

当前 GitHub 记录明确区分“助手预验证通过”与“等待你执行确认”。事实表通过验收后，再进入商品结构和贡献分析；暂不把预查总额当作业务分析结论。
