# 当前一步：建立类型化日历清洗表

更新日期：2026-10-27（Australia/Sydney）。

你的最新价格审计截图 15 项全部 PASS。三张原始表的导入与详细审计已经完成：日历 17 项、销量 15 项、价格 15 项，共 47 项详细检查通过。

## 从原始层进入清洗层

raw 保留来源原值，方便追溯。stg 是清洗层，让字段具备适合计算和连接的类型。今天只建立 stg.m5_calendar，不转换销量或价格表。

| 字段 | 清洗层类型 | 用途 |
| --- | --- | --- |
| date | DATE | 日期筛选、日期差与时间分析 |
| wm_yr_wk、wday、month、year、snap_CA、snap_TX、snap_WI | INTEGER | 周编号连接、年月筛选与 0/1 标记运算 |
| weekday、d、event_name_1、event_type_1、event_name_2、event_type_2 | VARCHAR | 保留名称、来源日编号和事件文本 |

仍然保留 14 列、1,969 行，事件字段的 NULL 不补成 0 或空字符串。日历保留至 2016-06-19，不截到销量末日；这不表示我们拥有最后 28 天的真实销量。周编号按来源转换，不重新计算为公历周。

## 本次只执行这一份脚本

1. 打开 [08_stage_calendar.sql](../sql/08_stage_calendar.sql)，复制全部内容。
2. 在 DBeaver 当前 retail_merchandising 连接中粘贴，使用“执行 SQL 脚本”（默认 Alt+X）运行整份脚本一次。
3. 等待最后 13 行结果，把截图发回。

脚本创建 stg.m5_calendar，不改动 raw.m5_calendar。它使用 CAST 转换类型；转换错误会报错，不会用 TRY_CAST 静默生成 NULL。类型转换后还会回转为文本，与原始表逐行对账，检查是否改变了原值。

## 预期结果

所有 13 行 status 均为 PASS。

| check_name | 预期 |
| --- | ---: |
| staging_rows | 1969 |
| column_count | 14 |
| schema_mismatch_count | 0 |
| distinct_dates、distinct_day_ids | 各 1969 |
| missing_core_rows | 0 |
| first_date | 2011-01-29 |
| last_date | 2016-06-19 |
| invalid_snap_rows | 0 |
| event_1_nulls | 1807 |
| event_2_nulls | 1964 |
| raw_only_rows、staging_only_rows | 各 0 |

schema_mismatch_count 会逐列核对名称、类型与顺序，不是只看类型数量。最后两项均为 0，表示转换后的记录还原成文本后，与当前 raw 日历完全一致，包含事件 NULL 和重复次数；此处比较对象是 raw 表，不重新读取 CSV。

如果提示表已存在，不要删表，只运行 VALIDATION 注释之后的 WITH 查询即可。其他报错或 FAIL 请保留现状并发回结果。

## 当前验收范围

助手在独立临时数据库中预验证 13/13 PASS，详见 [验证说明](CALENDAR_STAGING_VALIDATION.md)。用户创建清洗表仍待当前截图确认。

这是类型化清洗表，尚未建立最终 core 日历维度、主键约束、销量长表或日级价格覆盖。本步通过后，再继续其余清洗与建模步骤。
