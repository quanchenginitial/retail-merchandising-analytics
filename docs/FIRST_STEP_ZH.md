# 当前一步：检查类别内的商品加购集中度

更新日期：2026-11-09（Australia/Sydney）。

**这一步为了什么：检查类别 1613 的加购是否集中在少数商品，比较不同加购量商品分档的交易比率，为进一步排查提供线索。**

## SQL75 已验收

30 行全部 PASS。截图有 **298 个字段完整可见**，另外两个截断的 UNKNOWN_REFERENCE 标签依据固定契约和可见上下文唯一还原；全部数值及 16 个 NULL 与预检匹配。各分组 EARLY 与 LATE 的计数相加还原 SQL74，见 [验收记录](RETAILROCKET_CATEGORY_FUNNEL_TIME_COHORTS_VALIDATION.md)。两个时期长度不同，原始计数变化不直接代表增长。

## SQL76 怎样分商品

本次汇总全体合格组合中**首次浏览类别为 1613**的商品，不再拆 EARLY/LATE。每个商品至少有一个该类别的合格访客—商品组合，再按它的**加购组合数**归入唯一一档：

| cart_volume_band | 每个商品的加购组合数 |
| --- | --- |
| ZERO_CART | 0 |
| CART_01_04 | 1–4 |
| CART_05_19 | 5–19 |
| CART_20_PLUS | 至少 20 |
| TOTAL | 上述全部商品 |

这里统计的是满足原有严格顺序及同一 7 天期限的访客—商品组合，不是加购点击次数、实际人数或核验订单数。首次浏览类别保持固定，后续类别变化不改变归属。四档计数应加总为 TOTAL，并还原 SQL74 类别 1613 的 **25,105 个合格、483 个加购、76 个交易组合**。

## 两种比率有什么不同

- **weighted_cart_to_transaction_rate_pct**：100 × 本档交易组合总数 ÷ 加购组合总数。加购量较大的商品影响更大。
- **mean_item_cart_to_transaction_rate_pct**：先对每个有加购的商品计算未四舍五入的交易组合数 ÷ 加购组合数，再等权平均并乘 100。每个有加购的商品权重相同，零加购商品不进入这个平均。
- **cart_share_pct**：100 × 本档加购组合数 ÷ 全类别 483 个加购组合，用来读集中程度；显示值经过四舍五入，合计不一定恰好 100。
- **zero_transaction_cart_items**：有加购组合、但没有符合路径规则的交易组合的商品数。

ZERO_CART 的两种交易/加购比率都是 NULL，zero_transaction_cart_items 为 0。助手预检中 CART_20_PLUS 是空档，保留零计数和两种 NULL 比率属于正常结果。TOTAL 的商品均值从全部有加购商品重新计算，不能直接平均各档均值。结果同时保留 item_count、eligible_pairs、cart_pairs 和 transaction_pairs，阅读比率时要一起看分母。这里的零交易仅限本队列、窗口和顺序规则，不表示商品从未售出。

## 现在执行 SQL76

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [76_analyze_retailrocket_category_item_cart_concentration.sql](../sql/76_analyze_retailrocket_category_item_cart_concentration.sql)，完整执行查询。
3. 提供 **5 行、10 列完整结果**，预期全部 PASS。拉宽长字段名并保留 NULL；若需横向拆成两张，两张都保留 **cart_volume_band 和全部五行**。

这是只读查询，可以完整重复执行，无需重新导入 CSV 或建表。助手预检已通过，用户执行及截图验收仍待完成；见 [验证说明](RETAILROCKET_CATEGORY_ITEM_CART_CONCENTRATION_VALIDATION.md)。

## 如何使用这一步的结论

类别 1613 是在观察到先前较低比率后选出的，因此本次是**探索性追查，不是独立确认**。分档阈值没有被证明最优；少量加购就会使单个商品比率大幅变化，两种平均的差别本身不证明原因，也不支持直接下架或调整策略。公开结果只有分档统计，不含商品、访客或交易编号。

验证范围仍是事件/类别十字段及参考类别编号；不重验可用性字段、事实表已有 UTC 派生字段、整个事实表或类别层级。
