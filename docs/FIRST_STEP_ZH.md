# 当前一步：检查预测改善覆盖了多少商品

更新日期：2026-10-29（Australia/Sydney）。

**这一步为了什么：在平均误差已经降低的基础上，继续检查多少商品实际改善、多少持平、多少变差。** 平均分可以告诉我们总体表现，逐商品配对能补充改善的覆盖范围和幅度。

SQL36 的 **6 行、12 列全部 PASS**，已与独立预检指纹匹配。三个开发窗口中，WEEKDAY4 的 MAE 和 macro RMSSE 均低于 SNAIVE7；每行都有 216 个有效 RMSSE，0 个未定义。两个方法在前两个窗口整体低估、第三个窗口整体高估，四周均值的偏差较小。这些结论仅针对当前 FOODS_1 / CA_1 的 216 个商品序列，最终留出期仍未评分。

## 新一步如何比较

对同一个商品、同一个门店、同一个开发窗口，把两种方法各自的 **28 天整体误差**放在一起比较：

- WEEKDAY4 误差较小，计入 `weekday4_wins`。
- 两者完全相等，计入 `ties`。
- SNAIVE7 误差较小，计入 `snaive7_wins`。

MAE 与 RMSSE 分开比较，所以每个窗口有两行，共 **6 行**。这里数的是商品序列，不是预测天数或成交订单数。胜负使用未四舍五入的精确误差来判断；显示值看起来一样，也可能有微小差别。

`weekday4_win_pct` = 四周均值胜出的商品数 ÷ 可比较商品数 × 100。持平商品保留在分母内；它是**胜出商品占比，不是误差下降百分比**。

## 改善幅度怎么看

先对每件商品计算 **delta = WEEKDAY4 误差 − SNAIVE7 误差**，再汇总这些差值：

| 字段 | 含义 |
| --- | --- |
| mean_delta | 逐商品差值的平均数；负数表示平均误差下降 |
| median_delta | 逐商品差值的中位数；用于观察差值分布的中间位置 |

例如某商品的 MAE 从 2.00 降至 1.50，则差值为 **−0.50 件/天**。这是解释用的例子，并非某件真实商品的结果。中位数应先逐商品相减再计算，不能直接相减两套模型各自的中位数。胜出的数量与改善幅度需要一起读。

MAE 使用全部 216 个序列；RMSSE 如果缺少有效历史尺度，则排除该项评分并单独计数，不能把 NULL 填成零。极端情况下没有可比较序列，占比和差值应为 NULL。

## 这次只执行 SQL37

1. 打开 [37_compare_series_forecast_improvements.sql](../sql/37_compare_series_forecast_improvements.sql)，复制全文。
2. 在 DBeaver 的 **retail_merchandising** 连接中新建编辑器，粘贴后使用 **执行 SQL 脚本 / Execute SQL Script（默认 Alt+X）**。
3. 发回 **6 行、12 列**结果截图，包含 `origin`、`metric` 和 `check_status`；过宽可分两张。

SQL37 是只读查询，可以重复运行。它核对现有预测与评分来源，并保留两套预测表。

## 结果核对关系

12 个字段依次为 `origin`、`metric`、`total_series`、`compared_series`、`excluded_series`、`weekday4_wins`、`ties`、`snaive7_wins`、`weekday4_win_pct`、`mean_delta`、`median_delta`、`check_status`。

- 每行 `total_series` 应为 **216**。
- `compared_series + excluded_series = 216`。
- `weekday4_wins + ties + snaive7_wins = compared_series`。
- 每个开发窗口按 MAE、RMSSE 顺序各一行；没有把三个窗口混在一起的 TOTAL 行。

PASS 表示计算与数据检查通过。胜出占比不是显著性检验；同一门店的商品可能同时受到共同因素影响。我们先描述改善覆盖，再决定后续方法，不据此直接宣称最终留出表现或库存收益。

助手独立预检已通过：**648 条配对序列的 17 个字段、六行汇总及 10 个针对性用例**通过核验；整数判定完全一致，浮点评分与高精度参考在约定容差内一致。413,208 条训练记录、两套完整候选预测及已验收的 SQL36 汇总也已复核，来源与候选保持不变，临时文件已清理。

预检中，MAE 改善覆盖率依次为 **54.1667%、50.0000%、67.5926%**，RMSSE 改善覆盖率为 **72.6852%、65.7407%、80.5556%**。特别留意第二个窗口：MAE 有 108 件改善、14 件持平、94 件变差，改善者恰好占一半。请先复现全部六行，再一起解释幅度和覆盖的差异。

**用户 SQL37 执行仍待截图验收。** 详见 [配对比较方法](SERIES_FORECAST_IMPROVEMENTS_VALIDATION.md) 与 [固定比较规则](SERIES_FORECAST_IMPROVEMENTS_PROTOCOL.md)。
