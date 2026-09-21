from dataclasses import dataclass
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

from daokit.clickhouse.dao import ClickHouseDao
from daokit.clickhouse.model import CKModel


@dataclass
class EventModel(CKModel):
    __tablename__ = "events"

    name: str
    value: int


@dataclass
class EventFetchParam:
    name: str | None = None
    page: int | None = None
    page_size: int | None = None


class EventDao(ClickHouseDao):
    model = EventModel
    BATCH_SIZE = 2

    def _build_where(self, param: EventFetchParam) -> tuple[list[str], dict]:
        if param.name is None:
            return [], {}
        return ["name = {name:String}"], {"name": param.name}

    def build_order_by(self, param: EventFetchParam) -> str | None:
        return "value DESC"


class ClickHouseDaoTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.write_client = Mock()
        self.write_client.batch_insert = AsyncMock()
        self.read_client = Mock()
        self.read_client.fetch_all = AsyncMock()
        self.read_client.fetch_one = AsyncMock()
        self.dao = EventDao(self.write_client, self.read_client)

    def test_build_query_includes_validated_fields_filters_order_and_paging(self):
        sql, parameters = self.dao._build_query(
            EventFetchParam(name="signup", page=2, page_size=25),
            fields=["name", "value"],
        )

        self.assertIn("SELECT `name`,`value`", sql)
        self.assertIn("FROM `events`", sql)
        self.assertIn("WHERE name = {name:String}", sql)
        self.assertIn("ORDER BY value DESC", sql)
        self.assertIn("LIMIT {limit:UInt64}", sql)
        self.assertEqual(parameters, {"name": "signup", "limit": 25, "offset": 25})

    def test_build_query_rejects_unsafe_identifier_fields_and_pagination(self):
        with self.assertRaisesRegex(ValueError, "Invalid fields"):
            self.dao._build_query(EventFetchParam(), fields=["name; DROP TABLE events"])
        with self.assertRaisesRegex(ValueError, "page must be >= 1"):
            self.dao._build_query(EventFetchParam(page=0, page_size=1))
        with self.assertRaisesRegex(ValueError, "page_size must be > 0"):
            self.dao._build_query(EventFetchParam(page=1, page_size=0))

        class UnsafeModel(CKModel):
            __tablename__ = "events; DROP TABLE events"

        unsafe_dao = EventDao(self.write_client, self.read_client)
        unsafe_dao.model = UnsafeModel
        with self.assertRaisesRegex(ValueError, "Invalid SQL identifier"):
            unsafe_dao._build_query(EventFetchParam())

    async def test_fetch_models_and_count_delegate_to_the_read_client(self):
        self.read_client.fetch_all.return_value = [{"name": "signup", "value": 3}]
        self.read_client.fetch_one.return_value = {"count": 1}

        models = await self.dao.fetch_models(EventFetchParam(name="signup"))
        count = await self.dao.count(EventFetchParam(name="signup"))

        self.assertEqual(models, [EventModel(name="signup", value=3)])
        self.assertEqual(count, 1)
        self.read_client.fetch_all.assert_awaited_once()
        self.read_client.fetch_one.assert_awaited_once()

    async def test_batch_insert_chunks_models_and_skips_empty_input(self):
        items = [EventModel(name=f"event-{index}", value=index) for index in range(3)]

        await self.dao.batch_insert(items)
        await self.dao.batch_insert([])

        self.assertEqual(self.write_client.batch_insert.await_count, 2)
        sql, rows = self.write_client.batch_insert.await_args_list[0].args
        self.assertIn("INSERT INTO `events`", sql)
        self.assertIn("(`name`,`value`)", sql)
        self.assertEqual(rows, [("event-0", 0), ("event-1", 1)])
