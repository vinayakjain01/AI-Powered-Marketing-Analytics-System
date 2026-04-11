import psycopg2
import pandas as pd

def get_connection():
    return psycopg2.connect(
        host="localhost",
        database="campaign",
        user="postgres",
        password="1234",
        options="-c search_path=campaign_data"
    )

def run_query(query):
    conn = get_connection()
    df = pd.read_sql(query, conn)
    conn.close()
    return df