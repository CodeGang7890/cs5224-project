"""Development server for payment-ingester."""

import os
import subprocess
import sys


def main():
    """Run the development server with auto-reload."""
    port = os.getenv('PORT', str(8001))
    
    # Set default PUBSUB_EMULATOR_HOST for local development
    if 'PUBSUB_EMULATOR_HOST' not in os.environ:
        os.environ['PUBSUB_EMULATOR_HOST'] = 'localhost:8085'
    
    # Use uvicorn for development with auto-reload
    cmd = [
        sys.executable, '-m', 'uvicorn',
        'app.routes:app',
        '--host', '0.0.0.0',
        '--port', port,
        '--reload',
    ]
    
    print(f'Starting payment-ingester on http://0.0.0.0:{port}')
    print('Press Ctrl+C to stop')
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print('\nShutting down...')


if __name__ == '__main__':
    main()
