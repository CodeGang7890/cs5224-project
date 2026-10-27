"""Re-encrypt saved WhatsApp credentials before switching Cloud Run's key.

Run with `check` first, then `forward` immediately before the Cloud Run
revision switches to configuration-encryption-key. Run `verify` after the
switch. Use `reverse` if that deployment fails. No secret or decrypted value
is written to disk or stdout.

Requires: pip install "cloud-sql-python-connector[pg8000]" cryptography
Uses Application Default Credentials with access to three Secret Manager
secrets and the Cloud SQL instance.
"""

import argparse
import base64
import hashlib
import json
import urllib.request

import google.auth
from google.auth.transport.requests import Request as AuthRequest
from google.cloud.sql.connector import Connector, IPTypes
from cryptography.fernet import Fernet, InvalidToken


PROJECT = "cs5224-ansera"
INSTANCE = f"{PROJECT}:us-central1:main-postgres"
TABLE = "configuration_app_whatsappconfiguration"
FIELDS = ("access_token", "app_secret")


def secret_value(credentials, name):
    if not credentials.valid:
        credentials.refresh(AuthRequest())
    request = urllib.request.Request(
        f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets/{name}/versions/latest:access",
        headers={"Authorization": f"Bearer {credentials.token}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return base64.b64decode(json.load(response)["payload"]["data"]).decode()


def cipher(secret):
    # Match configuration-service/configuration_app/crypto.py exactly.
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "forward", "verify", "reverse"))
    args = parser.parse_args()

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    old = cipher(secret_value(credentials, "django-secret-key"))
    new = cipher(secret_value(credentials, "configuration-encryption-key"))
    password = secret_value(credentials, "cloud-sql-db-password")
    if args.mode in ("verify", "reverse"):
        source, target = new, old
    else:
        source, target = old, new

    with Connector(refresh_strategy="LAZY", credentials=credentials) as connector:
        connection = connector.connect(
            INSTANCE,
            "pg8000",
            user="app",
            password=password,
            db="configuration_service",
            ip_type=IPTypes.PUBLIC,
        )
        try:
            cursor = connection.cursor()
            lock = " FOR UPDATE" if args.mode in ("forward", "reverse") else ""
            cursor.execute(
                f"SELECT id, access_token, app_secret FROM {TABLE}{lock}"
            )
            rows = cursor.fetchall()
            updates = []
            field_count = 0
            for row_id, access_token, app_secret in rows:
                converted = []
                for value in (access_token, app_secret):
                    if not value:
                        converted.append(value)
                        continue
                    try:
                        plaintext = source.decrypt(value.encode())
                    except InvalidToken as exc:
                        raise RuntimeError(
                            "Migration stopped: a stored field cannot be decrypted with "
                            "the expected source key. No rows were changed."
                        ) from exc
                    field_count += 1
                    converted.append(target.encrypt(plaintext).decode())
                updates.append((converted[0], converted[1], row_id))

            if args.mode in ("check", "verify"):
                connection.rollback()
                print(f"{args.mode.capitalize()} passed: {len(rows)} rows, {field_count} encrypted fields.")
                return

            for access_token, app_secret, row_id in updates:
                cursor.execute(
                    f"UPDATE {TABLE} SET access_token = %s, app_secret = %s WHERE id = %s",
                    (access_token, app_secret, row_id),
                )
            connection.commit()
            print(
                f"{args.mode.capitalize()} migration committed: "
                f"{len(rows)} rows, {field_count} encrypted fields."
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


if __name__ == "__main__":
    main()
