import asyncio
from dataclasses import dataclass

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from daokit.mysql.client import MysqlClient
from daokit.mysql.dao import MysqlDao, FetchParamT
from daokit.mysql.model import AutoIncrementModel

'''
CREATE TABLE `user` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(32) NOT NULL,
  `email` varchar(32) NOT NULL,
  `created` datetime DEFAULT NULL,
  `updated` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_email_IDX` (`email`) USING BTREE,
  UNIQUE KEY `user_username_IDX` (`username`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='user';
'''


class UserModel(AutoIncrementModel):
    __tablename__ = "user"

    username: Mapped[str] = mapped_column(String(32))
    email: Mapped[str] = mapped_column(String(32))

    def __repr__(self):
        return f"<UserModel: {self.id}, {self.username}, {self.email})>"


@dataclass
class UserFetchParam:
    id: int = None
    username: str = None
    email: str = None


class UserDao(MysqlDao[UserModel, UserFetchParam]):
    model = UserModel

    def _build_unique_param(self, item: UserModel) -> UserFetchParam:
        return UserFetchParam(
            id=item.id,
        )

    def _build_where_clauses(self, param: UserFetchParam):
        where_clauses = []
        if param.id:
            where_clauses.append(UserModel.id == param.id)
        if param.username:
            where_clauses.append(UserModel.username == param.username)
        if param.email:
            where_clauses.append(UserModel.email == param.email)
        return where_clauses

    def _build_param(self, **kwargs) -> FetchParamT:
        return UserFetchParam(**kwargs)


conf = {
    "username": "root",
    "password": "123456",
    "host": "localhost",
    "port": 3306,
    "database": "test",
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30,
}
mysql_client = MysqlClient(conf)
user_dao = UserDao(mysql_client)


async def create_user(session: AsyncSession, username: str, email: str) -> UserModel:
    user = UserModel(
        username=username,
        email=email,
    )
    await user_dao.create(session, user)
    return user

async def get_user_by_id(session: AsyncSession, user_id: int) -> UserModel:
    user = await user_dao.fetch_one(session, UserFetchParam(id=user_id))
    return user

async def get_user_by_username(session: AsyncSession, username: str) -> UserModel:
    user = await user_dao.fetch_one(session, UserFetchParam(username=username))
    return user

async def update_user(old_user_model: UserModel, username: str, email: str):
    new_user_model = UserModel(
        username=username,
        email=email,
    )
    await user_dao.update(old_user_model, new_user_model)

async def main():
    async with mysql_client.session_context(transaction=True) as session:
        user = await create_user(session, "admin", "admin@example.com")
        user = await get_user_by_id(session, user.id)
        print(user)
        await update_user(user, "admin1", "admin1@example.com")
        user = await get_user_by_id(session, user.id)
        print(user)

    # if you only want to query, you don't need to begin transaction
    # you can use session_context() to get a session without transaction
    async with mysql_client.session_context() as session:
        user = await get_user_by_username(session, "admin1")
        print(user)


if __name__ == '__main__':
    asyncio.run(main())
