"""Database model declarations for the demo service."""

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative model base."""


class Order(Base):
    """Persisted order record."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_email: Mapped[str] = mapped_column(String(320))
    total: Mapped[str] = mapped_column(String(32))
