import multiprocessing

# On Render Free tier (512MB RAM limit), we MUST run exactly 1 worker.
# Our async ThreadPoolExecutor handles concurrent requests efficiently on a single worker process.
workers = 1 

# Use Uvicorn for ASGI compatibility
worker_class = "uvicorn.workers.UvicornWorker"

# Prevent Gunicorn from killing workers waiting on long LLM responses
timeout = 120 

# TCP keepalive for load balancers (helps Render not drop idle connections)
keepalive = 5 

# Restart workers periodically to prevent memory leaks from LLM clients
max_requests = 1000 
max_requests_jitter = 50
