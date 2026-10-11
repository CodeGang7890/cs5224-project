import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import job
from app.models import Base, BusinessConfiguration


class JobTests(unittest.TestCase):
    def test_reads_and_logs_the_businesses(self):
        # In-memory SQLite stands in for PostgreSQL; the tables are created here only for the test.
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        sessions = sessionmaker(engine)
        with sessions.begin() as session:
            session.add(BusinessConfiguration(business_name='Bakery', description='', location='Singapore'))
        with self.assertLogs('app.job', level='INFO') as logs:
            businesses = job.run(sessions)
        self.assertEqual([b.business_name for b in businesses], ['Bakery'])
        self.assertIn('Business 1: Bakery (Singapore)', logs.output[1])


if __name__ == '__main__':
    unittest.main()
