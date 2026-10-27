# 当前一步：导入日历原始表

更新日期：2026-10-27（Australia/Sydney）。

你的截图已经确认 `database_name = retail_merchandising`、`duckdb_version = v1.5.5`。连接检查通过。三份 CSV 的源文件审计也已完成，详见 [审计结果](M5_SOURCE_AUDIT.md)。本次只导入最小的日历文件。

## 为什么先做这一步

日历将销量文件中的 d_1、d_2 等编号对应到真实日期，并提供周编号、事件和 SNAP 标志。先把它导入 raw 原始层，保留所有列为 VARCHAR 文本；类型转换放到后续清洗层。CSV 中的空白字段读为 SQL NULL，表示没有记录对应事件，不填成数字 0。

## 操作

1. 确认编辑器顶部当前连接仍为 **retail_merchandising**。
2. 打开 [02_import_calendar.sql](../sql/02_import_calendar.sql)，将完整内容放入当前 SQL 编辑器。
3. 使用 **执行 SQL 脚本**（DBeaver 默认快捷键 Alt+X）按顺序运行全部语句。普通的单语句执行可能只运行光标所在语句。

脚本先创建 raw 分区，再创建 `raw.m5_calendar` 并读取文件，最后输出一行检查结果。输入文件保持在 `D:/database/m5-forecasting-accuracy/calendar.csv`。完成后，可刷新左侧数据库树查看新表。

## 预期结果

| 字段 | 预期值 |
| --- | --- |
| database_name | retail_merchandising |
| row_count | 1969 |
| column_count | 14 |
| varchar_column_count | 14 |
| distinct_day_ids | 1969 |
| first_date | 2011-01-29 |
| last_date | 2016-06-19 |

把这一行结果发回来即可。如果出现报错，先停在报错处，提供报错内容。若提示表已存在，只运行文件末尾的 SELECT 检查语句，不删除表，也不重复导入。

## 已验证与待验证

助手已在独立的临时数据库中运行同一 SQL，得到预期的行数、列数、类型数量、日编号数量和日期范围，见 [预验证记录](../data/calendar_import_preflight.json)。其中 database_name 为 memory，因为它是临时验证环境。没有操作你正在连接的数据库。你的实际导入结果仍待截图验收。

基础检查通过后，再检查日历字段和源文件是否一致，然后进入另外两份文件；暂不进行预测、指标计算或宽转长。
