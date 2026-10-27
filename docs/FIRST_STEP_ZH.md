# 当前一步：建立精确价格清洗表

更新日期：2026-10-27（Australia/Sydney）。

你的最新截图中，日历清洗表 13 项全部 PASS，日期与整数转换、事件空值及还原对账均已验收。现在建立 stg.m5_prices，暂不展开销量或计算销售金额。

## 先看价格精度与类型

助手实际检查了全部 6,841,121 条来源价格：624,039 条有一位小数、6,217,082 条有两位小数，最多两位；整数部分最多三位。因此这份快照可以无损存入 DECIMAL(18,2)，其中 18 表示总位数上限、2 表示固定小数位数。

| 字段 | 清洗层类型 |
| --- | --- |
| store_id、item_id | VARCHAR |
| wm_yr_wk | INTEGER |
| sell_price | DECIMAL(18,2) |

例如原始 2.0 在清洗层显示为 2.00，数值不变。原始写法仍保留在 raw.m5_prices。这里核对的是精确数值等价，不能再要求价格文本逐字相同。

## 本次只执行这一份脚本

1. 打开 [09_stage_prices.sql](../sql/09_stage_prices.sql)，复制全部内容。
2. 在 DBeaver 当前 retail_merchandising 连接中粘贴，按“执行 SQL 脚本”（默认 Alt+X）运行整份脚本一次。
3. 等待最后 13 行结果，将截图发回。

脚本在转换前检查当前精度规则：允许 1.2500 这种仅多出尾随零的写法，拒绝 1.2501 这种需要舍入的值；超出范围、缺失或非正价格也会停止建表。周编号先核实为不以零开头的五位数字。原始表保持不变。

## 预期结果

所有 13 行 status 均为 PASS。

| check_name | 预期 |
| --- | ---: |
| staging_rows | 6841121 |
| column_count | 4 |
| schema_mismatch_count | 0 |
| distinct_item_store_week_keys | 6841121 |
| missing_core_rows、nonpositive_price_rows | 各 0 |
| minimum_price、maximum_price | 0.01、107.32 |
| distinct_item_store_pairs | 30490 |
| distinct_weeks | 282 |
| raw_contract_violation_rows | 0 |
| raw_canonical_only_rows、staging_canonical_only_rows | 各 0 |

最后两项比较原始表和清洗表的精确价格值：只统一整数前导零、小数尾随零的写法，不先把原始价格舍入。这样既能接受 2.0 与 2.00 等价，又能发现 2.0001 被错误变成 2.00。重复次数也参与比较。

如果提示表已存在，不要删表，只执行 VALIDATION 注释之后的 WITH 查询。其他报错或 FAIL 请保留现状并发回。

## 验收范围

助手已在独立临时数据库验证 13/13 PASS，并完成 7 个针对性用例；详见 [验证说明](PRICE_STAGING_VALIDATION.md)。你的价格清洗表仍待实际结果确认。

本步不验证每条日销量的价格覆盖，也不生成销售金额。通过后，再推进销量宽转长与对应的数量核对。
