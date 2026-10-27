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
- [x] 1C4a 用户截图确认价格基础检查 12/12 PASS：6,841,121 行、4 个 VARCHAR 列、唯一商品门店周键，重复/必要字段缺失均为 0；30,490 个商品门店组合、3,049 件商品、10 家门店、282 周。见 [截图转录记录](data/price_import_learner_acceptance.json)。
- [x] 助手独立验证价格详细审计：完整来源 15/15 PASS，12 个微型用例通过；覆盖价格异常、重复/漏行、错误组合与周编号、仅文本变化。仅操作临时数据库，见 [验证说明](docs/PRICE_AUDIT_VALIDATION.md)。
- [x] 1C4b 用户截图确认价格详细检查 15/15 PASS：6,841,121 个有限正价格，范围 0.01–107.32；必要字段、重复键、编号对应及双向来源差异均为 0。见 [截图转录记录](data/price_audit_learner_acceptance.json)。此结果不代表日级价格覆盖已验收。
- [x] 原始层里程碑：三表导入及 47 项详细审计完成，见 [阶段记录](docs/RAW_LAYER_CHECKPOINT.md)。
- [x] 助手独立预验证日历清洗层：13/13 PASS，逐列类型/顺序及回转文本后的双向对账通过；未操作用户数据库，见 [验证说明](docs/CALENDAR_STAGING_VALIDATION.md)。
- [x] 2A1 用户截图确认 stg.m5_calendar 的 13 项检查全部 PASS：1,969 行、14 列，逐列类型及顺序正确、事件空值保留，回转原始文本后的双向差异均为 0。见 [截图转录记录](data/calendar_staging_learner_acceptance.json)。
- [x] 助手核实价格来源精度：624,039 条一位小数、6,217,082 条两位小数，无更高精度值；价格清洗脚本 13 项预验证与 7 个针对性用例通过，见 [验证说明](docs/PRICE_STAGING_VALIDATION.md)。
- [x] 2A2 用户截图确认价格清洗表 13/13 PASS：6,841,121 行、4 列，DECIMAL(18,2) 与 INTEGER 周编号正确，唯一键及规范化后的精确数值对账通过。见 [截图转录记录](data/price_staging_learner_acceptance.json)。
- [x] 助手完成完整销量宽转长预验证：59,181,090 行、14/14 检查通过，另有 8 个针对性用例；使用自有临时磁盘库并已清理，见 [验证说明](docs/SALES_DAILY_VALIDATION.md)。
- [x] 2A3a 用户截图确认四列 stg.m5_sales_daily 的 14 项检查全部 PASS：59,181,090 行、40,241,819 个零销量、累计 66,927,173 件，完整唯一日键及门店总量一致。见 [截图转录记录](data/sales_daily_learner_acceptance.json)。本步尚不证明逐格值一致。
- [x] 助手独立预验证逐格值对账：完整来源 15/15 PASS，16 个针对性用例通过，能识别总量不变的日期销量移位；见 [验证说明](docs/SALES_RECONCILIATION_VALIDATION.md)。
- [x] 2A3b 用户截图确认逐格对账 15/15 PASS：59,181,090 个单元格全部比较，销量不一致序列与单元格均为 0，键完整性和来源集合一致。见 [截图转录记录](data/sales_reconciliation_learner_acceptance.json)。
- [x] M5 清洗层里程碑完成，见 [阶段记录](docs/STAGING_LAYER_CHECKPOINT.md)。
- [x] 助手独立预验证商品维度：完整来源投影得到 3,049 个商品，15/15 检查和 12 个针对性用例通过；见 [验证说明](docs/PRODUCT_DIMENSION_VALIDATION.md)。
- [x] 3A1 用户截图确认 core.m5_product 的 15 项检查全部 PASS：3,049 个唯一商品、3 列、7 个部门和 3 个类别，来源映射及商品键一对一检查通过；见 [截图转录记录](data/product_dimension_learner_acceptance.json)。
- [x] 助手独立预验证门店维度：13/13 检查和 11 个针对性用例通过，来源确认 CA 4 家、TX 3 家、WI 3 家；见 [验证说明](docs/STORE_DIMENSION_VALIDATION.md)。
- [x] 3A2 用户截图确认 core.m5_store 的 13 项检查全部 PASS：10 家唯一门店、2 列、3 个州，来源映射、州门店数和来源键关联检查通过；见 [截图转录记录](data/store_dimension_learner_acceptance.json)。
- [x] 助手独立预验证日历维度：17/17 检查及 13 个故障用例通过，保留 1,969 天和原 14 字段，新增 day_number；见 [验证说明](docs/CALENDAR_DIMENSION_VALIDATION.md)。
- [x] 3A3 用户截图确认 core.m5_calendar 的 17 项检查全部 PASS：1,969 个唯一日/日期、15 列、282 周、原 14 字段与新增日序检查通过；见 [截图转录记录](data/calendar_dimension_learner_acceptance.json)。
- [x] 商品、门店、日历三张维度表完成单表验收，见 [阶段记录](docs/DIMENSIONS_CHECKPOINT.md)。
- [x] 助手独立预验证完整销量维度关联：20/20 检查与 15 个针对性用例通过，59,181,090 行、66,927,173 件和 40,241,819 个零销量行均保留；见 [验证说明](docs/DIMENSION_JOINS_VALIDATION.md)。
- [ ] 3B1 用户执行销量与三张维度表的完整关联审计，验收匹配覆盖和行数/销量保留。
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

执行 [当前一步](docs/FIRST_STEP_ZH.md)：用户运行只读 sql/15_audit_sales_dimension_joins.sql，返回 20 行结果。目的是确认每条销量都能匹配商品、门店和日期，关联后不漏行、不增行、不改变销量，为分类汇总提供可信基础。每次新操作都先简述本步目的及其分析用途，再给执行内容。

GitHub 仓库：<https://github.com/quanchenginitial/retail-merchandising-analytics>。
