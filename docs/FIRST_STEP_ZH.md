# 当前一步：查看浏览、加购与交易事件概览

更新日期：2026-11-09（Australia/Sydney）。

**这一步为了什么：了解三类行为各有多少记录、占总记录的多少，以及覆盖多少访客编号、商品和日期，为后续行为分析建立基础概览。**

## SQL69 已验收

截图 **28 行 × 5 列的 140 个字段全部完整可见并匹配**，包含 **20 项 PASS、8 项 INFO**。17 列事件事实表保留全部 **2,756,101 条事件记录**及 460 条完全重复的额外记录，完整字段对账与 UTC 时间/日期检查通过。见 [事实表验收记录](RETAILROCKET_EVENTS_ENRICHED_VALIDATION.md)。

## SQL70 做什么

只读 rr_mart.events_enriched 中原始 5 个事件字段与 2 个 UTC 字段，输出 **view、addtocart、transaction、TOTAL** 四行。

| 字段 | 用途 |
| --- | --- |
| event_type | 浏览、加购、交易记录或总计 |
| event_rows、event_share_pct | 事件记录数及其占全部事件记录的百分比，保留 4 位小数 |
| distinct_visitor_ids、distinct_item_ids | 各类记录涉及的不同访客编号与商品编号数 |
| distinct_transaction_ids | 不同的非空交易编号数 |
| first_event_utc、last_event_utc | 各类记录的最早、最晚 UTC 时间 |
| observed_utc_dates | 实际有该类记录的 UTC 日期数 |
| check_status | 数据与汇总检查是否通过 |

**TOTAL 的不同编号数、日期数和时间端点需要对全部记录重新计算，不能把三类结果直接相加。** 同一个访客或商品可能出现在多类事件里。

记录占比表示行为构成。例如，加购记录占全部事件的比例，不能解释为“看过商品的人中有多少完成加购”。后者还需要确定访客、商品、时间顺序和观察窗口，留待后续漏斗分析。访客编号不等于已确认的真实人数，交易记录或交易编号也尚未验证为订单。

## 现在执行 SQL70

1. 在 DBeaver 选中现有 **retail_merchandising** 连接。
2. 打开 [70_analyze_retailrocket_event_overview.sql](../sql/70_analyze_retailrocket_event_overview.sql)，完整执行查询。
3. 查看 **4 行、10 列结果**，预期四行 check_status 全部为 **PASS**。请保留全部列及两列完整 UTC 时间字符串；若画面太宽，可以分两张截图，并在两张中保留 event_type 与全部四行，便于对应。

这是只读查询，可以完整重复执行；无需新建表或重新导入 CSV。若出现 BLOCKED 与空指标，先核对检查原因，再解释业务结果。

## 验证及后续

助手预检已通过，用户执行与截图验收仍待完成；见 [行为事件概览验证说明](RETAILROCKET_EVENT_OVERVIEW_VALIDATION.md)。本次助手只读取 events.csv，并验证查询使用的七字段投影；其他十个历史属性字段继续依据已验收的 SQL69，不重新导入属性文件或重复构建事实表。

查询保留原有重复记录，时间范围采用 UTC。有观测的日期不证明全天采集完整，也不代表商家本地营业日。完成这一概览后，再逐步确定行为分析的时间窗口和分母。
