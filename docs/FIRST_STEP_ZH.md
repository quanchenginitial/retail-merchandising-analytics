# 当前一步：观察调价前后的周销量变化

更新日期：2026-11-02（Australia/Sydney）。

**这一步为了什么：观察同一商品、同一门店发生涨价、降价或价格不变时，相邻两周销量通常怎样变化，为后续调查形成线索。**

SQL45 的 12 行、12 列已验收，全部 PASS。在 335,390 次潜在比较中，335,374 次两端有价，16 次至少一端缺价；涨价 2,060 次、降价 1,736 次，共涉及 3,361 个不同商品门店组合。见 [验收记录](../data/price_variation_learner_acceptance.json)。

之前确认了价格是否变化；SQL46 开始同时观察销量，但本步只做描述性比较。三个价格组中的商品、门店和日期构成可能不同，不能直接将组间差异解释为调价效果。

## 本步怎样计算

沿用同一个十二周窗口，在同一商品、同一门店内比较相邻两周：

`销量变化件数 = 本周销量 − 上周销量`

例如从 10 件到 13 件，变化为 +3 件；从 0 件到 5 件，变化为 +5 件。零销量周也参与统计。本步没有除以上周销量，因此不会把零基数变化写成无限增长率。

按价格变化分成 UP（涨价）、DOWN（降价）、UNCHANGED（不变）、MISSING_ENDPOINT（至少一端缺价），另加 TOTAL。缺价记录单独列示，不补价、不跨过缺价周，也不当作价格不变。

## 这次执行 SQL46

1. 打开 [46_price_sales_association.sql](../sql/46_price_sales_association.sql)，复制全文。
2. 在 DBeaver 的 **retail_merchandising** 连接中新建编辑器，粘贴并使用 **执行 SQL 脚本 / Execute SQL Script（默认 Alt+X）**。
3. 发回 **5 行、12 列**结果截图，包含最右侧 check_status。

本步是只读查询，不新增分析表。助手独立预检已通过，用户 SQL46 仍待执行与截图验收。

## 怎样读结果

| 字段 | 含义 |
| --- | --- |
| price_direction | 价格变化组；TOTAL 为所有比较 |
| transitions | 该组相邻周比较次数 |
| distinct_pairs | 该组涉及的不同商品门店组合数 |
| previous_units / current_units | 各次比较的上周 / 本周销量之和 |
| unit_difference | 本周销量合计减上周销量合计，单位为件 |
| mean_unit_change | 每次比较平均增减多少件；不是每个商品平均，也不是增长率 |
| median_unit_change | 每次销量变化件数的中位数，帮助判断均值是否被少数大变化带动 |
| sales_up_pct / sales_down_pct / sales_unchanged_pct | 该组中销量增加 / 减少 / 不变的比较次数占比，包含零销量记录 |
| check_status | 数据和计算检查是否通过 |

先看 transitions 和 distinct_pairs 了解覆盖，再结合均值、中位数和三个比例解读。三个比例以本组全部比较次数为分母；独立四舍五入后合计可能略偏离 100%。空组保留一行，次数和合计为 0，均值、中位数、比例为 NULL。

**TOTAL 的 distinct_pairs 不能直接相加各组。** 同一商品门店可能先涨价、再降价，出现在多个组中。相邻比较也共享中间周：previous_units 和 current_units 是比较端点合计，不是十二周销量的重新计数，不能相加当作新的总销量。

价格不变组只是描述性参照，不是随机对照组。即使降价组销量平均上升，也还需要检查日期、商品构成、节假日及供货等替代解释，不能立即写成“降价带来增长”。见 [方法与预检结果](PRICE_SALES_ASSOCIATION_VALIDATION.md) 和 [固定口径](PRICE_SALES_ASSOCIATION_PROTOCOL.md)。
