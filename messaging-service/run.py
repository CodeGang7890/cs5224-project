"""Development server entry point: `python run.py` (serves on http://127.0.0.1:8001)."""

import os

from app import create_app
from app.config import PORT

app = create_app()

if __name__ == '__main__':
    app.run(
        host=os.getenv('HOST', '127.0.0.1'),
        port=int(os.getenv('PORT', PORT)),
        debug=os.getenv('FLASK_DEBUG', '1') == '1',
    )
