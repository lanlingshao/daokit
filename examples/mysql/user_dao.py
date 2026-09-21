import asyncio
from dataclasses import dataclass

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from daokit.mysql.client import MysqlClient
from daokit.mysql.dao import MysqlDao, FetchParamT
from daokit.mysql.model import AutoIncrementModel

"""
Step 0. Create the table first.

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
"""


# ---------------------------------------------------------------------------
# Step 1. Define the Model
# ---------------------------------------------------------------------------

class UserModel(AutoIncrementModel):
    __tablename__ = "user"

    username: Mapped[str] = mapped_column(String(32))
    email: Mapped[str] = mapped_column(String(32))

    def __repr__(self):
        return f"<UserModel: {self.id}, {self.username}, {self.email})>"


# ---------------------------------------------------------------------------
# Step 2. Define the query parameters
#
# FetchParam describes which fields can be used to query UserModel.
# ---------------------------------------------------------------------------
@dataclass
class UserFetchParam:
    id: int = None
    username: str = None
    email: str = None


# ---------------------------------------------------------------------------
# Step 3. Define the DAO
#
# The DAO contains the User-specific query conditions and unique-key logic.
# Generic CRUD behavior is provided by MysqlDao.
# ---------------------------------------------------------------------------

class UserDao(MysqlDao[UserModel, UserFetchParam]):
    model = UserModel

    def _build_unique_param(self, item: UserModel) -> UserFetchParam:
        return UserFetchParam(
            id=item.id,
        )

    def _build_where_clauses(self, param: UserFetchParam):
        where_clauses = []
        if param.id is not None:
            where_clauses.append(UserModel.id == param.id)
        if param.username is not None:
            where_clauses.append(UserModel.username == param.username)
        if param.email is not None:
            where_clauses.append(UserModel.email == param.email)
        return where_clauses

    def _build_param(self, **kwargs) -> FetchParamT:
        return UserFetchParam(**kwargs)


# ---------------------------------------------------------------------------
# Step 4. Create the MySQL client and DAO
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Step 5. Define application-level operations
#
# The application owns the transaction/session boundary.
# DAO only performs database operations using the provided session.
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Step 6. Run the example
# ---------------------------------------------------------------------------

async def main():
    # -----------------------------------------------------------------------
    # Step 6.1. Create a session and start a transaction.
    #
    # All operations in this block share the same transaction.
    # -----------------------------------------------------------------------
    async with mysql_client.session_context(transaction=True) as session:
        print("\n=== 1. Create user ===")
        user = await create_user(session, "admin", "admin@example.com")

        # -------------------------------------------------------------------
        # Step 6.2. Query by primary key
        # -------------------------------------------------------------------

        print("\n=== 2. Query user by id ===")
        user = await get_user_by_id(session, user.id)
        print(user)

        # -------------------------------------------------------------------
        # Step 6.3. Update the user
        # -------------------------------------------------------------------

        print("\n=== 3. Update user ===")
        await update_user(user, "admin1", "admin1@example.com")

        # -------------------------------------------------------------------
        # Step 6.4. Query again inside the same transaction
        # -------------------------------------------------------------------

        print("\n=== 4. Query updated user ===")
        user = await get_user_by_id(session, user.id)
        print(user)

    # -----------------------------------------------------------------------
    # Step 6.5. The transaction has been committed automatically.
    #
    # For read-only operations, a transaction is not required by the
    # application API. A normal session can be used.
    # -----------------------------------------------------------------------
    async with mysql_client.session_context() as session:
        print("\n=== 5. Query user after transaction ===")
        user = await get_user_by_username(session, "admin1")
        print(user)


if __name__ == '__main__':
    asyncio.run(main())
