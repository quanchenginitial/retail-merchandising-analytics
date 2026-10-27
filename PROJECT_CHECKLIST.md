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
- [ ] 1C1 用户执行日历 raw 导入并提交基础检查结果。
- [ ] 1C2 日历详细检查及销量、价格 raw 导入与对账。
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

执行 [当前一步](docs/FIRST_STEP_ZH.md)：用户在已验证的 retail_merchandising 连接中运行 sql/02_import_calendar.sql，导入 raw.m5_calendar 并返回检查结果。当前只处理日历文件；用户导入结果未收到前，不标记 1C1 完成。

GitHub 仓库：<https://github.com/quanchenginitial/retail-merchandising-analytics>。
