"""Uploads one sample invoice to the real bucket, to check your credentials and the bucket work.

    gcloud auth application-default login      # once
    GCS_BUCKET=cs5224-ansera-app-objects python scripts/check_storage.py [--keep]

The object is invoices/_check/<timestamp>.pdf. It's deleted again unless you pass --keep, so you
can look at it in the console or with `gcloud storage ls gs://<bucket>/invoices/_check/`.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, documents, storage
from scripts.preview_documents import sample

if not config.GCS_BUCKET:
    sys.exit('Set GCS_BUCKET first, e.g. GCS_BUCKET=cs5224-ansera-app-objects')

name = f'invoices/_check/{datetime.now(UTC):%Y%m%dT%H%M%S}.pdf'
uri = storage.upload_pdf(documents.render_pdf(sample(documents.ORDER, documents.INVOICE)), name)
print(f'Uploaded {uri}')

client = storage._get_client()
blob = client.bucket(config.GCS_BUCKET).get_blob(name)
print(f'Found it in the bucket: {blob.size} bytes, {blob.content_type}')
print(f'Signed link: {storage.signed_link(name) or "none (your own login can not sign, Cloud Run can)"}')

if '--keep' in sys.argv:
    print(f'Kept. Remove it with: gcloud storage rm {uri}')
else:
    blob.delete()
    print('Deleted it again.')
