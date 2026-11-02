# 当前一步：导入 Retailrocket 类别原始表

更新日期：2026-11-02（Australia/Sydney）。

**这一步为了什么：保存“类别—父类别”关系，为后续按类别汇总浏览、加购与交易行为建立分类依据。**

## SQL54 已验收

18 个 PASS 和全部可见数值匹配冻结报告。截图中 54 个整数值、18 个状态及 14 个完整名称，共 86 个字段完全可见；第 9/16/17/18 行名称末尾截断，已结合可见前缀、固定行号与 SQL 契约确认，无需重跑。详见 [事件导入验收](RETAILROCKET_EVENTS_IMPORT_VALIDATION.md)。

事件表保留 2,756,101 条记录及 460 条重复冗余记录，来源与表的双向差异为零。原始重复保留不代表去重策略已确定；交易事件数也不等于订单数。

## 认识类别表

| 字段 | 含义与本步处理 |
| --- | --- |
| categoryid | 当前类别编号，保留原始文本 |
| parentid | 上一级类别编号，保留原始文本；原文件为空时保存为 NULL |

这张表有 1,669 行，描述类别关系，不是 1,669 个商品。25 个空父编号保留为根类别候选，不补 0。类别与商品的对应关系将通过后续商品属性表建立，事件表本身没有类别字段。

## 现在执行 SQL55

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [55_import_retailrocket_categories.sql](../sql/55_import_retailrocket_categories.sql)，执行整个脚本。
3. 核对最后 **15 行、5 列**结果，提供完整截图；预期全部 PASS。列为 check_order、check_name、actual、expected、status，可将名称列适当拉宽。

脚本创建 rr_raw.category_tree，两列均为 VARCHAR。重点检查：row_count 和 distinct_categoryids 均为 1,669；column_count 和 varchar_column_count 均为 2；null_parentid_rows 为 25；其余问题计数与来源差异计数均为 0。

如果该表已经成功创建，只运行 SQL 中 CHECKS 标记之后的查询。脚本不会覆盖已有表，SQL54 的事件无需重新导入。出现 FAIL 时先保留结果并检查原因。

## 本步验证了什么

助手已在隔离环境试运行，使用独立 Python CSV 多重集合核对全部 1,669 行、2 个字段，并检查原始重复、空值与文字格式保留。记录及针对性验证见 [类别导入验证](RETAILROCKET_CATEGORIES_IMPORT_VALIDATION.md)。这与用户实际执行验收分开记录，助手未打开用户的持久数据库。

本步核对原始导入、直接父键引用和自身指向；尚未检查多节点环路、完整层级深度或根路径，不能因此宣布整个类别树结构已验证。两份属性文件、类型化清洗、时点属性连接及行为指标在后续分步推进。M5 与 Retailrocket 的编号不互相连接。
