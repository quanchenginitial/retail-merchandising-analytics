# 当前一步：建立候选篮子商品成员表

更新日期：2026-11-13（Australia/Sydney）。

**这一步为了什么：把“同一个候选篮子里出现过哪些商品”固定为每个商品成员一行，同时保留原事件出现次数，为后续共同购买分析准备一致的粒度。**

## SQL78 已验收

截图 **21 行 × 5 列、105 个字段完整匹配**，八项 PASS、十三项 INFO；十三个 expected=NULL 正常保留。22,457 条 transaction 事件对应 **17,672 个候选篮子、22,323 个独立篮子/商品成员关系**。其中 123 个成员关系出现多次，共多出 134 条记录；它们不是已核实的购买件数，也不自动构成错误。

候选篮子包含 **15,029 个单商品组、2,643 个多商品组**，最大 31 个不同商品。下一步会保留这些单商品组，避免只留下多商品篮子而改变后续分析的分母。

## SQL79 新表记录什么

从现有 rr_stg.events 建立 **rr_mart.transaction_basket_items**，每个 (visitorid, transactionid, itemid) 成员关系一行，六个字段均为 BIGINT：

| 字段 | 含义 |
| --- | --- |
| visitorid | 原匿名访客编号 |
| transactionid | 原交易编号；与 visitorid 一起组成候选篮子键 |
| itemid | 该候选篮子中出现的商品编号 |
| first_timestamp_ms | **这个商品成员关系**最早一次交易事件的毫秒时间戳 |
| last_timestamp_ms | **这个商品成员关系**最后一次交易事件的毫秒时间戳 |
| source_event_rows | 该成员关系在来源中出现的事件次数，**不是购买数量** |

首末时间属于每个商品成员，不是整个篮子的开始、结束或付款时间。本步使用全部 transaction 事件，不沿用类别 1613 或 7 天漏斗的筛选，也不要求先有可见浏览和加购。原始事件不删除，关联规则尚未计算。

## 现在执行 SQL79

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [79_build_retailrocket_transaction_basket_items.sql](../sql/79_build_retailrocket_transaction_basket_items.sql)。**第一次完整执行脚本**，包括建表部分和后面的检查部分；无需重新导入 CSV。
3. 提供 **21 行、5 列完整检查结果，预期全部 PASS**。列为 check_order、check_name、actual、expected、status；请拉宽 check_name。若拆图，保留 check_order/check_name，并让相邻截图有重叠行。

预期成员表 **22,323 行、17,672 个候选篮子**，source_event_rows 合计 **22,457**；重复成员 123 个、额外出现次数 134，单/多商品篮子数量与 SQL78 一致。

本步会创建新表。输入未通过校验时不会创建该成员表；**目标表已存在会拒绝覆盖**。如果你已经成功建表，之后只执行文件 **CHECKS 标记以下的检查段**，不要默认删除、重建或重复执行建表部分。

助手预检已通过，用户建表和截图验收仍待完成；见 [验证说明](RETAILROCKET_TRANSACTION_BASKET_ITEMS_VALIDATION.md)。

## 验证和解释范围

助手仅从 **events.csv** 独立核对原始五字段，并逐行核对新表全部 **22,323 行 × 6 字段**；不重跑属性历史、十五字段连接、UTC 派生、类别层级或此前整套分析。候选篮子是明确约定的分析单位，不代表已核实的真实订单、人数、件数或金额。公开保存汇总检查结果，不上传访客、商品、交易编号或成员明细。RF 分群、共同购买规则及 Power BI 仍未完成。
