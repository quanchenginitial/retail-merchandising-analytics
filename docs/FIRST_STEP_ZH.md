# 当前一步：导入 Retailrocket 原始事件表

更新日期：2026-11-02（Australia/Sydney）。

**这一步为了什么：把浏览、加购和交易事件完整载入数据库，保留原始值，为后续类型转换、去重与行为分析建立可追溯的起点。**

## 四份来源文件已核验

| 文件 | 实际数据行数（不含表头） | 字段数 |
| --- | ---: | ---: |
| events.csv | 2,756,101 | 5 |
| item_properties_part1.csv | 10,999,999 | 4 |
| item_properties_part2.csv | 9,275,903 | 4 |
| category_tree.csv | 1,669 | 2 |

只读结构审计 38/38 检查通过：严格 CSV/UTF-8 解析、表头与每行列数、必填与可选空值、标识及毫秒时间戳的基本格式等均有记录。四份文件大小与官方版本 2 清单一致，扫描前后 SHA-256 未变。本地指纹用于固定本次快照，不等于官方文件认证。详见 [来源审计](RETAILROCKET_SOURCE_AUDIT.md)。

独立事件检查发现 460 条重复冗余行，按五个解析字段完全相同计算；原始层全部保留。2,733,644 条浏览或加购事件的交易编号为空，22,457 条交易事件均有编号；不要把正常的空交易编号补成 0。交易事件数不等于去重订单数。事件时间范围按 Unix 毫秒转 UTC 为 2015-05-03 至 2015-09-18，原始层暂不转换时间。

## 现在执行 SQL54

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [54_import_retailrocket_events.sql](../sql/54_import_retailrocket_events.sql)，执行整个脚本。
3. 核对最后的 **18 行、5 列**检查结果，提供完整截图。列为 check_order、check_name、actual、expected、status。

脚本只建立新的 rr_raw.events 表，五列依次为 timestamp、visitorid、event、itemid、transactionid，均保留 VARCHAR。Retailrocket 使用单独的 rr_raw 命名空间，不与 M5 连接编号。两份属性及类别文件将在后续分别加载。

预期所有检查为 PASS。其中 row_count 为 2,756,101，column_count 与 varchar_column_count 均为 5；三类事件分别为 view 2,664,312、addtocart 69,332、transaction 22,457；两个方向的来源差异计数均为 0；duplicate_surplus_rows_preserved 的 actual 与 expected 均为 **460**。这最后一项验证原始重复没有被悄悄删除。

脚本不覆盖已有 rr_raw.events。如果已经成功导入，只运行 SQL 文件中 CHECKS 标记之后的核对查询即可，不要重复创建或删除表。出现 FAIL 时保留结果，先查原因再推进。

## 验证边界

助手已在隔离环境运行 SQL54 并核对完整来源与导入表的多重集合，包含重复次数。针对重复及空值保留、重复丢失和差异检测的验证见 [导入验证说明](RETAILROCKET_EVENTS_IMPORT_VALIDATION.md)。没有打开用户的持久数据库，用户执行与截图验收仍待完成。

本步不确定去重策略，不构建会话、漏斗、RF 或购物篮指标。原始事件、访客明细、来源 CSV 和数据库不上传 GitHub；上传 SQL、可复现检查及聚合证据。
