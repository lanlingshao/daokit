from dataclasses import dataclass, fields


@dataclass
class CKModel:
    __tablename__ = ""

    @classmethod
    def columns(cls):
        return [f.name for f in fields(cls)]

    def to_tuple(self):
        return tuple(getattr(self, f.name) for f in fields(self))

    @classmethod
    def from_dict(cls, row):
        ...
