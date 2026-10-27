# 当前一步：建立日历维度表

更新日期：2026-10-27（Australia/Sydney）。

**这一步为了什么：把销量日编号对应到真实日期、数值日序及来源周编号，支持按时间分析销量，并为后续匹配周价格提供依据。**

你的最新截图中，门店维度 13 项全部 PASS：10 家唯一门店、2 列、3 个州，来源对应关系与州门店数检查均通过。见 [门店验收记录](../data/store_dimension_learner_acceptance.json)。

## 本次在已有日历基础上做什么

已验收的 stg.m5_calendar 保留了转换好类型的 14 个来源字段。本次建立分析使用的 core.m5_calendar，保留这 14 列，增加 day_number，并核对日编号、日期及日序是否一一对应。

| 字段 | 示例 | 本步用途 |
| --- | --- | --- |
| d | d_1 | 与销量长表的来源日编号连接 |
| date | 2011-01-29 | 按真实日期、月份和年份分析 |
| day_number（新增） | 1 | 按数值顺序排序，检查观测区间 |
| wm_yr_wk | 保留来源周编号 | 后续匹配商品门店周价格 |

新表共 15 列。日序号从 d 后面的数字提取，再独立与日期差核对，避免按文字排序时 d_10 跑到 d_2 前面。来源周编号和星期编号保留原定义。

日历保留全部 1,969 天。现有销量覆盖前 1,941 天，截止 2016-05-22；之后 28 天只有日历信息，本步不会为这些日期生成销量或补零。后续模型验证仍会使用更早的切分点。

## 本次只执行这一份脚本

1. 打开 [14_build_calendar_dimension.sql](../sql/14_build_calendar_dimension.sql)，复制全部内容。
2. 在 DBeaver 当前 retail_merchandising 连接中新建 SQL 编辑器，粘贴后使用“执行 SQL 脚本”（默认 Alt+X），运行整份脚本一次。
3. 等最终 17 行检查结果出现，把完整结果截图发回。

助手已在独立临时内存数据库验证：完整数据 17 项检查和 13 个故障用例全部通过，详见 [验证说明](CALENDAR_DIMENSION_VALIDATION.md)。

## 预期结果

所有 17 行 status 均为 PASS。

| check_name | 预期 |
| --- | ---: |
| calendar_rows | 1969 |
| column_count | 15 |
| schema_mismatch_count | 0 |
| distinct_dates | 1969 |
| distinct_day_ids | 1969 |
| distinct_day_numbers | 1969 |
| missing_core_rows | 0 |
| invalid_day_mapping_rows | 0 |
| first_date | 2011-01-29 |
| last_date | 2016-06-19 |
| distinct_weeks | 282 |
| observed_sales_days | 1941 |
| post_observation_days | 28 |
| observed_last_date | 2016-05-22 |
| stg_only_rows | 0 |
| core_only_rows | 0 |
| source_key_join_errors | 0 |

检查共同确认日期键唯一且完整、原 14 个字段与清洗层精确一致、事件空值保留，以及新增日序与日编号和真实日期相符。

observed_sales_days 和 post_observation_days 是按已验收的销量快照边界统计日历行数；本步没有重新扫描销量或验收完整销量连接。唯一性由查询检查，未建立物理主键约束。

若表已存在，只执行 VALIDATION 注释之后的 WITH 查询。其他报错或 FAIL 请保留现状发回，不删除日期或改填销量。

## 通过后

接下来检查销量与商品、门店、日历的完整关联，确认每条记录都能正确匹配，且行数和销量不变，再检查价格覆盖。
