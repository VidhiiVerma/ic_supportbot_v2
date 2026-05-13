from dotenv import load_dotenv
load_dotenv()

import os
import logging
import pandas as pd
from databricks import sql
import threading

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
if not DATABRICKS_HOST:
    raise ValueError("Missing DATABRICKS_HOST")

if not DATABRICKS_HTTP_PATH:
    raise ValueError("Missing DATABRICKS_HTTP_PATH")

if not DATABRICKS_TOKEN:
    raise ValueError("Missing DATABRICKS_TOKEN")

logger.info("Databricks config loaded")


#  CONNECTION 
def get_connection():
    return sql.connect(
        server_hostname=DATABRICKS_HOST,
        http_path=DATABRICKS_HTTP_PATH,
        access_token=DATABRICKS_TOKEN,
    )


#  QUERY EXECUTION 
def fetch_df(query: str, params: tuple = ()) -> pd.DataFrame:
    import time
    max_retries = 3

    for attempt in range(max_retries):
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)

                    columns = [
                        col[0]
                        .lower()
                        .strip()
                        .replace(" ", "_")
                        .replace("(", "")
                        .replace(")", "")
                        for col in cursor.description
                    ]

                    rows = cursor.fetchall()
                    df = pd.DataFrame(rows, columns=columns)

                    return df

        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Query failed (attempt {attempt+1}/{max_retries}). Retrying...")
                time.sleep(2)
            else:
                logger.error("Query failed permanently", exc_info=True)
                raise


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


# MAIN 
def get_rep_data(rep_id: str):
    """
    Fetches all rep data in a single connection session to save time.
    """
    try:
        rep_id = int(rep_id)

        with get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. PAYOUT + ELIGIBILITY (JOINED)
                # We use a LEFT JOIN on rep_name to get both summary and eligibility in one go.
                joined_query = """
                SELECT p.*, 
                       e.total_eligibility, 
                       e.eligibility_reason, 
                       e.ic_eligibility as ic_eligibility_e, 
                       e.new_hire_eligibility as new_hire_eligibility_e
                FROM ic_implementation.ic_intelligence.payout_summary p
                LEFT JOIN ic_implementation.ic_intelligence.eligibility_2 e 
                  ON LOWER(TRIM(p.`Rep Name`)) = LOWER(TRIM(e.rep_name))
                WHERE p.`Rep ID` = ?
                """
                cursor.execute(joined_query, (rep_id,))
                df = pd.DataFrame(cursor.fetchall(), columns=_get_columns(cursor.description))

                if df.empty:
                    return None

                payout = df.iloc[0].to_dict()
                
                # Extract eligibility specific fields if they exist
                eligibility = {
                    "total_eligibility": payout.get("total_eligibility"),
                    "eligibility_reason": payout.get("eligibility_reason"),
                    "ic_eligibility": payout.get("ic_eligibility_e") or payout.get("ic_eligibility"),
                    "new_hire_eligibility": payout.get("new_hire_eligibility_e") or payout.get("new_hire_eligibility")
                }

                # 2. SALES CREDITING 
                sales_query = """
                SELECT *
                FROM ic_implementation.ic_intelligence.sales_crediting
                WHERE assignment_emp = ?
                """
                cursor.execute(sales_query, (rep_id,))
                sales_df = pd.DataFrame(cursor.fetchall(), columns=_get_columns(cursor.description))
                sales = sales_df.to_dict(orient="records")

        return {
            "payout": payout,
            "eligibility": eligibility,
            "sales": sales
        }

    except Exception:
        logger.error("Error fetching rep data", exc_info=True)
        return None