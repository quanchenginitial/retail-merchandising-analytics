# 当前一步：按商品部门观察价格与销量变化

更新日期：2026-11-02（Australia/Sydney）。

**这一步为了什么：检查整体价格与销量关联是否集中于特定商品部门，为解释商品构成差异补充证据。**

SQL47 的 11 行、12 列和全部 132 个字段值已验收，全部 PASS。涨价组在十一周的平均销量变化均为正；降价组在前八周为正、最后三周为负。这说明总体均值不能代表每一周的情况。它仍然不证明价格造成了销量变化。见 [截图验收记录](../data/weekly_price_sales_association_learner_acceptance.json)。

## 为什么继续看商品部门

不同商品部门的销量水平和调价次数可能不同。整体平均增加若干件，可能主要由某些部门贡献。SQL48 按数据中的七个商品部门编码分别显示涨价、降价、价格不变组的次数和平均销量变化，帮助识别这种构成差异。

这里的部门是商品分类编码，例如 FOODS_1；没有来源支持时不自行赋予更细的商品名称。每次比较仍是同一商品、同一门店的相邻两周，件数差仍为 **本周销量 − 上周销量**。

本次每个部门汇总全部十一组相邻周，**不是在同一周内进一步比较部门**。SQL47 已观察到的时间差异仍可能影响部门结果；这一步并未完成季节性或混杂因素调整。

## 执行 SQL48

1. 打开 [48_department_price_sales_association.sql](../sql/48_department_price_sales_association.sql)，复制全文。
2. 在 DBeaver 的 **retail_merchandising** 连接中新建编辑器，粘贴并使用 **执行 SQL 脚本 / Execute SQL Script（默认 Alt+X）**。
3. 发回完整 **7 行、12 列**结果截图，包含最右侧 check_status。按 dept_id 排序，**没有 TOTAL 行**。

这是只读查询，不新增分析表。助手独立预检已通过；用户 SQL48 执行与截图验收仍待完成。

## 怎样读结果

| 字段 | 含义 |
| --- | --- |
| dept_id | 七个商品部门之一 |
| series_count | 该部门不同的“商品 × 门店”组合数，不是独立商品数 |
| price_up_transitions / price_up_mean_unit_change | 涨价的相邻周比较次数，以及每次比较平均增减多少件 |
| price_down_transitions / price_down_mean_unit_change | 降价组的比较次数及平均件数差 |
| unchanged_transitions / unchanged_mean_unit_change | 价格不变组的比较次数及平均件数差 |
| missing_endpoint_transitions | 至少一个价格端点缺失的比较次数 |
| total_transitions | 该部门全部比较次数，应等于 series_count × 11 |
| total_unit_difference | 该部门全部比较的件数差合计，含缺价记录 |
| check_status | 输入、计算和对账检查是否通过 |

先看样本次数，再看均值。每个商品门店组合有十二周记录，产生十一组相邻比较；同一个组合在不同周可以进入不同价格方向组。七个部门的 series_count 合计为 30,490，全部比较次数合计为 335,390。

正负均值表示平均增加或减少的件数，**不是增长率或价格弹性**。所有零销量比较都保留；某部门某方向为空时，次数为 0、均值为 NULL。缺价记录独立统计，其销量差仍计入部门总差值。

各部门次数和件数差可以相加；还原 SQL46 的总体均值需要按比较次数加权，不能直接平均七个部门的均值。正式对账使用精确件数差合计，避免显示舍入影响。

即使同一部门内，商品、门店、时间和原有销量水平仍可能不同。价格不变组仍是描述性比较，不能据此认定促销收益或调价效果。见 [固定口径](DEPARTMENT_PRICE_SALES_ASSOCIATION_PROTOCOL.md) 与 [方法和预检](DEPARTMENT_PRICE_SALES_ASSOCIATION_VALIDATION.md)。
