import multiprocessing

# Workers = (2 x $num_cores) + 1. For a standard Render instance (2 cores), 4 is optimal.
workers = 4 

# Use Uvicorn for ASGI compatibility
worker_class = "uvicorn.workers.UvicornWorker"

# Prevent Gunicorn from killing workers waiting on long LLM responses
timeout = 120 

# TCP keepalive for load balancers (helps Render not drop idle connections)
keepalive = 5 

# Restart workers periodically to prevent memory leaks from LLM clients
max_requests = 1000 
max_requests_jitter = 50
