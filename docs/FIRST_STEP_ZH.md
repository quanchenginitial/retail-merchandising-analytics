# 当前一步：合并导入 Retailrocket 商品属性原始表

更新日期：2026-11-02（Australia/Sydney）。

**这一步为了什么：完整保存商品属性的历史变化，为后续把浏览、加购和交易事件关联到当时的商品类别与可用性状态做准备。**

## SQL55 已验收

截图 15 行 × 5 列、共 75 个字段完整可见，均与冻结报告匹配，15 个状态全部为 PASS。类别原始表保留 1,669 行、25 个空父类别，来源双向差异为 0。见 [类别导入验收](RETAILROCKET_CATEGORIES_IMPORT_VALIDATION.md)。多节点环路和完整层级路径仍将在后续检查。

## 为什么合并两份属性文件

两份文件具有相同四个字段，而且时间范围重叠。使用 UNION ALL 把记录上下接起来，保留各自全部历史记录与重复；增加 source_file 标记，便于按原文件核对。这个操作是纵向追加，不是按商品编号做横向连接。

| 文件 | 记录数 |
| --- | ---: |
| item_properties_part1.csv | 10,999,999 |
| item_properties_part2.csv | 9,275,903 |
| 合计 | 20,275,902 |

一行是一条“某时间、某商品、某属性、某值”的记录。同一商品可以有多个属性，并随时间多次出现，因此上述总数不能作为商品数量。

四个原始字段 timestamp、itemid、property、value 均先保留为 VARCHAR；新增的 source_file 也为 VARCHAR。property 和 value 中的数字、空格或组合文本按原样保存，具体含义后续再审计；本步不会把 value 当作价格。保存完整历史后，才能在时点关联时选择事件发生时已知的属性，避免把未来属性用于过去的事件。

## 现在执行 SQL56

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [56_import_retailrocket_properties.sql](../sql/56_import_retailrocket_properties.sql)，执行整个脚本。
3. 等待导入与对账完成，查看最后 **14 行、5 列**检查结果，预期全部 PASS。字段为 check_order、check_name、actual、expected、status；拉宽名称列后提供完整截图。

重点核对：row_count 为 20,275,902；part1_row_count 为 10,999,999；part2_row_count 为 9,275,903；column_count 和 varchar_column_count 均为 5，其余九项问题或差异计数均为 0。

本步处理约两千万条属性记录，会比类别表耗时更长，运行过程中请等待结束，避免重复启动。脚本通过普通 CREATE 创建 rr_raw.item_properties，已有表不会被覆盖。如果原始表已经成功创建，只执行 CHECKS 标记之后的全部语句；该部分会重建当前连接中的临时检查汇总表，并逐项完成来源对账。出现 FAIL 时保留结果再排查。

## 本步验证了什么

助手已完成隔离预检：检查总量、分文件数量、字段顺序和类型、必填字段、时间戳与商品编号格式、来源标记，并逐文件逐字段进行双向 EXCEPT ALL 完整对账，保留重复次数。此前独立 Python 全量来源审计提供结构、行数和哈希证据；本次补充针对性小样例测试，未另做 Python 全量属性元组对比。详见 [属性导入验证](RETAILROCKET_PROPERTIES_IMPORT_VALIDATION.md)。

助手预检与用户实际导入验收分别记录，助手未打开用户的持久数据库。本步保留原始历史，类型化清洗、重复键决策、时点属性关联和行为分析在后续分步完成。
