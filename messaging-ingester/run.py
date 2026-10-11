"""Development server entry point: `python run.py` (serves on http://127.0.0.1:8002)."""

import os

import uvicorn

from app.config import PORT

if __name__ == '__main__':
    uvicorn.run(
        'app:create_app',
        factory=True,
        host=os.getenv('HOST', '127.0.0.1'),
        port=int(os.getenv('PORT', PORT)),
        reload=os.getenv('RELOAD', '1') == '1',
    )
