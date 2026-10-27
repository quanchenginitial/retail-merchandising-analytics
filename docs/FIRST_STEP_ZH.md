# 当前一步：建立商品维度表

更新日期：2026-10-27（Australia/Sydney）。

**这一步为了什么：把每个商品所属的部门和类别整理成唯一的一行，为后续商品贡献、品类汇总和销量波动分析提供统一分类。**

你的最新截图中，逐格对账 15 项全部 PASS：59,181,090 个日销量值全部比较，差异序列和差异单元格均为 0。M5 三张清洗表已完成验收，见 [阶段记录](STAGING_LAYER_CHECKPOINT.md)。

## 维度表是什么

销量长表记录某个商品在某家门店某一天卖了多少；商品维度表描述这个商品属于哪个部门、哪个类别。之后通过 item_id 连接，才能准确按商品分类汇总销量。

原始销量宽表中，同一商品会在不同门店重复出现。本步提取 item_id、dept_id、cat_id，合并完全相同的对应关系，形成 3,049 个商品各一行的 core.m5_product。

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| item_id | VARCHAR | 商品编号；本表每个编号一行 |
| dept_id | VARCHAR | 商品部门编号，即中间分类层级 |
| cat_id | VARCHAR | 商品类别编号，即上层分类 |

原始代码按原样保留。若一个商品对应多个部门/类别，或一个部门对应多个类别，脚本会报错，避免任意选一个分类。这里的“唯一”由验收查询验证，尚未建立物理主键约束。

## 本次只执行这一份脚本

1. 打开 [12_build_product_dimension.sql](../sql/12_build_product_dimension.sql)，复制全部内容。
2. 在 DBeaver 当前 retail_merchandising 连接中新建 SQL 编辑器，粘贴后使用“执行 SQL 脚本”（默认 Alt+X），运行整份脚本一次。
3. 等最终 15 行检查结果出现，把完整结果截图发回。

脚本从已验收的 raw.m5_sales_wide 读取三个分类字段，新建 core.m5_product。助手在独立临时内存数据库中完成了全量来源预验证，15 项检查与 12 个针对性用例均通过，见 [验证说明](PRODUCT_DIMENSION_VALIDATION.md)。

## 预期结果

所有 15 行 status 均为 PASS。

| check_name | 预期 |
| --- | ---: |
| product_rows | 3049 |
| column_count | 3 |
| schema_mismatch_count | 0 |
| distinct_items | 3049 |
| duplicate_or_null_item_rows | 0 |
| missing_required_rows | 0 |
| distinct_departments | 7 |
| distinct_categories | 3 |
| raw_missing_required_rows | 0 |
| raw_item_mapping_conflicts | 0 |
| raw_department_mapping_conflicts | 0 |
| dimension_department_conflicts | 0 |
| raw_only_product_rows | 0 |
| dimension_only_product_rows | 0 |
| source_key_join_errors | 0 |

这些检查共同确认：一商品一行、来源分类没有冲突、没有漏掉或增加商品、三个字段与来源精确一致，而且每个来源商品键都能匹配恰好一行。

source_key_join_errors 只检查小型商品键集合；完整日销量连接会在后续单独验收。若表已存在，只执行 VALIDATION 注释之后的 WITH 查询。其他报错或 FAIL 请保留现状发回，不删除表或手动选择冲突分类。

## 通过后

下一步建立门店维度，随后逐步关联日历和价格，检查关联前后的行数、销量及价格覆盖，再开展商品分析。
