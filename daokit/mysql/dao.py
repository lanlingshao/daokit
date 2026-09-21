from collections.abc import Sequence
from itertools import islice
from typing import Generic, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from daokit.exception import DaoException
from daokit.mysql.client import MysqlClient
from daokit.mysql.model import BaseModel
from daokit.util.time import now_utc


T = TypeVar("T")
ModelT = TypeVar("ModelT", bound=BaseModel)
FetchParamT = TypeVar("FetchParamT")


class AsyncMysqlDao(Generic[ModelT, FetchParamT]):
    # 子类必须指定
    model: type[ModelT]

    BATCH_SIZE = 5000

    def __init__(
        self,
        mysql_client: MysqlClient,
    ):
        self.mysql_client = mysql_client

    async def create(self, session: AsyncSession, item: ModelT) -> None:
        session.add(item)
        # 这里需要flush，只有这样才能在程序里面获取插入数据的id
        await session.flush()

    async def batch_insert(self, session: AsyncSession, items: list[ModelT]) -> None:
        session.add_all(items)
        await session.flush()

    async def update(self, old: ModelT, new: ModelT) -> None:
        for attr in new.__dict__:
            if not attr.startswith("_"):
                setattr(old, attr, getattr(new, attr))
        # 当new_data_obj并没有改变obj中的数据时，sqlalchemy默认认为数据没变，不会更新updated字段, 所以这里需要手动更新updated字段
        if hasattr(old, "updated"):
            old.updated = now_utc()

    async def get_by_id(self, session: AsyncSession, id: int) -> ModelT | None:
        return await self.fetch_one(session, self._build_param(id=id))

    async def count(self, session: AsyncSession, param: FetchParamT) -> int:
        stmt = select(self.model)
        where_clauses = self._build_where_clauses(param)
        if where_clauses:
            stmt = stmt.where(*where_clauses)
        stmt = select(func.count()).select_from(stmt.subquery())
        count = await session.scalar(stmt)
        if count is None:
            return 0
        return count

    async def fetch(self, session: AsyncSession, param: FetchParamT, fields: tuple | None = None) -> Sequence[ModelT]:
        """
        fields: 不能是字符串，而是model.字段名，如: (BankFinancialModel.report_date, BankFinancialModel.security_id)
        """
        stmt = select(self.model)
        where_clauses = self._build_where_clauses(param)
        if where_clauses:
            stmt = stmt.where(*where_clauses)
        stmt = self._apply_offset(stmt, param)
        stmt = self._apply_order(stmt, param)
        if fields:
            stmt = stmt.options(load_only(*fields))
        result = await session.scalars(stmt)
        return result.all()

    async def fetch_with_count(
        self, session: AsyncSession, param: FetchParamT, fields: tuple | None = None,
    ) -> tuple[Sequence[ModelT], int]:
        items = await self.fetch(session, param, fields)
        count = await self.count(session, param)
        return items, count

    async def fetch_one(self, session: AsyncSession, param: FetchParamT) -> ModelT | None:
        records = await self.fetch(session, param)
        return records[0] if records else None

    async def upsert(self, session: AsyncSession, item: ModelT) -> None:
        old_item = await self.fetch_one(session, self._build_unique_param(item))
        if old_item:
            await self.update(old_item, item)
        else:
            await self.create(session, item)

    async def batch_upsert(self, session: AsyncSession, items: list[ModelT]) -> None:
        for item in items:
            await self.upsert(session, item)

    async def quick_batch_upsert(self, session: AsyncSession, items: list[ModelT]) -> None:
        # 快速批量插入或更新数据，比batch_upsert快很多
        if not items:
            return

        rows = [
            {
                column.name: getattr(item, column.name)
                for column in item.__table__.columns
            }
            for item in items
        ]

        for batch in self._chunked(rows, self.BATCH_SIZE):
            stmt = insert(self.model).values(batch)
            update_columns = {
                col: getattr(stmt.inserted, col)
                for col in self._upsert_update_columns()
            }
            stmt = stmt.on_duplicate_key_update(**update_columns)
            await session.execute(stmt)

    def _upsert_update_columns(self) -> list[str]:
        """
        ON DUPLICATE KEY UPDATE 时需要更新的字段
        """
        raise NotImplementedError

    async def quick_batch_upsert_rows(self, session: AsyncSession, rows: list[dict]) -> None:
        if not rows:
            return

        for batch in self._chunked(rows, self.BATCH_SIZE):
            stmt = insert(self.model).values(batch)
            update_columns = {col: getattr(stmt.inserted, col) for col in self._upsert_update_columns()}

            stmt = stmt.on_duplicate_key_update(**update_columns)
            await session.execute(stmt)

    @staticmethod
    def _chunked(items, size):
        iterator = iter(items)

        while True:
            batch = list(islice(iterator, size))
            if not batch:
                break
            yield batch

    async def soft_delete(self, session: AsyncSession, param: FetchParamT):
        if not hasattr(self.model, "deleted"):
            raise DaoException(msg="data not support soft delete")
        items = await self.fetch(session, param)
        if not items:
            return
        for item in items:
            item.deleted = 1

    async def delete(self, session: AsyncSession, param: FetchParamT):
        where_clauses = self._build_where_clauses(param)
        if where_clauses:
            # where_clause为空不允许删除，避免删除全表数据
            stmt = delete(self.model).where(*where_clauses)
            await session.execute(stmt)

    # ---------- 子类需要实现的方法 ----------

    def _build_unique_param(self, item: ModelT) -> FetchParamT:
        """
        upsert / update_if_exist 使用
        """
        raise NotImplementedError

    def _build_param(self, **kwargs) -> FetchParamT:
        raise NotImplementedError

    def _build_where_clauses(self, param: FetchParamT):
        """
        把 FetchParam 转成 SQLAlchemy where 条件
        """
        raise NotImplementedError

    def _apply_offset(self, stmt, param: FetchParamT):
        page = getattr(param, "page", None)
        page_size = getattr(param, "page_size", None)
        if page and page_size:
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        elif page_size:
            stmt = stmt.limit(page_size)
        return stmt

    def _apply_order(self, stmt, param: FetchParamT):
        return stmt
