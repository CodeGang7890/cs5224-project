# Gunicorn configuration for payment-ingester

import os

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '8001')}"
workers = int(os.getenv('WEB_CONCURRENCY', '2'))

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Worker processes
worker_class = 'uvicorn.workers.UvicornWorker'

# Timeout
timeout = 30

# Process naming
proc_name = 'payment-ingester'
