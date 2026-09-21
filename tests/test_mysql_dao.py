from dataclasses import dataclass
from datetime import datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

from sqlalchemy import String
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from daokit.exception import DaoException
from daokit.mysql.dao import MysqlDao
from daokit.mysql.model import AutoIncrementModel


class ArticleModel(AutoIncrementModel):
    __tablename__ = "test_articles"

    title: Mapped[str] = mapped_column(String(64))


@dataclass
class ArticleFetchParam:
    id: int | None = None
    title: str | None = None
    page: int | None = None
    page_size: int | None = None


class ArticleDao(MysqlDao[ArticleModel, ArticleFetchParam]):
    model = ArticleModel
    BATCH_SIZE = 2

    def _build_unique_param(self, item: ArticleModel) -> ArticleFetchParam:
        return ArticleFetchParam(id=item.id)

    def _build_param(self, **kwargs) -> ArticleFetchParam:
        return ArticleFetchParam(**kwargs)

    def _build_where_clauses(self, param: ArticleFetchParam):
        clauses = []
        if param.id is not None:
            clauses.append(ArticleModel.id == param.id)
        if param.title is not None:
            clauses.append(ArticleModel.title == param.title)
        return clauses

    def _upsert_update_columns(self) -> list[str]:
        return ["title"]


class MysqlDaoTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.dao = ArticleDao(Mock())

    async def test_create_adds_and_flushes_the_model(self):
        session = Mock()
        session.flush = AsyncMock()
        item = ArticleModel(title="first")

        await self.dao.create(session, item)

        session.add.assert_called_once_with(item)
        session.flush.assert_awaited_once()

    async def test_fetch_applies_filter_pagination_and_selected_fields(self):
        records = [ArticleModel(id=1, title="first")]
        scalars = Mock()
        scalars.all.return_value = records
        session = Mock()
        session.scalars = AsyncMock(return_value=scalars)

        result = await self.dao.fetch(
            session,
            ArticleFetchParam(title="first", page=2, page_size=10),
            fields=(ArticleModel.id, ArticleModel.title),
        )

        self.assertEqual(result, records)
        statement = session.scalars.await_args.args[0]
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("WHERE test_articles.title = 'first'", compiled)
        self.assertIn("LIMIT 10 OFFSET 10", compiled)

    async def test_count_returns_zero_when_database_returns_none(self):
        session = Mock()
        session.scalar = AsyncMock(return_value=None)

        result = await self.dao.count(session, ArticleFetchParam())

        self.assertEqual(result, 0)

    async def test_quick_batch_upsert_chunks_rows_and_skips_empty_input(self):
        session = Mock()
        session.execute = AsyncMock()
        items = [ArticleModel(id=index, title=f"article-{index}") for index in range(1, 4)]

        await self.dao.quick_batch_upsert(session, items)
        await self.dao.quick_batch_upsert(session, [])

        self.assertEqual(session.execute.await_count, 2)
        statement = session.execute.await_args_list[0].args[0]
        compiled = str(statement.compile(dialect=mysql.dialect()))
        self.assertIn("ON DUPLICATE KEY UPDATE", compiled)

    async def test_delete_requires_a_filter(self):
        session = Mock()
        session.execute = AsyncMock()

        await self.dao.delete(session, ArticleFetchParam())
        self.assertFalse(session.execute.called)

        await self.dao.delete(session, ArticleFetchParam(id=7))
        statement = session.execute.await_args.args[0]
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("DELETE FROM test_articles", compiled)
        self.assertIn("WHERE test_articles.id = 7", compiled)

    async def test_soft_delete_rejects_models_without_deleted_column(self):
        with self.assertRaisesRegex(DaoException, "not support soft delete"):
            await self.dao.soft_delete(Mock(), ArticleFetchParam(id=1))

    async def test_update_copies_values_and_refreshes_updated_timestamp(self):
        old = ArticleModel(id=1, title="old")
        new = ArticleModel(id=1, title="new")

        await self.dao.update(old, new)

        self.assertEqual(old.title, "new")
        self.assertIsInstance(old.updated, datetime)
