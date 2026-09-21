# daokit

`daokit` 是一个异步数据访问工具库，基于 SQLAlchemy、asyncmy、asynch 和
clickhouse-connect 构建。它为 MySQL 和 ClickHouse 提供可复用的客户端与 DAO
基类，同时将业务特有的查询逻辑保留在简洁、明确的 DAO 子类中。

## 特性

- 基于 SQLAlchemy + asyncmy 的异步 MySQL 客户端。
- MySQL 通用 CRUD、分页、软删除及批量 upsert 能力。
- 分离的 ClickHouse 写入（TCP）和查询（HTTP）客户端。
- 带表名、字段名校验的 ClickHouse SQL 构造能力。
- 用于 ClickHouse dataclass 模型序列化的轻量辅助方法。

## 安装

项目需要 Python 3.11 或更高版本。

```bash
uv sync
```

也可以使用 pip 安装依赖：

```bash
pip install aiohttp==3.11.18 asynch==0.3.1 asyncmy==0.2.10 \
  clickhouse-connect==1.1.1 greenlet==3.2.3 pyarrow==24.0.0 sqlalchemy==2.0.41
```

## MySQL 使用方式

1. 定义 SQLAlchemy Model 和查询参数 dataclass。
2. 继承 `MysqlDao`，实现 `_build_where_clauses`、`_build_param`、
   `_build_unique_param`；使用快速 upsert 时，还需要实现
   `_upsert_update_columns`。
3. 在应用层创建 MySQL 客户端和 DAO。
4. 调用 DAO 时传入由应用层管理的 `AsyncSession`。

完整可运行示例见 [examples/mysql/user_dao.py](examples/mysql/user_dao.py)。

```python
async with mysql_client.session_context(transaction=True) as session:
    user = UserModel(username="admin", email="admin@example.com")
    await user_dao.create(session, user)
    await user_dao.update(user, UserModel(username="admin-2", email="admin@example.com"))
# 正常退出代码块后自动提交事务。
```

### Session 与 Transaction 的职责

Session / Transaction 属于 MySQL 应用层的资源管理；DAO 不负责创建和提交事务。
应用层决定 Session 和事务边界，并将同一个 Session 传给 DAO 方法；因此，多个
DAO 操作需要同时成功或失败时，可以被包裹在同一个事务中。

`MysqlClient.session_context(transaction=True)` 在代码块正常结束时提交事务，
异常向外抛出时回滚。只读操作或应用层已经管理事务时使用
`session_context()`。`MysqlDao.create()` 和 `batch_insert()` 会调用 `flush()`，
以便在提交前获取数据库生成的 ID。

## ClickHouse 使用方式

ClickHouse 使用职责分离的两个客户端：

- `ClickHouseWriteClient`：通过 TCP 连接池提供高效的 `batch_insert`。
- `ClickHouseQueryClient`：通过 HTTP 查询，连接异常后会重连，并支持字典和
  Arrow 结果。

定义 dataclass Model 后，继承 `ClickHouseDao`，将查询参数转换为参数化的
`WHERE` 条件。完整示例见
[examples/clickhouse/user_dao.py](examples/clickhouse/user_dao.py)。

```python
users = await user_dao.fetch_models(UserFetchParam(username="admin"))
await user_dao.batch_insert([
    UserModel(username="admin", email="admin@example.com"),
])
```

应用退出时关闭两个客户端：

```python
await write_client.close()
await read_client.close()
```

## 测试

测试套件不依赖正在运行的 MySQL 或 ClickHouse 服务，覆盖 DAO 的 SQL 构造、
分批处理、客户端调用委托、模型转换和安全校验。

```bash
uv run python -m unittest discover -s tests -v
```

## 示例

- [MySQL 用户 DAO](examples/mysql/user_dao.py)
- [ClickHouse 用户 DAO](examples/clickhouse/user_dao.py)

运行示例前，请先创建对应文件顶部说明的表，并按实际环境更新连接配置。
