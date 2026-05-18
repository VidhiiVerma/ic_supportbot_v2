from dotenv import load_dotenv
load_dotenv()

import os
import logging
import queue
import pandas as pd
from databricks import sql
import threading
import concurrent.futures

# LOGGER SETUP
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ENV CONFIG
DATABRICKS_HOST = os.getenv("DATABRICKS_HOST")
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")

# Normalize host
if DATABRICKS_HOST and DATABRICKS_HOST.startswith("https://"):
    DATABRICKS_HOST = DATABRICKS_HOST.replace("https://", "")

# Validate
if not DATABRICKS_HOST or not DATABRICKS_HTTP_PATH or not DATABRICKS_TOKEN:
    raise ValueError("Missing critical Databricks environment configuration variables.")

logger.info("Databricks config loaded successfully.")


#  HIGH-PERFORMANCE THREAD-SAFE CONNECTION POOL
class DatabricksConnectionPool:
    def __init__(self, size=10):
        self._pool = queue.Queue()
        self.size = size
        self._created = 0
        self._lock = threading.Lock()
            
    def _create_connection(self):
        logger.info("Opening a new Databricks connection...")
        return sql.connect(
            server_hostname=DATABRICKS_HOST,
            http_path=DATABRICKS_HTTP_PATH,
            access_token=DATABRICKS_TOKEN,
        )

    def get_connection(self):
        # 1. Try to fetch an existing warm connection from the pool immediately
        try:
            conn = self._pool.get_nowait()
            # Test connection validity with a simple lightweight ping/check
            try:
                with conn.cursor() as cursor:
                    pass
                return conn
            except Exception as e:
                logger.warning(f"Stale connection detected in pool. Reconnecting... Error: {e}")
                try:
                    conn.close()
                except Exception:
                    pass
                return self._create_connection()
        except queue.Empty:
            # 2. Pool is empty. Create a new connection if we haven't reached the limit
            with self._lock:
                if self._created < self.size:
                    self._created += 1
                    return self._create_connection()
            
            # 3. If pool is full and completely busy, block and wait for a connection to be released
            logger.info("Databricks connection pool limit reached. Waiting for connection release...")
            return self._pool.get(block=True)

    def release_connection(self, conn):
        if conn is not None:
            self._pool.put(conn)

# Instantiate global connection pool
db_pool = DatabricksConnectionPool(size=10)


# Backward compatible helper
def get_connection():
    return db_pool.get_connection()


#  QUERY EXECUTION 
def fetch_df(query: str, params: tuple = ()) -> pd.DataFrame:
    max_retries = 3
    for attempt in range(max_retries):
        conn = db_pool.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                columns = _get_columns(cursor.description)
                rows = cursor.fetchall()
                df = pd.DataFrame(rows, columns=columns)
                return df
        except Exception as e:
            # Discard dead/broken connections on exception
            try:
                conn.close()
            except Exception:
                pass
            
            # Decrement connection counter so pool can recreate it
            with db_pool._lock:
                if db_pool._created > 0:
                    db_pool._created -= 1
            
            if attempt < max_retries - 1:
                logger.warning(f"Query failed (attempt {attempt+1}/{max_retries}). Retrying... Error: {e}")
                import time
                time.sleep(2)
            else:
                logger.error("Query failed permanently after retries.", exc_info=True)
                raise
        finally:
            # Release connection back to pool if not broken
            db_pool.release_connection(conn)


#  WAKE UP WAREHOUSE (Non-blocking)
def _wakeup():
    """Triggers warehouse start during server boot."""
    try:
        logger.info("Triggering Databricks warm-up...")
        fetch_df("SELECT 1")
        logger.info("Databricks warehouse is warm.")
    except Exception:
        # Expected if warehouse is still starting
        pass

threading.Thread(target=_wakeup, daemon=True).start()


def _get_columns(cursor_description):
    return [
        col[0].lower().strip().replace(" ", "_").replace("(", "").replace(")", "")
        for col in cursor_description
    ]


#  CONCURRENT RETRIEVAL HELPERS
def fetch_payout_data(rep_id: int):
    query = """
    SELECT *
    FROM ic_implementation.ic_intelligence.payout_summary
    WHERE `Rep ID` = ?
    """
    df = fetch_df(query, (rep_id,))
    return df.iloc[0].to_dict() if not df.empty else None


def fetch_sales_data(rep_id: int):
    query = """
    SELECT *
    FROM ic_implementation.ic_intelligence.sales_crediting
    WHERE assignment_emp = ?
    """
    df = fetch_df(query, (rep_id,))
    return df.to_dict(orient="records")


def fetch_eligibility_data(rep_name: str):
    if not rep_name:
        return {}
    query = """
    SELECT *
    FROM ic_implementation.ic_intelligence.eligibility_2
    WHERE LOWER(TRIM(rep_name)) = ?
    """
    df = fetch_df(query, (str(rep_name).lower().strip(),))
    return df.iloc[0].to_dict() if not df.empty else {}


# MAIN CONCURRENT DATA RETRIEVAL
def get_rep_data(rep_id: str):
    """
    Fetches payout and sales concurrently, followed by eligibility to minimize latency.
    """
    try:
        rep_id_int = int(rep_id)

        # Run Payout and Sales queries concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            payout_future = executor.submit(fetch_payout_data, rep_id_int)
            sales_future = executor.submit(fetch_sales_data, rep_id_int)

            payout = payout_future.result()
            sales = sales_future.result()

        if not payout:
            return None

        # Fetch eligibility based on the payout rep_name
        rep_name = payout.get("rep_name", "")
        eligibility = fetch_eligibility_data(rep_name)

        return {
            "payout": payout,
            "eligibility": eligibility,
            "sales": sales
        }

    except Exception:
        logger.error("Error fetching rep data", exc_info=True)
        return None