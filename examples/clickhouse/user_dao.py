import asyncio
from dataclasses import dataclass

from daokit.clickhouse.client import ClickHouseWriteClient, ClickHouseQueryClient
from daokit.clickhouse.dao import ClickHouseDao
from daokit.clickhouse.model import CKModel

"""
CREATE TABLE IF NOT EXISTS `user`
(
    username String,
    email    String
)
ENGINE = MergeTree
ORDER BY username;
"""


conf = {
    "host": "127.0.0.1",
    "tcp_port": "9000",
    "http_port": "8123",
    "username": "default",
    "password": "",
    "database": "test",
    "connect_timeout": 15,
    "maxsize": 5,
    "minsize": 1,
}


@dataclass
class UserModel(CKModel):
    __tablename__ = "user"

    username: str
    email: str


@dataclass
class UserFetchParam:
    username: str = None
    email: str = None


class UserDao(ClickHouseDao):
    model = UserModel
    use_final = False

    def _build_where(self, param: UserFetchParam) -> tuple[list[str], dict]:
        where = []
        parameters = {}

        if param.username is not None:
            where.append("username = {username:String}")
            parameters["username"] = param.username
        if param.email is not None:
            where.append("email = {email:String}")
            parameters["email"] = param.email
        return where, parameters


write_client = ClickHouseWriteClient(conf)
read_client = ClickHouseQueryClient(conf)
user_dao = UserDao(write_client=write_client, read_client=read_client)


async def batch_create_users(users: list[UserModel]):
    await user_dao.batch_insert(users)


async def fetch_user_dicts(param: UserFetchParam) -> list[dict]:
    users = await user_dao.fetch_dicts(param)
    return users


async def fetch_user_models(param: UserFetchParam) -> list[UserModel]:
    users = await user_dao.fetch_models(param)
    return users


async def main():
    try:
        await batch_create_users([
            UserModel(username="a", email="a@example.com"),
            UserModel(username="b", email="b@example.com"),
        ])

        users = await fetch_user_dicts(UserFetchParam(username="a"))
        print(users)
        users = await fetch_user_models(UserFetchParam(username="b"))
        print(users)
    finally:
        await write_client.close()
        await read_client.close()


if __name__ == "__main__":
    asyncio.run(main())
