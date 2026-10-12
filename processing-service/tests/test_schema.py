"""The SQLAlchemy models (app/models.py) against configuration-service's real schema.

configuration-service (Django) owns the PostgreSQL schema and every migration; this service only
maps the tables it uses. This test catches the two drifting apart: it needs a database migrated by
Django (CI: the schema job), given as SCHEMA_DATABASE_URL, and is skipped otherwise.
- every mapped table and column exists, with the same nullability, type and length;
- the tables this service inserts rows into have no required (NOT NULL, no default) column it
  doesn't map: Django adding one would make those inserts fail.
"""

import os
import unittest

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Integer, Numeric, String, Text, create_engine, inspect
from sqlalchemy.types import TypeDecorator

from app.models import Base, OrderItem, ScheduleItem, WeeklyAvailability

SCHEMA_DATABASE_URL = os.getenv('SCHEMA_DATABASE_URL', '')
INSERTED_INTO = [WeeklyAvailability]  # a week painted for a booking (app/schedule.py)
UPDATED = [OrderItem, ScheduleItem]


def kind(column_type) -> tuple:
    """A comparable (kind, length / precision) for a mapped or reflected column type."""
    if isinstance(column_type, TypeDecorator):  # e.g. AwareDateTime: compare what it's stored as
        column_type = column_type.impl
    for cls, name in ((Boolean, 'bool'), (DateTime, 'datetime'), (Date, 'date'), (JSON, 'json')):
        if isinstance(column_type, cls):
            return (name,)
    if type(column_type).__name__ in ('JSONB', 'JSON'):
        return ('json',)
    if isinstance(column_type, Numeric) and not isinstance(column_type, Integer):
        return ('numeric', column_type.precision, column_type.scale)
    if isinstance(column_type, (BigInteger, Integer)):
        return ('integer',)
    if isinstance(column_type, Text) or (isinstance(column_type, String) and column_type.length is None):
        return ('text',)
    if isinstance(column_type, String):
        return ('string', column_type.length)
    return (type(column_type).__name__,)


@unittest.skipUnless(SCHEMA_DATABASE_URL, 'needs a database migrated by configuration-service (SCHEMA_DATABASE_URL)')
class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(SCHEMA_DATABASE_URL)
        cls.inspector = inspect(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def columns(self, table: str) -> dict:
        return {column['name']: column for column in self.inspector.get_columns(table)}

    def test_every_mapped_column_matches_django(self):
        for table in Base.metadata.sorted_tables:
            real = self.columns(table.name)
            self.assertTrue(real, f'{table.name} does not exist')
            for column in table.columns:
                with self.subTest(table=table.name, column=column.name):
                    self.assertIn(column.name, real)
                    self.assertEqual(column.nullable, real[column.name]['nullable'], 'nullability')
                    mapped, django = kind(column.type), kind(real[column.name]['type'])
                    # A many-to-many table's id may be integer or bigint: both are 'integer'.
                    self.assertEqual(mapped, django, 'type')

    def test_no_unmapped_required_column_in_the_tables_written_to(self):
        for model in INSERTED_INTO:
            table = model.__table__
            for name, column in self.columns(table.name).items():
                with self.subTest(table=table.name, column=name):
                    required = not column['nullable'] and column.get('default') is None and not column.get('identity')
                    if required and name != 'id':
                        self.assertIn(name, table.columns, f'{table.name}.{name} is required but not mapped')
