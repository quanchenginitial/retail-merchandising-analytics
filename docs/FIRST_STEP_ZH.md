# 当前一步：整理商品类别与可用性的历史记录

更新日期：2026-11-06（Australia/Sydney）。

**这一步为了什么：保留商品在不同时间的类别与可用性观察，为后续判断“事件发生时，商品处于什么状态”准备数据。**

## SQL64 已验收

截图 18 行 × 5 列、90 个字段全部完整可见并匹配，包含 15 项 PASS、3 项 INFO、完整 UTC 时间字符串及 3 个 NULL 预期值。见 [事件时间验收](RETAILROCKET_EVENT_TIME_VALIDATION.md)。

2,756,101 条事件的毫秒往返、日期归属和每日计数核对通过，覆盖 139 个有观测的 UTC 日期。首日与末日分别有 13,683 条和 1,528 条事件，2,753,264 条带有非零毫秒部分。这些是事件记录数；起止日期不证明首末日全天采集，也不代表商家本地营业日。

## SQL65 做什么

从现有 rr_raw.item_properties 中选出含义明确的两类属性：**categoryid（类别）**和 **available（可用性）**，保存为 **rr_stg.item_state_observations**。

| 字段 | 保存类型 | 含义 |
| --- | --- | --- |
| timestamp | BIGINT | 这条属性观察的原始时间戳数值 |
| itemid | BIGINT | 匿名商品编号 |
| property | VARCHAR | categoryid 或 available |
| value | VARCHAR | 属性值原文；保持文本 |
| source_file | VARCHAR | 原始属性文件来源 |

本步整理 **2,291,853 条历史观察**，包括 **788,214 条类别记录**和 **1,503,639 条可用性记录**。一行代表某个商品、某项属性、某个时间的观察，不是一件独立商品。同一商品可能有多次历史记录，保留它们才能在后续讨论过去某一时点的状态。

只有时间戳和商品编号转换为整数；属性值保持原文，包括类别值原有的写法。可用性的 0/1 是数据发布方记录的状态，不是库存数量。其余 17,984,049 条含义未解释的属性继续保留在原始表。

本步尚不生成状态有效期或匹配行为事件，也不修复此前发现的 167 条未匹配类别属性。分文件选中行数会显示为两个 **INFO** 观测，expected 为 NULL；只有 20 项检查全部通过，才会发布这些观测值。

## 现在执行 SQL65

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 首次打开 [65_stage_retailrocket_item_state_observations.sql](../sql/65_stage_retailrocket_item_state_observations.sql)，执行整个脚本，建立商品状态观察表。
3. 查看最后 **22 行、5 列**结果，预期 **20 项 PASS、2 项 INFO**。请拉宽 check_name 列后提供完整截图，保留 INFO 行的 NULL 预期值。

脚本采用普通 CREATE，已有表不会被覆盖。如果提示 rr_stg.item_state_observations 已存在，保留该表，只执行 **-- CHECKS:** 标记之后的检查查询。

本步读取已有原始属性表，不需要重新导入 CSV 或重新执行 SQL56–64。

## 验证及后续

助手隔离预检已通过，用户执行与截图验收仍待完成；方法与实测范围见 [商品状态观察验证说明](RETAILROCKET_ITEM_STATE_OBSERVATIONS_VALIDATION.md)。助手未打开用户的持久数据库。

后续将继续验证属性时间、历史有效期及事件时点关联，再计算相应行为指标。
