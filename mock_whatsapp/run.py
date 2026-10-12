"""Starts mock_whatsapp: `python run.py` → http://localhost:9000 (listening on 0.0.0.0, so the
containers can reach its fake Graph API on this machine)."""

import os

import uvicorn

from app import config

if __name__ == '__main__':
    uvicorn.run('app:create_app', factory=True, host=config.HOST, port=config.PORT, reload=os.getenv('RELOAD', '1') == '1')
