import os

bind = "0.0.0.0:" + str(os.getenv("PORT", 5000))
workers = 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
max_requests = 1000
max_requests_jitter = 100
preload_app = True