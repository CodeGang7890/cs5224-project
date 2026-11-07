"""Photos and documents a customer sends: only their metadata, kept in memory (the user asked).

No file is uploaded or stored: the page sends the file's name, type and size, and the chat shows a
placeholder. The message itself is in the database as usual (its text is the caption, empty if
none: a text message can't be empty, so an empty one is always an attachment). After a restart
the metadata is gone, and the page shows a plain "Attachment" placeholder.
"""

import hashlib
import secrets

IMAGE, DOCUMENT = 'image', 'document'  # Meta's message types
KINDS = (IMAGE, DOCUMENT)

_by_wamid: dict[str, dict] = {}  # wamid → {kind, filename, mime_type, size, id, sha256}


def add(wamid: str, kind: str, filename: str, mime_type: str, size: int) -> dict:
    """Remembers an attachment, with a media id and sha256 like Meta's (made up: there's no file)."""
    item = {
        'kind': kind,
        'filename': filename,
        'mime_type': mime_type,
        'size': size,
        'id': str(secrets.randbelow(9 * 10**15) + 10**15),  # Meta's media ids: 16 digits
        'sha256': hashlib.sha256(f'{wamid}:{filename}:{size}'.encode()).hexdigest(),
    }
    _by_wamid[wamid] = item
    return item


def get(wamid: str) -> dict | None:
    return _by_wamid.get(wamid)


def clear() -> None:
    _by_wamid.clear()
