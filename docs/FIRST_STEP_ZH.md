# 第一小步：在官方页面识别 M5 的三份核心文件

更新日期：2026-10-27（Australia/Sydney）。

**前置条件已完成：** [quanchenginitial/retail-merchandising-analytics](https://github.com/quanchenginitial/retail-merchandising-analytics) Public 仓库已创建；阶段 0 的 12 份研究与路线文件已上传并逐份核对，研究提交为 [994cdb7](https://github.com/quanchenginitial/retail-merchandising-analytics/commit/994cdb794b2734ddd5951b5523dee669162e77e5)。完整数据下载、来源审计和你的学习验收尚未完成。

## 这一步的目的

先确认数据来自哪里，以及每份文件扮演什么角色，再开始下载和写 SQL。延续银行项目的节奏：完成一个动作，检查实际结果，再进入下一步。

## 本次只做一个动作

打开 [M5 Forecasting Accuracy 官方数据页面](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data)，阅读页面的数据说明和适用规则，在文件列表中找到以下三份文件：

| 文件 | 在本项目中的角色 |
|---|---|
| `sales_train_evaluation.csv` | 商品与门店组合的历史每日销量；当前计划采用的销量训练快照 |
| `calendar.csv` | 日编号与日期、周编号及日历信息的对应关系 |
| `sell_prices.csv` | 商品在门店与周层级的销售价格信息 |

本次完成标志是：你能确认这三份文件是否可见、是否需要登录或接受页面规则才能访问。告诉我实际看到的情况即可。如果页面要求接受规则，由你阅读并决定是否接受。

`sales_train_validation.csv` 与 `sales_train_evaluation.csv` 是不同历史长度的训练快照。本项目准备采用后者，不将两者当作互补记录拼接，也不因文件名里的 evaluation 就把它当成我们已经完成的模型测试结果。

本次只识别来源和文件；本地环境、下载和加载 SQL 留到后续逐项完成。

## 下一步预告

核对你的页面访问结果后，下一小步是确认本地项目路径与 Python/DuckDB 环境。随后按照来源规则获取三份文件，存入项目的 `data/raw/m5/`，记录来源、版本、获取日期、大小和 SHA-256；原始大文件排除出 Git。

文件实际到位后，再从一份文件的字段和行数检查开始。当前没有完整下载或 SQL 审计结果，也不提前把这些阶段标为完成。
