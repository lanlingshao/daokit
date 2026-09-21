# daokit

`daokit` is an asynchronous data-access toolkit built on SQLAlchemy, asyncmy,
asynch, and clickhouse-connect. It provides reusable DAO base classes and
clients for MySQL and ClickHouse, while leaving application-specific query
rules in small, explicit DAO subclasses.

## Features

- Asynchronous MySQL client based on SQLAlchemy + asyncmy.
- Generic MySQL CRUD, pagination, soft deletion, and batch-upsert helpers.
- Separate ClickHouse write (TCP) and query (HTTP) clients.
- ClickHouse SQL construction with identifier and field validation.
- Small model helpers for serializing ClickHouse dataclasses.

## Installation

The project requires Python 3.11 or later.

```bash
uv sync
```

Or install the package dependencies with pip:

```bash
pip install aiohttp==3.11.18 asynch==0.3.1 asyncmy==0.2.10 \
  clickhouse-connect==1.1.1 greenlet==3.2.3 pyarrow==24.0.0 sqlalchemy==2.0.41
```

## MySQL

1. Define a SQLAlchemy model and a fetch-parameter dataclass.
2. Subclass `MysqlDao` and implement `_build_where_clauses`, `_build_param`,
   `_build_unique_param`, and (when using quick upsert) `_upsert_update_columns`.
3. Create the client and DAO in the application layer.
4. Pass an application-managed `AsyncSession` to every DAO call.

The complete runnable example is in [examples/mysql/user_dao.py](examples/mysql/user_dao.py).

```python
async with mysql_client.session_context(transaction=True) as session:
    user = UserModel(username="admin", email="admin@example.com")
    await user_dao.create(session, user)
    await user_dao.update(user, UserModel(username="admin-2", email="admin@example.com"))
# The transaction is committed when the block exits normally.
```

### Session and transaction ownership

Session / Transaction are MySQL application-layer resource management;
DAO does not create sessions or commit transactions. The application selects
the session and transaction boundary, and supplies that session to DAO methods.
This makes multiple DAO operations atomic when they must succeed or fail
together.

`MysqlClient.session_context(transaction=True)` commits on successful exit and
rolls back when an exception escapes the block. Use `session_context()` for
read-only work or when the application already manages the transaction.
`MysqlDao.create()` and `batch_insert()` call `flush()` so generated IDs are
available before the transaction is committed.

## ClickHouse

ClickHouse uses distinct clients for writes and queries:

- `ClickHouseWriteClient` uses a TCP connection pool and provides efficient
  `batch_insert`.
- `ClickHouseQueryClient` uses HTTP, reconnects after connection failures, and
  supports dictionary and Arrow results.

Define a dataclass model and subclass `ClickHouseDao` to translate the fetch
parameter into a parameterized `WHERE` clause. The full example is in
[examples/clickhouse/user_dao.py](examples/clickhouse/user_dao.py).

```python
users = await user_dao.fetch_models(UserFetchParam(username="admin"))
await user_dao.batch_insert([
    UserModel(username="admin", email="admin@example.com"),
])
```

Close both clients during application shutdown:

```python
await write_client.close()
await read_client.close()
```

## Tests

The test suite is self-contained and does not require running MySQL or
ClickHouse instances. It verifies DAO SQL generation, batching, delegated
client calls, model conversion, and safety checks.

```bash
uv run python -m unittest discover -s tests -v
```

## Examples

- [MySQL user DAO](examples/mysql/user_dao.py)
- [ClickHouse user DAO](examples/clickhouse/user_dao.py)

Before running an example, create the table described at the top of its file
and update its connection configuration for your environment.
