# 当前一步：按周观察价格与销量变化

更新日期：2026-11-02（Australia/Sydney）。

**这一步为了什么：检查 SQL46 的整体结果在不同周是否一致，还是集中在少数周，为解释价格与销量的关联补充时间背景。**

SQL46 的五行、十二列已验收，全部 PASS。涨价组平均销量变化为 +3.194660 件，降价组为 +1.667051 件，价格不变组为 −0.043842 件。前两组中位数均为 +1 件。这些是每次相邻周比较的变化件数，并不证明涨价或降价造成了增长。见 [验收记录](../data/price_sales_association_learner_acceptance.json)。

## 为什么要按周拆开

整个窗口的平均值把不同日期混在一起。若调价较多的周本身就有普遍销量变化，直接看总体均值可能掩盖时间差异。SQL47 在每一周内并排展示三个价格组的数量和平均变化，先看这种可能性。

仍沿用同一个十二周窗口。每次比较保持“同一商品、同一门店、相邻两周”，销量变化仍是 **本周销量 − 上周销量**。十二周形成十一组相邻比较，因此本次报告有 **11 行，每行对应后一个周**，从 2016-02-06 开始，没有另加 TOTAL。

## 这次执行 SQL47

1. 打开 [47_weekly_price_sales_association.sql](../sql/47_weekly_price_sales_association.sql)，复制全文。
2. 在 DBeaver 的 **retail_merchandising** 连接中新建编辑器，粘贴并使用 **执行 SQL 脚本 / Execute SQL Script（默认 Alt+X）**。
3. 发回 **11 行、12 列**结果截图，包含最右侧 check_status。

这是只读查询，不新增分析表。助手独立预检已通过；用户 SQL47 仍待执行与截图验收。

## 怎样读结果

| 字段 | 含义 |
| --- | --- |
| retail_week / week_start | 比较中后一个周的编号和开始日期 |
| price_up_transitions | 当周涨价的商品门店相邻周比较次数 |
| price_up_mean_unit_change | 当周涨价组每次比较平均增减多少件 |
| price_down_transitions / price_down_mean_unit_change | 当周降价组的比较次数与平均销量变化 |
| unchanged_transitions / unchanged_mean_unit_change | 当周价格不变组的比较次数与平均销量变化 |
| missing_endpoint_transitions | 至少一个价格端点缺失的比较次数，仍计入覆盖 |
| total_transitions | 当周全部比较次数，应为 30,490 |
| total_unit_difference | 当周全部比较的销量变化合计，含缺价记录，单位为件 |
| check_status | 输入、计算与对账检查是否通过 |

先看三个组的样本数量，再比较同一行的三个均值。正数代表平均增加，负数代表平均减少，单位都是件，**不是销量增长百分比**。某周某组没有记录时，该组次数为 0、均值为 NULL，不补成 0。

十一周的比较次数可以相加；**各周均值不能直接取简单平均来还原 SQL46**，必须按各周比较次数加权，且正式对账使用未舍入的销量差值合计。各周缺价记录仍在内部完整统计；本表只简化展示，不会删掉它们或零销量观察。

同一周内，三组商品和门店构成仍可能不同；价格不变组依然不是因果对照。即使每周都观察到同方向变化，也不能直接解释为调价效果。见 [固定口径](WEEKLY_PRICE_SALES_ASSOCIATION_PROTOCOL.md) 和 [方法与预检](WEEKLY_PRICE_SALES_ASSOCIATION_VALIDATION.md)。
