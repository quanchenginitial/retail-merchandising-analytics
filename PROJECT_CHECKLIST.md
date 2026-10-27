# 商品分析项目进度

更新日期：2026-10-27（Australia/Sydney）。

## 本次已经发生的工作

- [x] 助手核对需求来源中的六类业务问题，并复查银行项目的逐步学习流程。
- [x] 助手查阅 M5、Retailrocket、Criteo、dunnhumby/completejourney、GA4 的发布方或维护方资料。
- [x] 确定 M5 主线、Retailrocket 独立行为模块；Criteo 为后续实验扩展。
- [x] 整理数据来源、问题覆盖、指标口径、模型验证方案、学习路线。
- [x] 助手验证 Retailrocket 官方元数据及 ZIP 开头四字节可访问；没有下载完整档案。
- [x] 用户建立 GitHub Public 仓库；连接器确认 main 上有初始 README。
- [x] 阶段 0 的 12 份文件已上传 main；逐份远端读取与本地准备内容一致。研究提交：[994cdb7](https://github.com/quanchenginitial/retail-merchandising-analytics/commit/994cdb794b2734ddd5951b5523dee669162e77e5)。
- [x] 文档内部链接和 JSON 格式通过检查；预测切分的五个截止日期已独立计算核对。此检查不属于数据分析或模型测试。

## 实际操作尚待完成

- [x] 1A 用户下载并提供 M5 三个核心 CSV；本地存在性已核对，已满足取得文件这一步。
- [x] 1A 后续：用户截图确认 DBeaver 连接检查成功，database_name 为 retail_merchandising，duckdb_version 为 v1.5.5。截图未显示物理文件完整路径，不据此声称路径已独立核验。
- [x] 1B 三个原始文件已取得，助手登记文件名、大小和 SHA-256，并完成只读源文件审计：33/33 通过。精确下载时间、实际下载 URL 和压缩包 hash 未采集。
- [x] 独立检查确认日历范围、日期映射，以及价格行数、复合键和价格范围。见 [审计记录](docs/M5_SOURCE_AUDIT.md)。
- [x] 助手独立预验证日历导入 SQL：临时数据库中得到 1,969 行、14 列、14 个 VARCHAR、1,969 个日编号及正确日期范围。此结果不代表用户已经导入。
- [x] 1C1 用户截图确认 raw.m5_calendar 基础导入检查：database_name=retail_merchandising；1,969 行、14 列且全为 VARCHAR、1,969 个不同日编号；日期为 2011-01-29 至 2016-06-19。此截图未证明全部字段已与源文件逐行对账。
- [x] 助手独立验证 03 日历审计 SQL：正常来源 17/17 PASS；重复行、少一行、NULL SNAP、无效日期和变更事件文本五种临时故障均被识别，共六个用例通过。仅操作临时数据库。
- [x] 1C2 用户截图确认日历 17/17 PASS：source_only_rows=0、table_only_rows=0；日期、编号、属性、SNAP 和事件空值检查均通过。证明当前 CSV 与 raw 日历表逐行一致（含重复次数），不是重新核验历史源文件 hash。见 [截图转录记录](data/calendar_learner_acceptance.json)。
- [x] 助手在独立临时数据库预验证销量导入脚本：14/14 基础检查通过，源文件 hash 与登记一致且前后不变；不是用户导入结果。见 [验证说明](docs/SALES_IMPORT_VALIDATION.md)。
- [x] 1C3a 用户截图确认销量 raw 宽表基础检查 14/14 PASS：30,490 行、1,947 个 VARCHAR 列、1,941 个连续日列、唯一编号与商品门店覆盖均符合预期，缺失标识为 0。见 [截图转录记录](data/sales_import_learner_acceptance.json)。此结果不代表日销量值已经对账。
- [x] 助手独立验证销量详细审计：完整来源 15/15 PASS，12 个微型用例通过；检验 NULL、非法数值、负值、重复/漏行、总量相抵改动、编号和列名变化。只操作临时数据库；见 [验证说明](docs/SALES_AUDIT_VALIDATION.md)。
- [x] 1C3b 用户截图确认销量详细检查 15/15 PASS：59,181,090 个有效非负整数销量单元格、40,241,819 个零销量单元格、累计 66,927,173 件；来源双向差异均为 0，编号及映射检查通过。见 [截图转录记录](data/sales_audit_learner_acceptance.json)。
- [x] 助手独立预验证价格导入：12/12 基础检查通过，原文件 hash 与登记一致且验证前后不变；仅操作临时数据库，见 [验证说明](docs/PRICE_IMPORT_VALIDATION.md)。
- [ ] 1C4a 用户执行价格 raw 导入与 12 项结构、键基础检查。
- [ ] 1C4b 用户执行价格值检查与来源对账。
- [ ] 2A 清洗、宽转长、类型转换，并记录异常处理规则。
- [ ] 3 建维度与事实表；检查主键、关联覆盖、行数不膨胀、销量对账。
- [ ] 4 商品结构、ABC/XYZ、趋势分析通过检查。
- [ ] 5 时间切分、预测基线、滚动验证与一次最终留出评估完成。
- [ ] 6 价格关联、销售异常候选清单与人工核查规则完成。
- [ ] 7 Retailrocket 数据审计、时点属性连接、分群、购物篮和漏斗分析完成。
- [ ] 8 Power BI 页面、指标和筛选行为逐页核对完成。
- [ ] 可选 A：Criteo 修订版实验模块访问确认、数据审核、估计与区间验证完成。
- [ ] 9 干净环境复跑、英文结论、中文讲解和最终作品集检查完成。

以上空框均表示未完成；创建文档不等于用户已完成练习。没有预测误差、业务洞察、模型提升或自动刷新成果可以在此时写入简历。

## 下一次对话从这里继续

执行 [当前一步](docs/FIRST_STEP_ZH.md)：用户运行 sql/06_import_prices.sql，导入 raw.m5_prices 并返回 12 行基础检查结果。日历与销量详细验收已完成，不重复导入；价格数值、完整对账与日级价格覆盖后续分别验收。

GitHub 仓库：<https://github.com/quanchenginitial/retail-merchandising-analytics>。
