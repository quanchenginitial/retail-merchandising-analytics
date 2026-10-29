# 商品分析项目进度

更新日期：2026-10-29（Australia/Sydney）。

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
- [x] 3B1 用户截图确认完整销量维度关联 20/20 PASS：59,181,090 行、66,927,173 件、40,241,819 个零销量行均保留，三类未匹配与门店汇总差异为 0；见 [截图转录记录](data/dimension_joins_learner_acceptance.json)。
- [x] 助手独立预查价格覆盖：12 项机械检查及 2 项正销量覆盖门槛通过，15 个针对性用例通过；观察到 12,299,413 个缺价日记录全部为零销量，销量件数覆盖率 100%。仅为助手预查，见 [验证说明](docs/PRICE_COVERAGE_VALIDATION.md)。
- [x] 3B2 用户截图确认价格覆盖 14 PASS、9 INFO：12,299,413 个缺价日记录全部为零销量，日记录覆盖率 79.2173%，正销量记录和销量件数覆盖率均为 100%；见 [截图转录记录](data/price_coverage_learner_acceptance.json)。
- [x] 助手独立预验证日销量事实表：全量 20 项检查通过，25 个针对性用例通过；保留缺价 NULL，以零销量金额为 0 的明确口径生成金额代理，见 [验证说明](docs/SALES_FACT_VALIDATION.md)。仅为助手临时库验证。
- [x] 3C 用户截图确认 mart.m5_sales_daily 的 20 项检查全部 PASS、1 项 INFO：59,181,090 行、30,490 条完整序列、66,927,173 件，逐值及日期/价格/标记/金额差异均为 0；估算销售额合计 USD 191,577,546.04。见 [截图转录记录](data/sales_fact_learner_acceptance.json)。
- [x] 3 商品分析模型阶段完成：维度、事实表、键唯一性与覆盖、关联无膨胀、销量逐值及金额口径均验收；未声明物理主键。见 [阶段记录](docs/ANALYTICAL_MODEL_CHECKPOINT.md)。
- [x] 助手准备类别贡献查询并独立预验证：固定 2016-01-26 至 2016-04-24 的 90 天窗口，三类别及总计，与来源整数分金额汇总一致；16 个针对性用例通过。见 [方法与预查](docs/CATEGORY_CONTRIBUTION_VALIDATION.md)。
- [x] 4A 用户截图确认类别贡献 4 行全部 PASS：90 天合计 3,767,196 件、估算金额 USD 11,846,945.98；三类商品的数量、金额、占比和覆盖率与预查一致。见 [截图记录](data/category_contribution_learner_acceptance.json)；[结果文档](docs/CATEGORY_CONTRIBUTION_VALIDATION.md)提供助手的业务解读。
- [x] 助手准备部门贡献查询并独立预验证：同一 90 天窗口，7 部门及 TOTAL；来源整数分计算一致，向上汇总与已验收类别结果一致，14 个针对性用例通过。见 [方法与预查](docs/DEPARTMENT_CONTRIBUTION_VALIDATION.md)。
- [x] 4B 用户截图确认部门贡献 8 行全部 PASS：部门汇总与类别一致，TOTAL 的类别内金额占比为 NULL；FOODS_3、HOUSEHOLD_1、HOBBIES_1 的类别内金额占比分别为 60.9198%、76.2764%、95.4242%。见 [截图记录](data/department_contribution_learner_acceptance.json) 和 [助手解读](docs/DEPARTMENT_CONTRIBUTION_VALIDATION.md)。
- [x] 助手准备商品销量集中度查询并独立预验证：同一 90 天窗口、销量排序及精确累计阈值，逐商品、逐排名/累计值来源对照通过，14 个针对性用例通过；见 [方法与预查](docs/PRODUCT_UNIT_CONCENTRATION_VALIDATION.md)。
- [x] 4C1 用户截图确认商品销量集中度 8 行全部 PASS：达到 80%/95% 分别需 1,135/2,103 个商品；3,045 个正销量商品、4 个零销量商品，累计销量仍为 3,767,196 件。见 [截图记录](data/product_unit_concentration_learner_acceptance.json)；该结果尚非 ABC 标签。
- [x] 助手准备 80%/95% 销量 ABC 基线表与验收查询：逐商品来源/标签对照及与已验收累计范围对账通过，21 个边界与异常用例通过。见 [方法与预验证](docs/PRODUCT_ABC_UNITS_VALIDATION.md)。
- [x] 4C2 用户截图确认销量 ABC 基线 5 行全部 PASS：A/B/C/ZERO_SALES 分别为 1,135/968/942/4 个商品，互斥分组还原全部 3,049 个商品、3,767,196 件；正销量排名连续，零销量排名为 NULL。见 [截图记录](data/product_abc_units_learner_acceptance.json) 和 [基线验收](docs/PRODUCT_ABC_UNITS_VALIDATION.md)。
- [x] 助手准备只读 ABC 阈值敏感性查询：原始销量宽表与 Python 前缀算法核对全部 3,049 个基线商品、15,245 个场景分类及 5 行汇总，26 个边界与异常用例通过；基线前后不变。见 [方法与预查](docs/ABC_THRESHOLD_SENSITIVITY_VALIDATION.md)。
- [x] 4C3 用户截图确认 SQL22 阈值敏感性 5 行全部 PASS：A75_95、A85_95、AB80_92、AB80_98 分别使 194/240/273/392 个商品换组，基线换组为 0；结果与预检一致。见 [截图记录](data/abc_threshold_sensitivity_learner_acceptance.json) 和 [结果解读](docs/ABC_THRESHOLD_SENSITIVITY_VALIDATION.md)。换组商品的历史销量占比不代表销量变化；A 边界调整 5 个百分点、A+B 调整 3 个百分点，不据换组数直接比较等幅扰动的敏感性，也不声称最优阈值或时间稳定。
- [x] 助手独立预验证商品周销量：36,588 行的全部 8 字段与原宽表逐周七列求和一致，13 行汇总及 20 个针对性用例通过；逐商品验证 90=84+6，ABC 基线未变。84 天 3,536,539 件，加排除六天 230,657 件还原 3,767,196 件；见 [方法与预查](docs/PRODUCT_WEEKLY_VALIDATION.md)。
- [x] 4D1 用户截图确认 SQL23 商品周销量 13 行全部 PASS：2016-01-30 至 2016-04-22 的 12 个完整零售周、全部 10 店合并，合计 36,588 个商品周、2,561,160 条源日记录、3,536,539 件及 1,056 个零销量商品周。见 [截图记录](data/product_weekly_learner_acceptance.json) 和 [周销量验收](docs/PRODUCT_WEEKLY_VALIDATION.md)。1,056 不是不同商品数；84 天全零的 7 个商品属于助手独立统计，截图本身未显示。
- [x] 助手独立预验证商品波动指标：原始宽表周向量与 Python 高精度总体统计核对全部 3,049 行、14 字段及三行汇总，22 个测试通过，输入周表未变；CV 中位数/P90/最大值为 0.205417/0.495779/3.316625，7 个全零商品 CV 为空。见 [方法与预查](docs/PRODUCT_VARIABILITY_VALIDATION.md)。
- [x] 4D2 用户截图确认 SQL24 波动指标三行全部 PASS：3,042 个有销量商品、7 个全零商品；CV 中位数/P90/最大值为 0.205417/0.495779/3.316625，全零 CV 为 NULL；972 + 84 = 1,056 个零销量商品周。见 [验收记录](data/product_variability_learner_acceptance.json)。
- [x] 助手独立预查 SQL25 XYZ 基线：3,049 行、15 字段与原始来源对照，24 个测试通过，周表和指标表未变；阈值 X≤0.5、Y≤1、Z>1，以整数等价公式保护边界，全零商品独立。见 [XYZ 验证](docs/PRODUCT_XYZ_VALIDATION.md)。
- [x] 4D3 用户截图确认 SQL25 XYZ 基线五行全部 PASS：X/Y/Z/ZERO_SALES 分别有 2,745/167/130/7 个商品，合计 3,049 个商品、3,536,539 件及 1,056 个零销量商品周；TOTAL CV 中位数为 0.205417，全零组为 NULL。见 [验收记录](data/product_xyz_learner_acceptance.json) 和 [XYZ 基线解读](docs/PRODUCT_XYZ_VALIDATION.md)。
- [x] 助手独立预查 SQL26 XYZ 阈值敏感性：3,049 个基线商品的 15 字段及 15,245 个场景商品标签逐一核对通过，21 个针对性用例通过；三个输入表及来源 hash 不变，临时库已清理。五场景均 PASS，四个替代场景分别有 164/66/15/24 个商品换组。见 [方法与预查](docs/XYZ_THRESHOLD_SENSITIVITY_VALIDATION.md) 和 [机器记录](data/xyz_threshold_sensitivity_preflight.json)。
- [x] 4D4 用户截图确认 SQL26 XYZ 阈值敏感性五行全部 PASS：基线换组为 0，四个替代场景换组商品分别为 164/66/15/24，商品占比与历史销量占比均与预检一致；七个全零商品保留。见 [验收记录](data/xyz_threshold_sensitivity_learner_acceptance.json) 和 [敏感性解读](docs/XYZ_THRESHOLD_SENSITIVITY_VALIDATION.md)。
- [x] 助手独立预查 SQL27 ABC × XYZ：3,049 个商品的全部 22 字段与来源对照，五行矩阵及 20 个针对性用例通过，四个输入表、来源 CSV 和历史 ABC 预检均未改动，临时库已清理。逐商品核对 90=84+6；C × ZERO_SALES 有 3 个商品，仅在排除的六天合计销售 12 件。见 [组合验证](docs/PRODUCT_ABC_XYZ_VALIDATION.md) 和 [预检记录](data/product_abc_xyz_preflight.json)。
- [x] 4E1 用户于 2026-10-29 截图确认 SQL27 ABC × XYZ 商品数矩阵五行全部 PASS：A/B/C/ZERO_SALES 分别含 1,135/968/942/4 个商品，XYZ 列合计为 2,745/167/130/7；两个日期窗口均显示。A × X 有 1,082 个商品，C × ZERO_SALES 有 3 个；截图展示商品数，未展示这些商品的销量小计。见 [验收记录](data/product_abc_xyz_learner_acceptance.json) 和 [组合验收](docs/PRODUCT_ABC_XYZ_VALIDATION.md)。
- [x] 助手独立预查 SQL28 组合销量贡献：3,049 个商品的 22 字段、逐商品组合归属及 16 个组合的整数汇总均与来源对照一致，17 行报告及 18 个针对性用例通过。五个输入表、来源 hash 和历史预检均未变，临时库已清理；5 个空组合保留。A × X 占商品数 35.4870%，分别贡献 90 天/84 天销量的 76.7842%/76.8488%；这两项来自不同长度的嵌套窗口。见 [方法与预查](docs/ABC_XYZ_CONTRIBUTION_VALIDATION.md) 和 [机器记录](data/abc_xyz_contribution_preflight.json)。
- [x] 4E2 用户于 2026-10-29 截图确认 SQL28 组合销量贡献 17 行全部 PASS：16 个组合及 TOTAL、两套日期与销量占比均显示，5 个空组合保留。A × X 的商品占比为 35.4870%，90 天/84 天销量占比分别为 76.7842%/76.8488%；两个窗口嵌套，不能当作前后期增长。见 [验收记录](data/abc_xyz_contribution_learner_acceptance.json) 和 [贡献验收](docs/ABC_XYZ_CONTRIBUTION_VALIDATION.md)。
- [x] 助手独立预查 SQL29 完整 A × Z 商品查看：3,049 个商品的全部 22 个组合字段、该组 15 行 × 10 字段及排序与独立来源对照一致，18 个针对性用例通过。组内合计 20,626 件（90 天）、18,907 件（84 天），差额六天为 1,719 件；五个输入表、原始 CSV 及 27 份历史预检均未改动，临时库已清理。公开证据只保留汇总与指纹；见 [查看验证](docs/AZ_PRODUCT_DRILLDOWN_VALIDATION.md) 和 [预检记录](data/az_product_drilldown_preflight.json)。
- [x] 4E3 用户于 2026-10-29 截图确认 SQL29 完整 A × Z 组 15 行、10 列全部 PASS，两窗口可见；内存规范化后完整结果及有序成员指纹均与预检一致，20,626/18,907 件与 49 个零销量商品周等汇总一致。公开仅保存聚合与指纹，不保存真实商品编号、逐行结果或截图。见 [验收记录](data/az_product_drilldown_learner_acceptance.json) 和 [查看验收](docs/AZ_PRODUCT_DRILLDOWN_VALIDATION.md)。
- [x] 助手独立预查 SQL30 单商品周轨迹：3,049 个商品的 22 个组合字段、已验收 SQL29 的两项指纹、自动选择及 12 行 × 10 列的列名/列序/值/时间顺序均与来源对照一致，18 个针对性用例通过。12 周共 2,730 件，11 个正销量周及 1 个零销量周；五个输入表、两份原始 CSV 和 28 份历史预检不变，私有库已清理。见 [周轨迹验证](docs/AZ_LEADING_PRODUCT_WEEKLY_VALIDATION.md) 和 [聚合预检](data/az_leading_product_weekly_preflight.json)。
- [x] 4E4 用户于 2026-10-29 截图确认 SQL30 周轨迹 12 行、10 列全部 PASS：选中商品、完整有序轨迹与周销量向量的三个指纹均匹配；合计 2,730 件，11 个正销量周及 1 个零销量周，两窗口与复选框均核对。已显示周占比合计 100.0002%，末周累计为 100.0000%；两者分别来自逐行显示舍入与整数累计。见 [聚合验收](data/az_leading_product_weekly_learner_acceptance.json) 和 [周轨迹验收](docs/AZ_LEADING_PRODUCT_WEEKLY_VALIDATION.md)。
- [x] 助手独立预查 SQL31 门店比较：3,049 × 22 基线字段、选中商品 840 条日记录的 6 字段、门店映射、已验收 12 周向量及 11 行 × 11 列结果均与来源匹配，20 个针对性用例通过。前后六周合计为 62/2,668 件，差额 2,606 件，全部 10 店均增加；该现象本身不识别原因。五个完整分析快照及选中日记录、core/raw 门店映射三个相关投影保持不变；两份原始 CSV、29 份历史预检未变，私有库清理。见 [门店比较验证](docs/AZ_LEADING_PRODUCT_STORE_COMPARISON_VALIDATION.md) 和 [聚合预检](data/az_leading_product_store_comparison_preflight.json)。
- [x] 4E5 用户于 2026-10-29 截图确认 SQL31 门店比较 11 行、11 列全部 PASS：有序报告指纹与预检一致，两半窗、四位占比及 TOTAL 州空值核对通过。10 店前后六周合计 62/2,668 件，差额 2,606 件；全部门店增加，但不据此识别原因。见 [聚合验收](data/az_leading_product_store_comparison_learner_acceptance.json) 和 [门店比较验收](docs/AZ_LEADING_PRODUCT_STORE_COMPARISON_VALIDATION.md)。
- [x] 助手独立预查 SQL32 价格背景：3,049 × 22 基线字段、840 × 6 日记录、120 条原始价格的 4 字段及 12 行 × 12 列输出均与来源匹配，覆盖完整 120 个店周位置；36 个针对性用例通过。当前全部店周有价，价格整体范围 USD 2.00–2.68；110 次相邻同店周比较中 2 次涨价、1 次降价、107 次不变。110 是十店乘十一组相邻周，并非 110 家门店。五完整分析快照及四相关投影、三份来源 CSV 和 30 份历史预检未变，私有库清理。见 [价格背景验证](docs/AZ_LEADING_PRODUCT_PRICE_CONTEXT_VALIDATION.md) 和 [聚合预检](data/az_leading_product_price_context_preflight.json)。
- [x] 4E6 用户于 2026-10-29 截图确认 SQL32 价格背景 12 行、12 列全部 PASS：完整报告指纹匹配，首周三个比较值均为 NULL；120 个店周有价，110 次同店相邻周比较为 2 涨、1 跌、107 不变。见 [聚合验收](data/az_leading_product_price_context_learner_acceptance.json) 和 [价格背景验收](docs/AZ_LEADING_PRODUCT_PRICE_CONTEXT_VALIDATION.md)。
- [x] 4 描述性商品组合与波动里程碑完成：贡献结构、ABC/XYZ 及敏感性、组合分析与所选商品的周轨迹/门店/价格背景均有已验收输出；见 [阶段业务发现](docs/STAGE04_ASSORTMENT_FINDINGS.md)。这不代表项目全部完成、预测完成或价格因果已识别；截图验收也不等于独立测试了用户的概念理解。
- [x] 助手独立预查 SQL33 预测范围与时间：冻结已发布目录中的 FOODS_1 / CA_1 共 216 条序列，413,208 条训练记录的 6 字段与原始来源逐值一致，四个起点的 13 列输出及 33 个针对性用例通过。训练最多到 d_1913，未读取最终留出销量值；日历覆盖不等于目标销量记录已验收。来源文件与相关输入投影不变，临时文件已清理。见 [时间检查方法](docs/FORECAST_SCOPE_AND_TIME_AUDIT_VALIDATION.md) 和 [预检记录](data/forecast_scope_and_time_audit_preflight.json)。
- [x] 5A1 用户于 2026-10-29 截图确认 SQL33 范围与时间检查四行、13 列全部 PASS，规范报告指纹与预检一致：FOODS_1 / CA_1 共 216 条序列，四个训练截止日及 28 天日历区间核对通过。最后七/二十八天计数为 1,512/6,048 条记录，不能当作销量；见 [聚合验收](data/forecast_scope_and_time_audit_learner_acceptance.json) 和 [范围验收](docs/FORECAST_SCOPE_AND_TIME_AUDIT_VALIDATION.md)。
- [x] 助手独立预查 SQL34 季节朴素预测：24,192 行 × 13 字段预测与原始来源独立参考逐值一致，413,208 条训练记录的 6 字段一致；四个起点各 216 条序列、6,048 行预测，4 行 × 11 列汇总及 19 个针对性用例通过。来源、相关输入投影、只读验证前后的已存预测及历史证据均未改动，临时文件已清理。见 [基线验证](docs/SEASONAL_NAIVE_FORECASTS_VALIDATION.md) 和 [预检记录](data/seasonal_naive_forecasts_preflight.json)。这是候选预测生成，尚未计算误差或选择最终模型。
- [x] 5A2 用户于 2026-10-29 截图确认 SQL34 季节朴素预测四行、11 列全部 PASS，汇总指纹与预检一致：每起点 216 条序列、6,048 行预测，预测总量为最近七日总量的四倍。零预测行数为 3,208/3,336/2,972/2,956，表示预测位置而非零销量商品数。见 [聚合验收](data/seasonal_naive_forecasts_learner_acceptance.json) 和 [基线验收](docs/SEASONAL_NAIVE_FORECASTS_VALIDATION.md)；本步尚未评价预测误差。
- [x] 助手独立预查 SQL35 WEEKDAY4：24,192 行 × 15 字段新预测、413,208 条训练记录的 6 字段及原 SNAIVE7 的 24,192 行 × 13 字段均与独立来源参考一致；四行、12 列汇总及 19 个针对性用例通过。每起点 216 条序列、6,048 行预测，精确四分之一单位保留；原 SNAIVE7、来源、相关输入及历史证据未改，临时文件已清理。见 [均值预测验证](docs/WEEKDAY_MEAN_FORECASTS_VALIDATION.md) 和 [预检记录](data/weekday_mean_forecasts_preflight.json)。尚未进行误差比较或最终选型。
- [x] 5A3 用户于 2026-10-29 截图确认 SQL35 四行、12 列全部 PASS，规范报告指纹与预检一致：每起点 216 条序列、6,048 个预测位置；预测总量为 8,336.00/8,891.00/9,456.00/8,017.00，与各自最近 28 日输入总量相等。零值与小数预测位置计数均保留，不能当作商品数。见 [聚合验收](data/weekday_mean_forecasts_learner_acceptance.json) 和 [均值预测验收](docs/WEEKDAY_MEAN_FORECASTS_VALIDATION.md)。此验收只确认构建，不代表误差更小。
- [x] 助手独立预查 SQL36 开发集误差：36,288 条评分记录 × 12 字段、1,296 条序列诊断 × 16 字段与独立来源参考一致，精确字段/状态零差异，RMSSE 在声明容差内一致；413,208 条训练记录和两种各 24,192 行候选重建核对通过。六行、12 列汇总及 20 个针对性用例通过，每行均为 216 条序列、6,048 个预测位置，RMSSE 有效 216、未定义 0。来源、已存候选与历史证据未改，临时文件已清理。见 [比较验证](docs/DEVELOPMENT_FORECAST_ERRORS_VALIDATION.md) 和 [预检记录](data/development_forecast_errors_preflight.json)。只评分开发集，尚未最终选型。
- [x] 5A4 用户于 2026-10-29 截图确认 SQL36 六行、12 列全部 PASS，规范报告指纹与预检一致。每行 216 条序列、6,048 个评分位置、RMSSE 有效 216/未定义 0；WEEKDAY4 在三个开发窗的 MAE 与 macro RMSSE 均较低。见 [聚合验收](data/development_forecast_errors_learner_acceptance.json) 和 [开发集误差验收](docs/DEVELOPMENT_FORECAST_ERRORS_VALIDATION.md)。这是当前固定范围的开发集均值结果，不等于多数商品都改善或最终选型。
- [x] 助手独立预查 SQL37 成对序列：648 个起点/序列配对 × 17 字段与独立参考一致，精确配对、有效性及胜负标签零差异，浮点差值在声明容差内一致；六行、12 列汇总及 10 个针对性用例通过。每行参与 216、排除 0。原始训练、两候选和 SQL36 已验收报告/诊断指纹重建核对通过；来源、候选、历史证据及比较协议未改，临时文件已清理。见 [成对验证](docs/SERIES_FORECAST_IMPROVEMENTS_VALIDATION.md) 和 [预检记录](data/series_forecast_improvements_preflight.json)。
- [x] 5A5 用户于 2026-10-29 截图确认 SQL37 六行、12 列全部 PASS，规范报告指纹与预检一致；每行参与 216、排除 0。第二开发窗 MAE 为 108 改善/14 平局/94 变差，改善恰为 50%；各窗两指标的平均和中位差值均为负。见 [聚合验收](data/series_forecast_improvements_learner_acceptance.json) 和 [成对验收](docs/SERIES_FORECAST_IMPROVEMENTS_VALIDATION.md)。这不表示每条序列改善或最终模型已选定。
- [x] 记录试点开发判断：基于已观察的 SQL36/37 结果，将 WEEKDAY4 作为该 216 序列试点的优先开发基线，保留 SNAIVE7 对照；不按各商品未来误差事后择优，也不外推为全目录结论。见 [全目录扩展协议](docs/FULL_CATALOG_BASELINE_FORECASTS_PROTOCOL.md)。
- [x] 助手独立预查 SQL38 全目录构建：3,414,880 条近期输入 × 6 字段、6,829,760 条新预测 × 14 字段与原始来源独立参考逐值一致；八行、12 列汇总及 13 个针对性用例通过（5 个有效行为、5 个预期建表拒绝、3 个预期已存表验证拒绝）。每个起点/方法 30,490 序列、853,720 条预测。助手另核对试点 413,208×6 训练记录、原两表各 24,192 行的 13/15 字段及各自映射为 14 字段的重叠；SQL38 本身不读取或检查原试点表。来源、固定依赖、试点表与相关输入未变，临时文件清理完成。见 [全目录构建验证](docs/FULL_CATALOG_BASELINE_FORECASTS_VALIDATION.md) 和 [预检记录](data/full_catalog_baseline_forecasts_preflight.json)。尚未计算全目录误差或全历史 RMSSE 尺度。
- [x] 5A6 用户于 2026-10-29 截图确认 SQL38 全目录构建八行、12 列全部 PASS，规范报告指纹与预检一致；每个起点/方法 30,490 条序列、853,720 条预测，共 6,829,760 个预测位置。最近 7/28 天输入量及预测总量恒等式、零值与小数位置计数均核对通过。见 [聚合验收](data/full_catalog_baseline_forecasts_learner_acceptance.json) 和 [构建验收](docs/FULL_CATALOG_BASELINE_FORECASTS_VALIDATION.md)；尚未证明全目录预测更准确。
- [x] 助手独立预查 SQL39 全目录开发误差：58,327,370 条历史三字段、30,490 条索引映射、日历及事实日期/周一致性核对通过；6,829,760×14 已存预测、5,122,320×12 误差记录及 182,940×16 序列诊断与独立参考一致，精确字段/状态零差异，RMSSE 在声明容差内一致。六行、12 列汇总及 11 个针对性用例通过（6 个有效行为、5 个预期损坏拒绝）。第一窗两方法均 30,480 个有效尺度/10 个无正训练销量的未定义尺度，后两窗全部 30,490 有效；未定义序列仍参与 MAE/bias。来源、固定依赖、候选与输入未变，试点重叠评分指纹重现，临时文件已清理。见 [完整目录误差验证](docs/FULL_CATALOG_DEVELOPMENT_ERRORS_VALIDATION.md) 和 [预检记录](data/full_catalog_development_errors_preflight.json)。
- [x] 5A7 用户于 2026-10-29 截图确认 SQL39 全目录开发误差六行、12 列全部 PASS，规范报告指纹与预检一致。每行 30,490 条序列、853,720 个评分位置；第一窗 RMSSE 有效 30,480/未定义 10，后两窗全部 30,490 有效。WEEKDAY4 三窗平均 MAE 与 macro RMSSE 均较低；未定义原因/组指标属于独立预检证据。见 [聚合验收](data/full_catalog_development_errors_learner_acceptance.json) 和 [误差验收](docs/FULL_CATALOG_DEVELOPMENT_ERRORS_VALIDATION.md)。
- [x] 助手独立预查 SQL40 全目录成对覆盖：91,470 个起点/序列配对 × 17 字段及 182,940 条模型诊断 × 16 字段核对通过，精确字段/胜负/NULL 状态零差异，浮点根与差值在声明容差内一致。六行、12 列及 8 个针对性用例通过（6 个有效行为、2 个预期候选损坏拒绝）；原始历史三字段/完整映射/日历、已存候选、已验收 SQL38/39 指纹及试点配对重合均复核。未重新导出或声称新增直接比较 5,122,320 条日误差。97 个固定依赖、来源、候选及相关输入未变，临时文件清理完成。见 [成对验证](docs/FULL_CATALOG_PAIRED_IMPROVEMENT_VALIDATION.md) 和 [预检记录](data/full_catalog_paired_improvement_preflight.json)。
- [ ] 5A8 用户执行并验收 SQL40 全目录成对改善覆盖：三个开发起点 × MAE/RMSSE 共六行、12 列，报告参与/排除、两方法获胜与精确平局、胜率及平均/中位差值。MAE 保留全部 30,490，RMSSE 首窗正常排除 10 条未定义尺度；助手预检通过、用户尚未执行。差值为 WEEKDAY4 减 SNAIVE7，不使用显示舍入值判平局，不最终选型。
- [ ] 5 时间切分、预测基线、滚动验证与一次最终留出评估完成。
- [ ] 6 价格关联、销售异常候选清单与人工核查规则完成。
- [ ] 7 Retailrocket 数据审计、时点属性连接、分群、购物篮和漏斗分析完成。
- [ ] 8 Power BI 页面、指标和筛选行为逐页核对完成。
- [ ] 可选 A：Criteo 修订版实验模块访问确认、数据审核、估计与区间验证完成。
- [ ] 9 干净环境复跑、英文结论、中文讲解和最终作品集检查完成。

