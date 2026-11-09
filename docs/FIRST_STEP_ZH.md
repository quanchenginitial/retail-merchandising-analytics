# 当前一步：比较不同首次浏览类别的 7 天路径

更新日期：2026-11-09（Australia/Sydney）。

**这一步为了什么：在同一批合格组合、同样的 7 天窗口下，查看不同首次浏览类别的浏览规模、后续加购及交易比例，并保留未知类别的完整分母。**

## SQL73 已验收

截图 **5 行 × 4 列、20 个字段完整匹配，五行全部 PASS**。2,042,310 个合格组合中，**1,527,206 个（74.7784%）**可映射静态类别；304,405 个早于首条类别观察、210,699 个没有类别历史，引用未知为 0。见 [类别覆盖验收](RETAILROCKET_FIRST_VIEW_CATEGORY_COVERAGE_VALIDATION.md)。

## SQL74 怎样分组

每个访客—商品组合的类别固定在**首次观测浏览**时，后续 7 天发生类别变化也不改组。加购仍须严格晚于浏览，交易严格晚于合格加购，两个动作都须在同一个首次浏览加 7 天的截止时间以内，包含终点。

结果预计有 **15 行**：

- **TOP_CATEGORY：10 行。** 按合格组合数从多到少选出 10 个可映射类别；并列按数字类别编号升序。转化率不参与排序。
- **OTHER_MAPPED：1 行。** 其余可映射类别的合计，是多个类别的集合。
- **UNKNOWN_REFERENCE、BEFORE_FIRST、NO_HISTORY：各 1 行。** 未知状态继续保留，包括计数为 0 的桶。
- **TOTAL：1 行。** 全部合格组合的汇总。

categoryid 只在 TOP_CATEGORY 行显示；其他汇总行的 NULL 属正常情况。编号是匿名类别标签，不能凭编号猜测“食品”“家具”等名称。

## 怎样阅读九列结果

| 字段 | 含义 |
| --- | --- |
| segment、categoryid | 分组类型与匿名类别编号 |
| eligible_pairs | 本组的合格浏览组合数 |
| cart_pairs | 本组在窗口内进入后续加购的组合数 |
| transaction_pairs | 本组进一步进入后续交易的组合数 |
| cart_rate_pct | 100 × 本组 cart_pairs ÷ eligible_pairs（%） |
| transaction_rate_pct | 100 × 本组 transaction_pairs ÷ eligible_pairs（%） |
| cart_to_transaction_rate_pct | 100 × 本组 transaction_pairs ÷ cart_pairs（%） |
| check_status | 检查是否通过 |

**每行使用自己的分母，分母为 0 时比率为 NULL。比率不能相加，TOTAL 的比率由总计重新计算。** 排除 TOTAL 后，各行计数应分别汇总为 **2,042,310 个合格组合、43,147 个加购组合、15,520 个交易组合**；类别覆盖还需与 SQL73 对账。

## 现在执行 SQL74

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [74_analyze_retailrocket_category_7day_funnel.sql](../sql/74_analyze_retailrocket_category_7day_funnel.sql)，完整执行查询。
3. 提供 **15 行、9 列完整结果**，预期全部 PASS，并保留所有 NULL。若画面过宽，可分成两张截图；两张都保留 **segment、categoryid 和全部 15 行**，便于逐行对应。

这是只读查询，可以完整重复执行，无需重新导入 CSV 或建表。

## 验证与解释范围

助手预检已通过，用户执行与截图验收仍待完成；见 [分类别 7 天路径验证说明](RETAILROCKET_CATEGORY_7DAY_FUNNEL_VALIDATION.md)。本次保持事件/类别十字段和参考编号的范围，四份源文件的验证仅保留类别历史，不重验可用性、UTC、整个事实表或类别层级。

本表展示分组后的匿名类别编号与统计结果，原始事件、访客/商品/交易编号和类别历史明细不上传。未知分组表示分析所用类别历史的覆盖状态，不证明网站对顾客缺少分类。类别差异可能同时涉及商品构成、观察覆盖和所选窗口；结果用于描述和提出后续问题，不证明类别导致转化变化，也不等于真实人数、会话或已验证订单表现。
