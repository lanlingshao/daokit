import re
from abc import ABC
import logging
from typing import Generic, TypeVar

from daokit.clickhouse.client import ClickHouseWriteClient, ClickHouseQueryClient
from daokit.clickhouse.model import CKModel

logger = logging.getLogger(__name__)


T = TypeVar("T")
ModelT = TypeVar("ModelT", bound=CKModel)
FetchParamT = TypeVar("FetchParamT")

_IDENTIFIER_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*$"
)


class ClickHouseDao(Generic[ModelT], ABC):
    model: type[CKModel]

    BATCH_SIZE = 5000
    use_final = False

    def __init__(
        self,
        write_client: ClickHouseWriteClient,
        read_client: ClickHouseQueryClient,
    ):
        self.write_client = write_client
        self.read_client = read_client

    # ------------------------------------------------------------------
    # identifier
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_identifier(value: str) -> str:
        # prevent the table name is "user; DROP TABLE xxx"
        if not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError(f"Invalid SQL identifier: {value!r}")
        return value

    def _table_name(self) -> str:
        return self._validate_identifier(self.model.__tablename__)

    def _validate_fields(self, fields: list[str]) -> list[str]:
        allowed = set(self.model.columns())
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(f"Invalid fields: {sorted(invalid)}")
        return fields

    def _build_fields(self, fields: list[str] | None) -> str:
        if not fields:
            return "*"
        fields = self._validate_fields(fields)
        return ",".join(
            f"`{field}`"
            for field in fields
        )

    def _build_where(self, param: FetchParamT) -> tuple[list[str], dict]:
        return [], {}

    def build_order_by(self, param: FetchParamT) -> str | None:
        return None

    def _build_from(self) -> str:
        sql = f"FROM `{self._table_name()}`"
        if self.use_final:
            sql += " FINAL"
        return sql

    def _build_query(self, param: FetchParamT, fields: list[str] | None = None) -> tuple[str, dict]:
        where, parameters = self._build_where(param)

        fields_str = self._build_fields(fields)

        sql = f"""
              SELECT {fields_str}
              {self._build_from()}
              """

        if where:
            sql += "\nWHERE " + " AND ".join(where)

        order_by = self.build_order_by(param)
        if order_by:
            sql += f"\nORDER BY {order_by}"

        page = getattr(param, "page", None)
        page_size = getattr(param, "page_size", None)
        if page is not None and page_size is not None:
            if page < 1:
                raise ValueError("page must be >= 1")
            if page_size <= 0:
                raise ValueError("page_size must be > 0")
            offset = (page - 1) * page_size

            sql += """
                   LIMIT {limit:UInt64}
                   OFFSET {offset:UInt64}
                   """

            parameters["limit"] = page_size
            parameters["offset"] = offset

        logger.debug(
            "ClickHouse query: %s, parameters=%s",
            sql,
            parameters,
        )

        return sql, parameters

    def _build_count(self, param: FetchParamT) -> tuple[str, dict]:
        where, parameters = self._build_where(param)
        sql = f"""
              SELECT count() AS count
              {self._build_from()}
              """
        if where:
            sql += f"\nWHERE {' AND '.join(where)}"
        return sql, parameters

    async def fetch_dicts(self, param: FetchParamT, fields: list[str] | None = None) -> list[dict]:
        sql, parameters = self._build_query(param, fields)
        return await self.read_client.fetch_all(sql, parameters=parameters)

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
        sql, parameters = self._build_count(param)
        result = await self.read_client.fetch_one(sql, parameters=parameters)
        if not result:
            return 0
        return int(result["count"])

    async def batch_insert(self, items: list[ModelT]):
        """
        limit the number of rows inserted per batch
        限制每批次插入的行数
        """

        if not items:
            return

        columns = self._validate_fields(self.model.columns())
        columns_sql = ",".join(
            f"`{column}`"
            for column in columns
        )

        sql = f"""
              INSERT INTO `{self._table_name()}`
              ({columns_sql})
              VALUES
              """

        for i in range(0, len(items), self.BATCH_SIZE):
            batch = items[i:i + self.BATCH_SIZE]
            rows = [item.to_tuple() for item in batch]
            await self.write_client.batch_insert(sql, rows)