以上空框均表示未完成；创建文档不等于用户已完成练习。阶段 4 描述性里程碑、试点预测/开发比较及全目录构建/开发误差汇总均已验收，不声称已独立测试用户的概念理解。全目录成对覆盖已通过助手预检，等待用户执行验收；最终选型、最终留出评估、价格因果和自动刷新成果尚未完成。

## 下一次对话从这里继续

执行 [当前一步](docs/FIRST_STEP_ZH.md)：[SQL40](sql/40_compare_full_catalog_paired_improvement.sql) 检查整体平均优势是否覆盖多数商品门店序列。沿用全部 30,490 条序列、两种固定候选及三个开发窗口，只读返回三个起点 × MAE/RMSSE 共六行、12 列。MAE 比较全部序列；RMSSE 使用共同有效训练尺度，第一窗 10 条未定义保持排除并单独计数。精确绝对误差分子/平方误差分子决定胜负平局，胜率分母包含所有参与序列及平局；平均/中位差值为 WEEKDAY4 减 SNAIVE7，负值有利于 WEEKDAY4。新建编辑器粘贴全文件，用执行 SQL 脚本（默认 Alt+X），按 [成对方法](docs/FULL_CATALOG_PAIRED_IMPROVEMENT_VALIDATION.md) 核对。助手预检通过，用户尚未执行。三个开发窗 MAE 改善率为 54.0144%/53.8209%/55.8183%，RMSSE 为 72.1686%/73.1256%/75.9134%；所有平均/中位差值为负，但仍有大量平局和 SNAIVE7 更优序列。保留候选，不读取最终留出实际值或最终选型。先说明目的，再执行一个小步骤、验收并更新 GitHub。

GitHub 仓库：<https://github.com/quanchenginitial/retail-merchandising-analytics>。
