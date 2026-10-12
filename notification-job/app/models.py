"""Read-only SQLAlchemy models of configuration-service's tables.

configuration-service (Django) owns the schema and its migrations: never create or alter tables
from here. Map only the columns the job needs; Django's table name is <app_label>_<model name>.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BusinessConfiguration(Base):
    """configuration_app.BusinessConfiguration: a business (tenant)."""

    __tablename__ = 'configuration_app_businessconfiguration'

    id: Mapped[int] = mapped_column(primary_key=True)
    business_name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(255))

    def __repr__(self) -> str:
        return f'BusinessConfiguration(id={self.id}, business_name={self.business_name!r})'
