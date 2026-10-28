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
- [ ] 4E2 用户执行并验收 SQL28 ABC × XYZ 组合销量贡献：只读查询全部 16 个组合及 TOTAL，比较商品占比、90 天销量占比和 84 天销量占比；空组合保留为 0，两个窗口分母分开。助手预检通过，用户尚未执行。
- [ ] 4 商品结构、ABC/XYZ、趋势分析通过检查。
- [ ] 5 时间切分、预测基线、滚动验证与一次最终留出评估完成。
- [ ] 6 价格关联、销售异常候选清单与人工核查规则完成。
- [ ] 7 Retailrocket 数据审计、时点属性连接、分群、购物篮和漏斗分析完成。
- [ ] 8 Power BI 页面、指标和筛选行为逐页核对完成。
- [ ] 可选 A：Criteo 修订版实验模块访问确认、数据审核、估计与区间验证完成。
- [ ] 9 干净环境复跑、英文结论、中文讲解和最终作品集检查完成。

以上空框均表示未完成；创建文档不等于用户已完成练习。类别、部门、商品集中度、ABC 基线及敏感性、12 周商品销量、波动指标、XYZ 基线及敏感性、ABC × XYZ 组合表及商品数矩阵均已验收。组合销量贡献已通过助手预检，尚待用户执行验收；预测误差、模型提升和自动刷新成果尚未完成。

## 下一次对话从这里继续

执行 [当前一步](docs/FIRST_STEP_ZH.md)：SQL28 在已验收分类下比较各组合的商品数与历史销量贡献，不更改标签或输入表。在 retail_merchandising 连接中新建编辑器并粘贴 SQL28 全文件，使用执行 SQL 脚本（默认 Alt+X）；这是一条只读查询，不建表，返回全部 16 个组合及 TOTAL 共 17 行、10 列，空组合也保留。商品占比分母为全部 3,049 个商品；90 天与 84 天销量占比分母分别为 3,767,196 件和 3,536,539 件。先核对精确整数总量及行列边际，再展示四位小数占比，分母为零时占比为 NULL。ABC 的 2016-01-26 至 2016-04-24 与 XYZ 的 2016-01-30 至 2016-04-22 均显示；两个嵌套窗口不能当作前后期增长比较，也不能相加。助手预检通过，用户尚未执行。本步分析记录销量贡献，不计算金额或直接给出库存行动。先说明目的，再执行一个小步骤、验收并更新 GitHub。

GitHub 仓库：<https://github.com/quanchenginitial/retail-merchandising-analytics>。
