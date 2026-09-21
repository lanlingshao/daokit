from datetime import datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from daokit.util.time import now_utc


class Base(DeclarativeBase):
    pass


class BaseModel(Base):
    __abstract__ = True  # 不创建表
    __tablename__ = ""

    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc()
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc(),
        onupdate=now_utc()
    )

    @property
    def table_name(self):
        return self.__tablename__

    # 序列化
    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        exclude = exclude or set()
        return {
            c.name: getattr(self, c.name)
            for c in self.__table__.columns
            if c.name not in exclude
        }


class AutoIncrementModel(BaseModel):
    __abstract__ = True

    # 默认主键设置，子类中可以定义自己的主键
    id: Mapped[int] = mapped_column(primary_key=True)

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return self.id == other.id

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"

    def identity(self):
        return self.id
