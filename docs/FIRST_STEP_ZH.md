# 当前一步：建立有交易记录编号的频次基线

更新日期：2026-11-13（Australia/Sydney）。

**这一步为了什么：了解观察窗口内，有交易记录的访客编号分别出现了多少个候选篮子，先建立 F（Frequency，频次），为后续基于交易记录的 RF 分析准备。**

## SQL84 已验收

截图 **十二行 × 九列、108 个字段完整匹配，十二项全部 PASS、无 NULL**，24 个明确的月份零值完整保留；见 [验收](../data/retailrocket_pair_month_coverage_learner_acceptance.json)。[购物篮发现综述](STAGE07_BASKET_FINDINGS.md) 已整理，描述性里程碑完成，独立时间验证与推荐效果评估尚未完成。

## F 的定义和分母

对每个 visitorid，统计不同 `(visitorid, transactionid)` 候选篮子的数量。**一个篮子即使有多个商品或重复事件，也只为该编号的 F 贡献一次。** 这不是事件行数、商品数或购买件数。

总体只含 SQL70 已确认的 **11,719 个有交易记录的访客编号**，对应 **17,672 个候选篮子**。不包含 F=0 或没有交易记录的编号，也不是对全部 1,407,580 个事件访客编号分类。

F_1、F_2、F_3_4、F_5_PLUS 分别表示 1、2、3–4、至少 5 个篮子，四个区间互斥，再加 TOTAL 合计行。visitor_share_pct 用 11,719 作分母；basket_share_pct 用 17,672 作分母。不要将 TOTAL 与前四行再次相加。

max_baskets_per_visitor 表示本区间单个编号的最高频次。若某区间没有编号，其计数和占比为 0，最大频次为 NULL，属于正常空集合表达。百分比保留六位小数。

## 现在执行 SQL85

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [85_analyze_retailrocket_visitor_purchase_frequency.sql](../sql/85_analyze_retailrocket_visitor_purchase_frequency.sql)，完整执行只读查询。无需建表、重新导入 CSV 或重跑旧 SQL。
3. 提供 **五行、七列完整结果，正常五行全部 PASS**；确保最右侧 check_status 可见。

七列依次为 frequency_band、visitor_ids、visitor_share_pct、candidate_baskets、basket_share_pct、max_baskets_per_visitor、check_status。

助手预检已通过，用户执行和截图验收仍待完成；见 [验证说明](RETAILROCKET_VISITOR_PURCHASE_FREQUENCY_VALIDATION.md)。

## 验证和解释范围

本步分析只读取三个成员键，不读取时间字段。助手核对重建的六字段成员输入，并独立比较 **全部 11,719 行、两字段**的编号/频次；此前来源和成员证据继续复用。

这些区间只描述该快照的交易记录频次，不是忠诚度、客户价值或 RFM 标签。访客编号不等于已核实自然人，候选篮子不等于核实订单；观察时间长短也可能不同。本步没有计算 Recency，RF 分群、独立规则验证和 Power BI 仍未完成。
