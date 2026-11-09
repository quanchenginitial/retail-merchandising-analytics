# 当前一步：比较两个首次浏览时间队列

更新日期：2026-11-09（Australia/Sydney）。

**这一步为了什么：把整体类别路径拆成两个首次浏览时间段，保持同一组类别与同样的 7 天规则，检查类别差异是否在不同时间段中仍然出现。**

## SQL74 已验收

截图 **15 行 × 9 列、135 个字段完整匹配，15 行全部 PASS**，八个 NULL 保留。各组计数合计仍为 **2,042,310 个合格、43,147 个加购、15,520 个交易组合**，与 SQL72/73 对账通过；见 [分类别路径验收](RETAILROCKET_CATEGORY_7DAY_FUNNEL_VALIDATION.md)。

## SQL75 怎样划分时间

只根据同一访客—商品组合的**首次观测浏览时间**划分：

| cohort | 首次观测浏览的 UTC 时间 |
| --- | --- |
| EARLY | 早于 2015-07-01T00:00:00Z |
| LATE | 从上述分界时刻开始，至原有合格截止 2015-09-11T02:59:47.788000Z |

恰好落在分界时刻的组合属于 LATE。后续加购和交易仍须严格按顺序、在各自首次浏览加 7 天的同一个含终点窗口内；**后续事件可以跨过 7 月 1 日，组合仍留在首次浏览决定的队列**。这里没有按事件发生月份重新分组。

两组固定沿用 SQL74 从全体合格组合选出的**同一组 Top10 类别及同一顺序**，不各自重新排名。某类别在一组中即使没有组合，也保留该行。OTHER_MAPPED、三个未知桶和 TOTAL 也都保留。

## 怎样阅读结果

结果在 SQL74 的九列前增加 **cohort**，共 **10 列**。EARLY 和 LATE 各 15 行，总共 **30 行**。其余字段含义不变：

- eligible_pairs、cart_pairs、transaction_pairs：本队列、本分组的三阶段组合数。
- cart_rate_pct：100 × 本行 cart_pairs ÷ eligible_pairs（%）。
- transaction_rate_pct：100 × 本行 transaction_pairs ÷ eligible_pairs（%）。
- cart_to_transaction_rate_pct：100 × 本行 transaction_pairs ÷ cart_pairs（%）。

分母为 0 的比率保留 NULL。每个队列内，不含 TOTAL 的计数汇总为该队列 TOTAL；**相同 segment/categoryid 在 EARLY 与 LATE 的计数相加，应还原 SQL74 对应行**。比率不能直接相加，也不能用简单平均还原总比率。

## 现在执行 SQL75

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [75_analyze_retailrocket_category_funnel_time_cohorts.sql](../sql/75_analyze_retailrocket_category_funnel_time_cohorts.sql)，完整执行查询。
3. 提供 **30 行、10 列完整结果**，预期全部 PASS。可以按 EARLY/LATE 分两张截图，每张 15 行；若列太宽还需横向拆分，请保留 **cohort、segment、categoryid 和该队列的全部 15 行**，并保留 NULL。

这是只读查询，可以完整重复执行，无需重新导入 CSV 或建表。

## 验证与解释范围

助手预检已通过，用户执行与截图验收仍待完成；见 [时间队列验证说明](RETAILROCKET_CATEGORY_FUNNEL_TIME_COHORTS_VALIDATION.md)。本次保持事件/类别十字段和参考编号的范围，不重验可用性字段、事实表已有 UTC 派生字段、整个事实表或类别层级，也不重跑此前整套验证。

两个首次浏览区间长度不同，组合构成和记录覆盖也可能不同。比较比率时同时查看分母，不能把后一队列原始计数更高直接称为增长。这是探索性的时间分组比较，不是显著性检验，不能仅凭差异认定季节性或因果关系。固定同一组匿名类别标签便于逐项比较，但不会自动消除组内商品构成差异。未知桶仍表示分析历史覆盖，并不证明网站对顾客缺少分类；公开内容仅含分组后的类别代码及统计，不含原始访客、商品、交易编号或类别历史明细。
