import asyncio
from collections.abc import Callable
from typing import Any

import clickhouse_connect
import pyarrow as pa
from asynch import Pool
from clickhouse_connect.driver.asyncclient import AsyncClient
from clickhouse_connect.driver.exceptions import ClickHouseError


class ClickHouseWriteClient:
    """
    clickhouse 连接池
    特点：
    1、基于 clickhouse-driver 的异步封装，插入性能高
    2、适合 CDC 顺序消费场景
    """
    def __init__(self, conf: dict):
        self.conf = conf
        self._pool = self._create_pool()

    def _create_pool(self) -> Pool:
        return Pool(
            minsize=self.conf.get("minsize", 1),
            maxsize=self.conf.get("maxsize", 10),
            user=self.conf["username"],
            password=self.conf["password"],
            host=self.conf["host"],
            port=self.conf["tcp_port"],
            database=self.conf["database"],
        )

    async def execute(self, sql: str):
        """
        执行任意 SQL

        适用于：
        - INSERT SELECT
        - ALTER
        - DELETE
        - OPTIMIZE
        - CREATE
        """
        async with self._pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(sql)

    async def insert_batch(self, sql: str, rows: list[tuple]):
        """
        批量插入
        """
        if not rows:
            return
        async with self._pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.executemany(sql, rows)


class ClickHouseReadClient:
    """
    分析用 ClickHouse 客户端
    使用clickhouse-connect库，适合分析场景，支持自动重连和Arrow查询
    """

    def __init__(self, conf: dict):
        self.conf = conf

        self._client: AsyncClient | None = None
        self._connected = False

        self._connect_lock = asyncio.Lock()

    async def _create_client(self) -> AsyncClient:
        return await clickhouse_connect.get_async_client(
            host=self.conf["host"],
            port=self.conf.get("http_port", 8123),
            username=self.conf["username"],
            password=self.conf["password"],
            database=self.conf["database"],
        )

    async def _connect(self):
        if self._connected:
            return

        async with self._connect_lock:
            if self._connected:
                return

            client = await self._create_client()

            try:
                await client.command("SELECT 1")
            except Exception:
                try:
                    await client.close()
                except Exception:
                    pass
                raise

            self._client = client
            self._connected = True

    async def _ensure_connected(self):
        if not self._connected:
            await self._connect()

    async def _reset_connection(self):
        self._connected = False

        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass

        self._client = None

    async def _reconnect(self):
        await self._reset_connection()
        await self._connect()

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        """
        判断是否属于连接异常
        """
        connection_errors = (
            ConnectionError,
            BrokenPipeError,
            TimeoutError,
            OSError,
            ClickHouseError,
        )

        return isinstance(exc, connection_errors)

    async def close(self):
        await self._reset_connection()

    async def _execute(
        self,
        operation: Callable[[], Any],
        retry: bool = True,
    ):
        await self._ensure_connected()
        try:
            return await operation()
        except Exception as e:
            if not self._is_connection_error(e):
                raise
            await self._reset_connection()
            if not retry:
                raise
            await self._connect()
            return await operation()

    # command
    async def execute(self, sql: str):
        """
        DDL/DML

        CREATE
        ALTER
        DELETE
        TRUNCATE
        OPTIMIZE
        """
        async def operation():
            return await self._client.command(sql)
        return await self._execute(operation)

    # query
    async def fetch_one(self, sql: str) -> dict | None:
        async def operation():
            result = await self._client.query(sql)
            rows = list(result.named_results())
            return rows[0] if rows else None

        return await self._execute(operation)

    async def fetch_all(self, sql: str) -> list[dict]:
        async def operation():
            result = await self._client.query(sql)
            rows = list(result.named_results())
            return rows

        return await self._execute(operation)

    # Arrow
    async def query_arrow(self, sql: str) -> pa.Table:
        """
        返回 PyArrow Table

        适合：
        - 因子计算
        - DuckDB
        - Polars
        - Pandas
        """
        async def operation():
            return await self._client.query_arrow(sql)

        return await self._execute(operation)

    async def query_arrow_stream(self, sql: str):
        """
        Arrow RecordBatchReader

        适合超大结果集
        """
        async def operation():
            return await self._client.query_arrow_stream(sql)

        return await self._execute(operation)
