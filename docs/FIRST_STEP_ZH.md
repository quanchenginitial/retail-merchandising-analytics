# 当前一步：检查销量与三张维度表的完整关联

更新日期：2026-10-27（Australia/Sydney）。

**这一步为了什么：确认每条销量都能找到对应商品、门店和日期，且关联后不漏行、不增加行、不改变销量，为后续按商品分类、地区和时间汇总提供可信基础。**

你的最新截图中，日历维度 17 项全部 PASS。商品、门店、日历三张维度表已完成单表验收，见 [阶段记录](DIMENSIONS_CHECKPOINT.md)。

## 为什么还需要检查关联

一张表单独正确，不等于连接后的结果一定正确。如果某个商品编号找不到分类，该商品会无法归类；如果维度表同一个编号出现两行，连接就可能让销量重复计算。

本次实际执行三类关联：

| 销量字段 | 关联维度 | 后续分析用途 |
| --- | --- | --- |
| item_id | core.m5_product | 商品、部门、类别汇总 |
| store_id | core.m5_store | 门店、州汇总 |
| d | core.m5_calendar | 日期趋势、周编号对应 |

查询使用 LEFT JOIN 保留未匹配的销量行，再明确统计缺失匹配。只看总销量不够：零销量行即使找不到日期，总销量也可能完全不变。因此还会检查零销量行数和各门店的行数、销量。

## 本次只执行这一份查询

1. 打开 [15_audit_sales_dimension_joins.sql](../sql/15_audit_sales_dimension_joins.sql)，复制全部内容。
2. 在 DBeaver 当前 retail_merchandising 连接中新建 SQL 编辑器，粘贴、全选后执行（默认 Ctrl+Enter）。
3. 等最终 20 行检查结果出现，把完整结果截图发回；可放大结果区以显示全部检查。

这是一条只读查询，可以重复运行。本步扫描完整销量长表，等待结束即可。助手已在独立临时数据库通过全部 20 项检查及 15 个针对性用例；这次独立关联审计耗时约 6 秒，实际耗时因环境而异。详见 [验证说明](DIMENSION_JOINS_VALIDATION.md)。

## 预期结果

所有 20 行 status 均为 PASS。

| check_name | 预期 |
| --- | ---: |
| product_rows | 3049 |
| store_rows | 10 |
| calendar_rows | 1969 |
| base_rows | 59181090 |
| joined_rows | 59181090 |
| row_count_difference | 0 |
| base_units | 66927173 |
| joined_units | 66927173 |
| units_difference | 0 |
| base_zero_rows | 40241819 |
| joined_zero_rows | 40241819 |
| missing_product_rows | 0 |
| missing_store_rows | 0 |
| missing_calendar_rows | 0 |
| source_missing_core_rows | 0 |
| source_negative_units_rows | 0 |
| invalid_joined_day_rows | 0 |
| first_sales_date | 2011-01-29 |
| last_sales_date | 2016-05-22 |
| store_control_mismatches | 0 |

base 表示关联前，joined 表示关联后。三类 missing 行数都应为 0；整体和各门店的行数、销量、零销量行应保持一致。日期只覆盖已有销量的 1,941 天，日历后续 28 天不会被当作已有销售。

查询先检查三张小维度表的键及必要属性。如果出现重复键、空键或缺少必需属性，会报错停止，避免放大销量行数。若报错或出现 FAIL，保留现状并发回；不要通过删除销量行或随意去重让结果通过。必须全部 20 项通过，单独看到总销量正确并不足够。

本步依赖此前已验收的销量值和维度含义，不重新做逐格来源对账，也没有创建保存关联结果的新事实表。

## 通过后

下一步检查每天的销量能否找到对应的商品门店周价格，明确缺价分布，再决定销售金额代理指标的可计算范围与事实表字段。
