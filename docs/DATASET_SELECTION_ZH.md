# 商品分析数据集选择

核对日期：2026-10-27。选择原则：来源可追溯、业务字段有解释、规模足够、能在本机逐步处理、允许清楚说明证据边界。规模以下列发布方说明为依据，下载后必须重新计算；数字不能当作已经完成的本地审计。

## 结论

以 M5 为商品分析主线，Retailrocket 为独立购物行为模块。先完成主线，再扩展行为分析。Criteo 修订版用于后续因果方法练习；Complete Journey 用于需要购买金额、优惠券和家庭分群时的扩展；GA4 留作 BigQuery 练习。三个主模块不共享业务主键，不拼成一家公司。

## 候选比较

| 数据集 | 来源和规模 | 能补的业务能力 | 访问与使用条件 | 本项目决定 |
| --- | --- | --- | --- | --- |
| M5 / Walmart | 3,049 商品、10 店、3 州；30,490 序列；evaluation 训练文件有 1,941 日，长表为 59,181,090 个观测；Kaggle 页面列出 5 个 CSV、450.47 MB | SKU/门店结构、季节性、间歇销量、28 日预测、价格关联、异常候选 | 官方竞赛页标示 Subject to Competition Rules；完整当前规则正文和下载未在本轮验证。组织者另提供 Drive 文件夹 | 主线；进入分析前确认官方访问与条款 |
| Retailrocket v2 | 2,756,101 事件，1,407,580 访客；20,275,902 商品属性变化记录、417,053 商品；约 4.5 个月 | 行为分群、浏览/加购/交易、同单商品、属性时点连接 | 官方 API 确认 CC BY-NC-SA 4.0；约 304.72 MB ZIP，解压总量约 987.50 MB；本轮仅核验元数据和 ZIP 签名 | 独立行为模块 |
| Criteo corrected uplift | 13,979,592 用户行；官方标示 297M 压缩 | treatment 与 conversion/visit，增量与异质性方法 | 官方 CC BY-NC-SA 4.0；下载域名在本环境未能解析；未取得档案 | 可选实验扩展，访问问题解决后再做 |
| dunnhumby 原版 Complete Journey | 两年、2,500 个高频购物家庭，跨品类购买及部分人口属性、营销接触 | RFM、购物篮、优惠券关联 | 官方按钮存在，完整下载及具体数据许可未验证；发布方将 Source Files 描述为现实启发的数据表示 | 可选，不阻塞主线 |
| completejourney 包 / 84.51° Complete Journey 2.0 | 维护方列出一年、2,469 家庭、1,469,307 交易行和 20,940,529 促销记录 | 金额分群、购物篮、店周促销 | 包元数据标 CC0、公开 RDS；这是维护者分发，不是已核验的原始下载。84.51° 原网站本轮返回 403 | 如需金额 RFM 再加入，保留分发链说明 |
| Google GA4 公共样本 | 2020-11-01 至 2021-01-31；事件级，实际行数待查询 | 更完整的商品/会话/渠道分析及嵌套 SQL | 需启用 BigQuery API 的项目；官方称 Sandbox/free tier 可探索；混淆导致部分内部不一致 | 云 SQL 进阶扩展，初期不增加平台成本和设置 |

## 为什么不用已有项目的数据重新做一次

既有 Olist 项目已经覆盖销售结构、客户分群、复购、配送和评价；UCI Online Retail II 项目侧重日级销售/取消流水和工程流程。M5 增加商品×门店×日期层面的规模和预测难度，Retailrocket 增加购买前事件。两者分别补齐缺口。

零售场景与家具业务的方法可迁移，但这些数据不是 IKEA 数据，也不能据此描述 IKEA、日本或韩国顾客的真实表现。

## M5 使用细节

准备 `sales_train_evaluation.csv`、`calendar.csv`、`sell_prices.csv`。不要同时叠加 validation 与 evaluation 两个销售文件：前者的历史包含在后者中，叠加会重复计算。日序号从 2011-01-29 起，训练最后一天 d_1941 对应 2016-05-22；比赛最后测试日 2016-06-19 不是该训练文件结束日。

`sell_price` 是商品在门店某周的平均价格。销量乘该价格只能形成销售额估计值，不能当逐笔净收入或毛利。没有库存、补货提前期、成本、客户、订单或退款明细。价格缺失和销量为零均不能单独证明缺货。主线可以预测已记录销量并提出库存调查清单，但不能测量真实库存服务水平。

## Retailrocket 使用细节

官方说明列出 2,664,312 次 view、69,332 次 addtocart、22,457 次 transaction 事件。transaction 数不是订单去重结果。商品属性中只有 `categoryid`、`available` 含义明确；其余属性匿名，不能擅自认定其中某列是价格或成本。

属性是随时间变化的记录，连接事件时只能选事件时点以前最近的记录；没有前序记录时保留未知。官方称约 90% 事件能匹配商品属性，不能把剩余未知当成不可售。`available` 可用于观察可用性关联，但不是精确库存数量。没有已确认取消/退款事实，也不能做标准金额 RFM。

## Criteo 和其他扩展的解释边界

Criteo 应使用更正后的约 1,398 万行版本。旧约 2,531 万行版本有发布方披露的泄漏问题。它来自广告随机留出实验，提供的是广告干预方法练习，不能当成商品页改版的真实 A/B 实验。数据非均匀抽样且匿名，不能恢复原广告主商业增量。

Complete Journey 两种版本的家庭数、年份和交易量不能混用。维护包说明的 `sales_value` 含厂商补偿，未必等于顾客自付金额；促销接触不等于随机分组。dunnhumby 另有约三亿条的 Let's Get Sort-of-Real，但官方明确为 dummy data，因此不把它选为真实业务发现主证据。

## 下载与版本控制原则

首次取得文件时保存来源页、访问日期、文件大小、SHA-256、压缩包清单和数据版本。URL 可访问不等于整份内容已经验证；元数据数量不等于本地对账结果。原始文件保持不变且不进 GitHub，只上传经审核的汇总、代码和复现说明。涉及接受网站条款的页面由用户审阅。

## 直接来源

- M5：[组织者仓库](https://github.com/Mcompetitions/M5-methods)、[竞赛数据页](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data)、[竞赛规则](https://www.kaggle.com/competitions/m5-forecasting-accuracy/rules)、[官方指南](https://github.com/Mcompetitions/M5-methods/blob/master/M5-Competitors-Guide.pdf)、[组织者数据目录](https://drive.google.com/drive/folders/1D6EWdVSaOtrP1LEFh1REjI3vej6iUS_4?usp=sharing)。
- Retailrocket：[原始发布页](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset)、[官方元数据](https://www.kaggle.com/api/v1/datasets/view/retailrocket/ecommerce-dataset)、[固定版本下载](https://www.kaggle.com/api/v1/datasets/download/retailrocket/ecommerce-dataset?datasetVersionNumber=2)。
- Criteo：[发布方数据与更正说明](https://ailab.criteo.com/criteo-uplift-prediction-dataset/)。
- dunnhumby：[Source Files](https://www.dunnhumby.com/source-files/)。completejourney：[维护者说明](https://bradleyboehmke.github.io/completejourney/)、[字段指南](https://bradleyboehmke.github.io/completejourney/articles/completejourney.html)、[许可元数据](https://raw.githubusercontent.com/bradleyboehmke/completejourney/master/DESCRIPTION)。
- Google：[GA4 样本说明](https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset)。
