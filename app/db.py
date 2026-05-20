from dotenv import load_dotenv
load_dotenv()

import os
import logging
import threading
import time
import pandas as pd
from databricks import sql
from queue import Queue, Empty

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


DATABRICKS_HOST = os.getenv("DATABRICKS_HOST")
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")

if DATABRICKS_HOST and DATABRICKS_HOST.startswith("https://"):
    DATABRICKS_HOST = DATABRICKS_HOST.replace("https://", "")

if not all([DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN]):
    raise ValueError("Missing Databricks environment variables.")

logger.info("Databricks configuration loaded.")


class DatabricksConnectionPool:

    def __init__(self, size=2):

        self.size = size
        self.pool = Queue(maxsize=size)

        for _ in range(size):
            self.pool.put(self._create_connection())

    def _create_connection(self):

        logger.info("Creating Databricks connection...")

        return sql.connect(
            server_hostname=DATABRICKS_HOST,
            http_path=DATABRICKS_HTTP_PATH,
            access_token=DATABRICKS_TOKEN,
        )

    def get_connection(self):

        try:
            conn = self.pool.get(timeout=5)

            # lightweight health check
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()

                return conn

            except Exception as e:

                logger.warning(f"Dead Databricks connection detected: {e}")

                try:
                    conn.close()
                except Exception:
                    pass

                return self._create_connection()

        except Empty:

            logger.warning(
                "No Databricks connection available in pool."
            )

            # fail fast instead of freezing worker
            raise Exception("Databricks pool exhausted")

    def release_connection(self, conn):

        if conn:
            try:
                self.pool.put_nowait(conn)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass


# Small pool because you only have 1 worker
db_pool = DatabricksConnectionPool(size=2)

def fetch_df(query: str, params: tuple = ()) -> pd.DataFrame:

    max_attempts = 3

    for attempt in range(1, max_attempts + 1):

        conn = None

        start_time = time.time()

        try:

            conn = db_pool.get_connection()

            with conn.cursor() as cursor:

                logger.info(
                    f"Executing Databricks query "
                    f"(attempt {attempt})"
                )

                cursor.execute(query, params)

                rows = cursor.fetchall()

                columns = [
                    col[0]
                    .lower()
                    .strip()
                    .replace(" ", "_")
                    .replace("(", "")
                    .replace(")", "")
                    for col in cursor.description
                ]

                elapsed = round(time.time() - start_time, 2)

                logger.info(
                    f"Databricks query completed "
                    f"in {elapsed}s"
                )

                return pd.DataFrame(rows, columns=columns)

        except Exception as e:

            elapsed = round(time.time() - start_time, 2)

            logger.error(
                f"Databricks query failed "
                f"(attempt {attempt}) "
                f"after {elapsed}s: {e}",
                exc_info=True,
            )

            # kill broken connection
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

            if attempt < max_attempts:

                wait = attempt * 2

                logger.info(
                    f"Retrying Databricks query in {wait}s..."
                )

                time.sleep(wait)

            else:
                logger.error("All Databricks retries failed.")
                raise

        finally:

            if conn:
                db_pool.release_connection(conn)


def warmup_databricks():

    logger.info("Starting Databricks warmup...")

    try:

        start = time.time()

        fetch_df("SELECT 1")

        elapsed = round(time.time() - start, 2)

        logger.info(
            f"Databricks warmup completed in {elapsed}s"
        )

    except Exception as e:

        logger.error(
            f"Databricks warmup failed: {e}"
        )

# run warmup in background
threading.Thread(
    target=warmup_databricks,
    daemon=True
).start()


def fetch_rep_id_by_email(email: str):

    if not email:
        return None

    query = """
    SELECT `Rep ID`
    FROM ic_implementation.ic_intelligence.user_access
    WHERE LOWER(TRIM(Email)) = ?
    """

    try:

        df = fetch_df(
            query,
            (str(email).lower().strip(),)
        )

        if df.empty:
            return None

        rep_id = df.iloc[0].get("rep_id")

        return str(rep_id).strip() if rep_id else None

    except Exception as e:

        logger.error(
            f"Rep lookup failed for {email}: {e}"
        )

        return None