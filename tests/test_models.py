from dataclasses import dataclass
from unittest import TestCase

from daokit.clickhouse.model import CKModel


@dataclass
class Metric(CKModel):
    __tablename__ = "metrics"

    symbol: str
    price: float


class ClickHouseModelTests(TestCase):
    def test_model_serialization_and_deserialization_follow_declared_fields(self):
        metric = Metric(symbol="DAO", price=12.5)

        self.assertEqual(Metric.columns(), ["symbol", "price"])
        self.assertEqual(metric.to_tuple(), ("DAO", 12.5))
        self.assertEqual(
            Metric.from_dict({"symbol": "DAO", "price": 12.5, "ignored": True}),
            metric,
        )
