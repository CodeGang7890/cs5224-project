"""The notification job: (1) read from the database, (2) business logic, (3) call an external API.

Only (1) is built so far: it reads the businesses and logs them.
"""

import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import BusinessConfiguration

logger = logging.getLogger(__name__)


def run(session_factory: Callable[[], Session] = get_session) -> list[BusinessConfiguration]:
    with session_factory() as session:
        businesses = session.scalars(select(BusinessConfiguration).order_by(BusinessConfiguration.id)).all()
    logger.info('Found %d businesses', len(businesses))
    for business in businesses:
        logger.info('Business %s: %s (%s)', business.id, business.business_name, business.location)
    # TODO: (2) decide what to notify, (3) call the external API.
    return list(businesses)
