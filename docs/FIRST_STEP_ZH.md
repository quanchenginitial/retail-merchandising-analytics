# 当前一步：建立商品项目的 DuckDB 连接

更新日期：2026-10-27（Australia/Sydney）。

三份核心 CSV 已由你下载并提供，助手已完成源文件扫描，33 项记录的检查通过。源文件保持在 `D:/database/m5-forecasting-accuracy/`，无需重新下载或搬动。实际结果见 [源文件审计](M5_SOURCE_AUDIT.md)。目前尚未建立或验收你的项目数据库连接。

## 这一步的目的

CSV 是输入文件，DuckDB 数据库用于保存后续的原始表、清洗表和分析模型，DBeaver 则是连接数据库并编写 SQL 的操作界面。这一步只建立连接并确认连接到正确的新数据库。

## 本次操作

1. 打开 DBeaver，选择新建数据库连接，搜索并选择 **DuckDB**。
2. 将数据库文件路径设为 `D:/database/retail_merchandising.duckdb`，连接名设为 `retail_merchandising`。此路径在本轮检查时不存在，用于新项目；不选择银行项目数据库，也不把 CSV 文件当作数据库路径。若界面提供创建数据库选项，使用该选项。
3. 完成连接，在该连接下打开 SQL 编辑器，执行：

```sql
SELECT
    current_database() AS database_name,
    version() AS duckdb_version;
```

也可打开仓库中的 [连接检查 SQL](../sql/01_connection_check.sql)。它只读取连接信息，不建表、不加载数据。

## 我们怎样验收

结果应只有一行，`database_name` 应为 `retail_merchandising`，另一个字段返回你的实际 DuckDB 版本。把结果发回来即可；如出现报错，提供报错内容，我们先解决连接问题。

助手在本机独立复核价格数据时使用的命令行版本是 v1.5.5；DBeaver 的驱动版本需以你实际查询结果为准，两者不提前视为相同。

## 下一步

连接通过后，只导入最小的 `calendar.csv` 到原始层，检查 1,969 行、14 列与日期字段，再进入较大的销量和价格文件。不要一次导入全部文件或提前做宽转长。
