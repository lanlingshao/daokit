from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    AsyncSessionTransaction,
    async_sessionmaker,
    create_async_engine,
)


# 借鉴perfect的src/prefect/server/database/interface.py中的PrefectDBInterface
class MysqlClient:
    def __init__(self, database_conf: dict):
        self.conf = database_conf
        self._engine = self._create_engine()
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    def _create_engine(self) -> AsyncEngine:
        url = "mysql+asyncmy://{username}:{password}@{host}:{port}/{database}".format(
            username=self.conf["username"],
            password=self.conf["password"],
            host=self.conf["host"],
            port=self.conf["port"],
            database=self.conf["database"],
        )
        engine = create_async_engine(
            url,
            pool_size=self.conf["pool_size"],
            max_overflow=self.conf["max_overflow"],
            pool_timeout=self.conf["pool_timeout"],
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        return engine

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def _session(self) -> AsyncSession:
        return self._session_factory()

    @asynccontextmanager
    async def session_context(self, transaction: bool = False):
        """
        get session context

        Example:
            async with mysql_client.session_context() as session:
                ...

            async with mysql_client.session_context(
                begin_transaction=True
            ) as session:
                ...

        Provides a SQLAlchemy session and a context manager for opening/closing
        the underlying connection.

        Args:
            transaction: if True, the context manager will begin a SQL transaction.
                Exiting the context manager will COMMIT or ROLLBACK any changes.
        """
        session = await self._session()
        async with session:
            if transaction:
                async with self.begin_transaction(session):
                    yield session
            else:
                yield session

    @asynccontextmanager
    async def begin_transaction(self, session: AsyncSession) -> AsyncGenerator[AsyncSessionTransaction, None]:
        """
        begin transaction

        begin内部实现了回滚和commit，调用链如下：
        it implements rollback and commit internally. The call chain is:
        AsyncSessionTransaction -> AsyncSession -> AsyncSessionTransaction
        """

        async with session.begin() as transaction:
            yield transaction

    async def close(self):
        await self._engine.dispose()

    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        *,
        commit: bool = True,
    ) -> Result:
        """
        execute SQL（INSERT / UPDATE / DELETE / DDL）

        Example:
            await client.execute(
                "DELETE FROM user WHERE id = :id",
                {"id": 1},
            )

            await client.execute(
                '''
                ALTER TABLE factor_value
                ADD PARTITION (...)
                '''
            )
        """

        async with self.session_context(transaction=commit) as session:
            result = await session.execute(
                text(sql),
                params or {},
            )

            return result

    async def executemany(
        self,
        sql: str,
        params_list: Sequence[dict[str, Any]],
        *,
        commit: bool = True,
    ) -> Result:
        """
        batch execute SQL（INSERT / UPDATE / DELETE / DDL）

        Example:
            await client.executemany(
                '''
                INSERT INTO user(id, name)
                VALUES(:id, :name)
                ''',
                [
                    {"id": 1, "name": "a"},
                    {"id": 2, "name": "b"},
                ]
            )
        """

        async with self.session_context(transaction=commit) as session:
            result = await session.execute(
                text(sql),
                list(params_list),
            )
            return result

    async def fetch_all(self, sql: str, params: dict[str, Any] | None = None) -> list[dict]:
        """
        fetch all rows
        """

        async with self.session_context() as session:
            result = await session.execute(
                text(sql),
                params or {},
            )
            rows = result.mappings().all()
            return [dict(row) for row in rows]

    async def fetch_one(self, sql: str, params: dict[str, Any] | None = None) -> dict | None:
        """
        fetch one row
        """
        async with self.session_context() as session:
            result = await session.execute(
                text(sql),
                params or {},
            )
            row = result.mappings().first()
            if row is None:
                return None

            return dict(row)

    async def fetch_scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """
        fetch the first column of the first row
        """
        async with self.session_context() as session:
            result = await session.execute(
                text(sql),
                params or {},
            )
            return result.scalar()
