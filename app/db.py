import os
from databricks import sql

def get_connection():
    return sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOST"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN")
    )


def run_query(query: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query)

        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

        return [dict(zip(columns, row)) for row in rows]

    finally:
        conn.close()  