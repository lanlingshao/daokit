from abc import ABC
import logging
from typing import Generic, TypeVar

from daokit.clickhouse.client import ClickHouseWriteClient, ClickHouseReadClient
from daokit.clickhouse.model import CKModel

logger = logging.getLogger(__name__)


T = TypeVar("T")
ModelT = TypeVar("ModelT", bound=CKModel)
FetchParamT = TypeVar("FetchParamT")


class ClickHouseDao(Generic[ModelT], ABC):
    model: type[CKModel]

    BATCH_SIZE = 5000
    use_final = False

    def __init__(
        self,
        write_client: ClickHouseWriteClient,
        read_client: ClickHouseReadClient,
    ):
        self.write_client = write_client
        self.read_client = read_client

    def _build_where(self, param: FetchParamT) -> list[str]:
        return []

    def build_order_by(self, param: FetchParamT) -> str | None:
        return None

    def build_query_sql(self, param: FetchParamT, fields: list[str] = None) -> str:
        where = self._build_where(param)
        fields_str = "*"
        if fields:
            # 给字段加别名，针对自定义字段
            fields_str = ",".join([f"{field} as `{field}`" for field in fields])
        sql = f"""
        SELECT {fields_str}
        FROM {self.model.__tablename__}
        """
        if self.use_final:
            sql += " FINAL"
        if where:
            sql += f"\nWHERE {' AND '.join(where)}"
        order_by = self.build_order_by(param)
        if order_by:
            sql += f"\nORDER BY {order_by}"
        if getattr(param, "page", None) and getattr(param, "page_size", None):
            offset = (param.page - 1) * param.page_size
            sql += f"\nLIMIT {param.page_size} \nOFFSET {offset}"

        logger.debug(sql)

        return sql

    def build_count_sql(self, param: FetchParamT) -> str:
        where = self._build_where(param)
        sql = f"""
        SELECT count() AS count
        FROM {self.model.__tablename__}
        """
        if where:
            sql += f"\nWHERE {' AND '.join(where)}"
        return sql

    async def fetch_dicts(self, param: FetchParamT, fields: list[str] = None) -> list[dict]:
        sql = self.build_query_sql(param, fields)
        return await self.read_client.fetch_all(sql)

    async def fetch_dicts_with_count(self, param: FetchParamT, fields: list[str] = None) -> tuple[list[dict], int]:
        dicts = await self.fetch_dicts(param, fields)
        count = await self.count(param)
        return dicts, count

    async def fetch_models(self, param: FetchParamT, fields: list[str] = None) -> list[ModelT]:
        dicts = await self.fetch_dicts(param, fields)
        models = []
        for d in dicts:
            m = self.model.from_dict(d)
            models.append(m)
        return models

    async def count(self, param: FetchParamT) -> int:
        where = self._build_where(param)
        sql = f"""
                SELECT count()
                FROM {self.model.__tablename__} FINAL
                """
        if len(where):
            sql += f"\nWHERE {' AND '.join(where)}"

        result = await self.read_client.fetch_one(sql)
        if not result:
            return 0
        return list(result.values())[0]

    async def insert_batch(self, items: list[ModelT]):
        if not items:
            return

        cols = self.model.columns()
        sql = f"""
        INSERT INTO {self.model.__tablename__}
        ({",".join(cols)})
        VALUES
        """

        for i in range(0, len(items), self.BATCH_SIZE):
            batch = items[i:i + self.BATCH_SIZE]
            rows = [item.to_tuple() for item in batch]
            await self.write_client.insert_batch(sql, rows)
