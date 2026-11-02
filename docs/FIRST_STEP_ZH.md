# 当前一步：同周、同部门的价格组比较

更新日期：2026-11-02（Australia/Sydney）。

**这一步为了什么：把周度和商品部门一起纳入比较背景，观察调价组与同周、同部门价格不变组的平均销量变化差。**

SQL48 的 7 行、12 列共 84 个值已验收，七个 PASS 完整可见。FOODS_1 的涨价组和降价组平均销量变化都为负，FOODS_3 两组都为正。结合 SQL47 的周度差异，我们已经知道整体平均值不能直接推广到每个部门或每一周。见 [验收记录](../data/department_price_sales_association_learner_acceptance.json)。

## 这次怎样比较

仍用同一个十二周窗口及同一商品门店组合的相邻周销量变化：**本周销量 − 上周销量**。先在每个“商品部门 × 当前周”内分出涨价、降价、价格不变组。某方向当周有记录，而且价格不变组也有记录，才能计算两组的平均变化差。

随后，在每个部门内，按调价组各周的比较次数加权，汇总为一行涨价、一行降价，共 **7 × 2 = 14 行**。参考组也使用同一套周度权重，让两组均值具有相同的周度权重；不直接拿 SQL48 中跨周汇总的价格不变组均值相减。

没有参考组的调价记录仍计入总覆盖，并单列 unsupported_transitions。它们不进入变化差计算，不补成零。这里 comparable 表示“同周同部门存在价格不变参考组”，与 SQL45 中“两端价格可比较”的含义不同。

## 执行 SQL49

1. 打开 [49_week_department_price_contrasts.sql](../sql/49_week_department_price_contrasts.sql)，复制全文。
2. 在 DBeaver 的 **retail_merchandising** 连接中新建编辑器，粘贴并使用 **执行 SQL 脚本 / Execute SQL Script（默认 Alt+X）**。
3. 发回完整 **14 行、12 列**截图，包含最右侧 check_status。每个部门按 UP、DOWN 排序，**没有 TOTAL 行**。

这是只读查询。助手独立预检已通过；用户 SQL49 执行与截图验收仍待完成。

## 怎样读这十二列

| 字段 | 含义 |
| --- | --- |
| dept_id / price_direction | 商品部门和本行的涨价 UP 或降价 DOWN 方向 |
| direction_transitions | 该部门、该价格方向的全部相邻周比较次数 |
| comparable_transitions | 所在周有价格不变参考组、因此能进入变化差计算的次数 |
| unsupported_transitions | 缺少同周同部门参考组的次数；前两项覆盖应满足 comparable + unsupported = direction |
| comparable_weeks | 同时有本方向记录和价格不变记录的周数 |
| weighted_direction_mean_change | 有参考支持范围内，调价组每次比较的平均销量变化，单位为件 |
| weighted_unchanged_mean_change | 按调价组周度次数加权后的价格不变参考组平均变化 |
| mean_change_gap | 前两种未舍入均值之差，最后独立保留六位小数 |
| positive_gap_weeks / negative_gap_weeks | 未舍入周度变化差为正或为负的周数；零差周数 = comparable_weeks − 正差周数 − 负差周数 |
| check_status | 输入、计算、覆盖与对账检查是否通过 |

先看比较次数和覆盖周数，再看变化差。若调价组平均增加 3 件、参考组平均增加 5 件，mean_change_gap 为 −2 件；这表示前者增长更少，**不表示前者销量下降了 2 件**。它也不是因果意义上的“损失销量”。

三列均值/差值分别从未舍入值保留六位，直接相减屏幕上两列均值可能有末位差异。周度正负也依据未舍入值判断。没有可比较记录时均值和变化差为 NULL，而不是 0。

正差、负差周数只是周的计数；汇总变化差同时取决于各周的变化幅度和比较次数。因此，即使多数周为正差，也不能据此判断加权汇总一定为正。

所有原始零销量和缺价观察均保留在完整内部对账中；缺价方向不被当作已知涨价、降价或价格不变。两种调价方向可以复用同一个价格不变参考组，但各自采用自己的周度次数权重，因此不能把两行参考支持相加，也不能把 UP 与 DOWN 的变化差直接当作两种调价策略的效果比较。各行变化差也不能直接相加。

本次只是按相同周和部门做描述性分层。参考组仍可能包含不同商品、门店和原有销量水平；它不是同一 SKU 的反事实，也没有自动平衡这些差异。变化差不能称为净促销提升、价格弹性或调价因果效果。见 [固定口径](WEEK_DEPARTMENT_PRICE_CONTRASTS_PROTOCOL.md) 与 [方法和预检](WEEK_DEPARTMENT_PRICE_CONTRASTS_VALIDATION.md)。

本步验收后，计划汇总价格关联部分的发现和局限，再进入异常候选排查。该汇总、异常模块及整体项目仍待完成。
