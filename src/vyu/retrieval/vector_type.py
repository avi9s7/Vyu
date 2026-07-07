from __future__ import annotations

from sqlalchemy.types import UserDefinedType


class PgVector(UserDefinedType):
    """PostgreSQL pgvector column type with a fixed dimension count."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")
        self.dimensions = dimensions

    def get_col_spec(self, **kwargs: object) -> str:
        del kwargs
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect):  # type: ignore[no-untyped-def]
        del dialect

        def process(value: object | None) -> str | None:
            if value is None:
                return None
            if isinstance(value, str):
                return value
            if isinstance(value, (list, tuple)):
                return "[" + ",".join(str(float(item)) for item in value) + "]"
            raise TypeError(f"unsupported pgvector bind value: {type(value)!r}")

        return process
