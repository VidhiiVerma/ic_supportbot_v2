from dotenv import load_dotenv
load_dotenv()

import os
import logging
import pandas as pd
from databricks import sql

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


# MAIN 
def get_rep_data(rep_id: str):
    try:
        rep_id = int(rep_id)

        # PAYOUT 
        payout_query = """
        SELECT *
        FROM ic_implementation.ic_intelligence.payout_summary
        WHERE `Rep ID` = ?
        """

        payout_df = fetch_df(payout_query, (rep_id,))

        if payout_df.empty:
            return None

        payout = payout_df.iloc[0].to_dict()
        rep_name = payout.get("rep_name")

        # ELIGIBILITY 
        eligibility = {}

        if rep_name:
            eligibility_query = """
            SELECT *
            FROM ic_implementation.ic_intelligence.eligibility_2
            WHERE LOWER(TRIM(rep_name)) = LOWER(TRIM(?))
            """

            try:
                eligibility_df = fetch_df(eligibility_query, (rep_name,))

                if not eligibility_df.empty:
                    eligibility = eligibility_df.iloc[0].to_dict()

            except Exception:
                eligibility = {}

        #  SALES CREDITING 
        sales_query = """
        SELECT *
        FROM ic_implementation.ic_intelligence.sales_crediting
        WHERE assignment_emp = ?
        """

        sales_df = fetch_df(sales_query, (rep_id,))
        sales = sales_df.to_dict(orient="records")

        #  FINAL OUTPUT 
        return {
            "payout": payout,
            "eligibility": eligibility,
            "sales": sales
        }

    except Exception:
        logger.error("Error fetching rep data", exc_info=True)
        return None