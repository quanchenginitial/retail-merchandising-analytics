# 当前一步：建立门店维度表

更新日期：2026-10-27（Australia/Sydney）。

**这一步为了什么：将每家门店与所属州整理成唯一对应关系，支持后续比较各门店、各地区的销量表现，避免关联时重复计算或归错地区。**

你的最新截图中，商品维度 15 项全部 PASS：3,049 个唯一商品、3 列、7 个部门、3 个类别，来源对应关系及商品键关联检查通过。见 [商品验收记录](../data/product_dimension_learner_acceptance.json)。

## 门店维度表是什么

商品维度提供商品分类，门店维度提供销售地点的州归属。以后销量表通过 store_id 连接这张表，就能按门店或州汇总。

raw.m5_sales_wide 中，同一家门店会随不同商品重复出现。本步合并完全相同的 store_id、state_id 对应关系，建立 10 家门店各一行的 core.m5_store。

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| store_id | VARCHAR | 来源门店编号，每个编号一行 |
| state_id | VARCHAR | 来源州编号 |

一个州可以有多家门店，但一家门店必须只对应一个州。州归属直接读取原始 state_id；原始代码保留不变。若来源出现缺失、空代码或同店多州，脚本会报错。

## 本次只执行这一份脚本

1. 打开 [13_build_store_dimension.sql](../sql/13_build_store_dimension.sql)，复制全部内容。
2. 在 DBeaver 当前 retail_merchandising 连接中新建 SQL 编辑器，粘贴后使用“执行 SQL 脚本”（默认 Alt+X），运行整份脚本一次。
3. 等最终 13 行检查结果出现，把完整结果截图发回。

助手已在独立临时内存数据库验证完整来源：13 项检查及 11 个针对性用例全部通过。来源确认州分布为 CA 4 家、TX 3 家、WI 3 家，详见 [验证说明](STORE_DIMENSION_VALIDATION.md)。

## 预期结果

所有 13 行 status 均为 PASS。

| check_name | 预期 |
| --- | ---: |
| store_rows | 10 |
| column_count | 2 |
| schema_mismatch_count | 0 |
| distinct_stores | 10 |
| duplicate_or_null_store_rows | 0 |
| missing_required_rows | 0 |
| distinct_states | 3 |
| raw_missing_required_rows | 0 |
| raw_store_mapping_conflicts | 0 |
| raw_only_store_rows | 0 |
| dimension_only_store_rows | 0 |
| source_key_join_errors | 0 |
| state_store_count_mismatches | 0 |

这些检查共同确认一门店一行、州归属无冲突、没有遗漏或新增门店、字段与来源精确一致，并且每个来源门店键都匹配恰好一行。唯一性由查询验证，本步未建立物理主键约束。

source_key_join_errors 检查的是小型来源门店键集合；完整日销量连接会另行验收。若表已存在，只执行 VALIDATION 注释之后的 WITH 查询。其他报错或 FAIL 请保留现状发回，不删除表或手动选择冲突州。

## 通过后

接下来完成日历维度，再逐步检查销量与各维度、价格的关联，核对行数、销量和价格覆盖后开展分析。
