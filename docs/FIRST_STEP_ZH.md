# 当前一步：按首次浏览的历史可用性记录比较路径

更新日期：2026-11-09（Australia/Sydney）。

**这一步为了什么：观察类别 1613 在不同历史可用性记录下的加购与交易路径，同时保留记录不足的组合，为后续排查提供线索。**

## SQL76 已验收

截图 **5 行 × 10 列、50 个字段完整匹配，五行全部 PASS**，四个 NULL 保留。总计 1,161 个商品，包含 1,010 个零加购商品和 151 个有加购商品；加权交易/加购比率为 **15.7350%**，有加购商品的等权均值为 **14.6612%**。空的 CART_20_PLUS 档正常保留零计数和 NULL，比率差异本身不证明原因；见 [验收记录](RETAILROCKET_CATEGORY_ITEM_CART_CONCENTRATION_VALIDATION.md)。

## SQL77 怎样分组

仍使用首次浏览类别为 **1613** 的同一 7 天合格访客—商品组合。按该组合**首次浏览时、时间不晚于浏览的最后一条 available 历史记录**分组：

| availability_status | 含义 |
| --- | --- |
| RECORDED_1 | 匹配到的历史 available 值为 1 |
| RECORDED_0 | 匹配到的历史 available 值为 0 |
| BEFORE_FIRST | 首次浏览早于该商品最早的 available 记录 |
| NO_HISTORY | 该商品没有 available 历史记录 |
| TOTAL | 上述四组总计 |

类别与可用性都固定在首次浏览时，后续状态变化不重新分组。未知状态不使用未来记录或其他商品填补。每个合格访客—商品组合在首次浏览时刻的全部浏览记录，必须分别具有一致的类别与可用性信息；严格的浏览→加购→交易顺序和同一个 7 天期限保持不变。

## 怎样阅读九列结果

availability_status 后面是 eligible_pairs、cart_pairs、transaction_pairs 三阶段组合数，再加四个百分比与 check_status：

- **eligible_share_pct**：100 × 本组合格数 ÷ 类别 1613 的全部合格数。
- **cart_rate_pct**：100 × 本组加购数 ÷ 本组合格数。
- **transaction_rate_pct**：100 × 本组交易数 ÷ 本组合格数。
- **cart_to_transaction_rate_pct**：100 × 本组交易数 ÷ 本组加购数。

四组计数相加应还原 TOTAL 的 **25,105 个合格、483 个加购、76 个交易组合**。零分母对应 NULL，不替换为 0；空组也保留。比率使用各自分母，不能直接相加或简单平均。这里的组合数不是点击次数、实际人数或核验订单数。

## 现在执行 SQL77

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [77_analyze_retailrocket_category_availability_funnel.sql](../sql/77_analyze_retailrocket_category_availability_funnel.sql)，完整执行查询。
3. 提供 **5 行、9 列完整结果**，预期全部 PASS。拉宽字段名并保留 NULL；若需横向拆成两张，两张都保留 **availability_status 和全部五行**。

这是只读查询，可以完整重复执行，无需重新导入 CSV 或建表。助手预检已通过，用户执行及截图验收仍待完成；见 [验证说明](RETAILROCKET_CATEGORY_AVAILABILITY_FUNNEL_VALIDATION.md)。

## 验证与解释范围

本次验证从此前的 **10 个事件/类别字段扩大为 15 个事件/类别/可用性字段**。助手从四份 CSV 重建 categoryid 与 available 两种历史，共 2,291,853 条命名属性记录；不重验事实表已有 UTC 派生字段、完整十七字段、类别层级或此前整套分析。

RECORDED_0/1 表示最后已记录的历史状态，**不能直接当作浏览当刻真实库存、顾客实际看到的状态或缺货原因**。BEFORE_FIRST/NO_HISTORY 表示分析资料的覆盖不足，不证明网站发生故障。类别 1613 是根据先前结果选出的，仍属探索性追查；组间路径差异不是因果效果或独立确认。公开内容只有状态分组统计，不含访客、商品、交易编号或原始属性历史。
