import asyncio
from dataclasses import dataclass

from daokit.clickhouse.client import ClickHouseWriteClient, ClickHouseQueryClient
from daokit.clickhouse.dao import ClickHouseDao
from daokit.clickhouse.model import CKModel

"""
Step 0. Create the table first.

CREATE TABLE IF NOT EXISTS `user`
(
    username String,
    email    String
)
ENGINE = MergeTree
ORDER BY username;
"""

# ---------------------------------------------------------------------------
# Step 1. Define the Model
# ---------------------------------------------------------------------------

@dataclass
class UserModel(CKModel):
    __tablename__ = "user"

    username: str
    email: str


# ---------------------------------------------------------------------------
# Step 2. Define the query parameters
# ---------------------------------------------------------------------------

@dataclass
class UserFetchParam:
    username: str = None
    email: str = None


# ---------------------------------------------------------------------------
# Step 3. Define the DAO
#
# Generic insert/query behavior is provided by ClickHouseDao.
# UserDao only needs to define how UserFetchParam is translated into
# ClickHouse WHERE conditions.
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Step 4. Create the ClickHouse clients and DAO
#
# Write and query clients are separated.
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Step 6. Run the example
# ---------------------------------------------------------------------------

async def main():
    try:
        # ---------------------------------------------------------------
        # Step 6.1. Batch insert
        # ---------------------------------------------------------------

        print("\n=== 1. Batch insert users ===")

        await batch_create_users([
            UserModel(username="a", email="a@example.com"),
            UserModel(username="b", email="b@example.com"),
        ])

        # ---------------------------------------------------------------
        # Step 6.2. Query as dictionaries
        #
        # fetch_dicts() is useful when the application only needs raw
        # database results.
        # ---------------------------------------------------------------

        print("\n=== 2. Fetch as dictionaries ===")

        users = await fetch_user_dicts(UserFetchParam(username="a"))
        print(users)

        # ---------------------------------------------------------------
        # Step 6.3. Query as Models
        #
        # fetch_models() converts database rows into UserModel instances.
        # ---------------------------------------------------------------

        print("\n=== 3. Fetch as models ===")
        users = await fetch_user_models(UserFetchParam(username="b"))
        print(users)
    finally:
        # ---------------------------------------------------------------
        # Step 6.4. Close clients
        # ---------------------------------------------------------------

        print("\n=== 4. Close clients ===")
        await write_client.close()
        await read_client.close()


if __name__ == "__main__":
    asyncio.run(main())
