"""Invoice and receipt PDFs in Google Cloud Storage (the bucket from `GCS_BUCKET`).

With no `GCS_BUCKET` (local development, the tests) nothing is uploaded and the functions return
None, so the payment flow runs without Google Cloud.
"""

import logging
from datetime import timedelta

from . import config

logger = logging.getLogger(__name__)

# V4 signed URLs last 7 days at most.
LINK_VALIDITY = timedelta(days=7)

_client = None


CLOUD_PLATFORM_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'

def _get_client():
    global _client
    if _client is None:
        import google.auth
        from google.cloud import storage

        credentials, _ = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
        _client = storage.Client(project=config.GCP_PROJECT_ID, credentials=credentials)
    return _client


def upload_pdf(pdf: bytes, object_name: str, client=None) -> str | None:
    """Uploads the PDF and returns its `gs://` URI, or None when no bucket is configured."""
    if not config.GCS_BUCKET:
        logger.info('GCS_BUCKET is not set: not uploading %s', object_name)
        return None
    blob = (client or _get_client()).bucket(config.GCS_BUCKET).blob(object_name)
    blob.upload_from_string(pdf, content_type='application/pdf')
    logger.info('Uploaded gs://%s/%s', config.GCS_BUCKET, object_name)
    return f'gs://{config.GCS_BUCKET}/{object_name}'


def signed_link(object_name: str, client=None) -> str | None:
    """A link the customer can open for LINK_VALIDITY, or None when there's no bucket.

    Signs through the IAM API, which needs credentials with a service account (Cloud Run's) that
    may sign for itself (roles/iam.serviceAccountTokenCreator).
    """
    if not config.GCS_BUCKET:
        return None
    client = client or _get_client()
    try:
        from google.auth.transport.requests import Request

        credentials = client._credentials
        email = getattr(credentials, 'service_account_email', None)
        if not email:  # e.g. your own `gcloud auth application-default login`
            logger.warning('No link for %s: these credentials belong to a user, not a service account', object_name)
            return None
        credentials.refresh(Request())
        return client.bucket(config.GCS_BUCKET).blob(object_name).generate_signed_url(
            version='v4',
            expiration=LINK_VALIDITY,
            method='GET',
            service_account_email=email,
            access_token=credentials.token,
        )
    except Exception:
        logger.warning('Could not sign a link for %s (no service account credentials?)', object_name, exc_info=True)
        return None
