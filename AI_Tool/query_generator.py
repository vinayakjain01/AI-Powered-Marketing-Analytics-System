import google.generativeai as genai

model = genai.GenerativeModel("models/gemini-2.5-flash")

SCHEMA = """
Tables:

fact_ads:
- date_id
- campaign_id
- amount_spent
- impressions
- clicks
- purchases
- purchase_value

dim_campaign:
- campaign_id
- campaign_name
- sales_platform
- geo_location_segment
- country_funnel

dim_date:
- date_id
- month
- year
"""

def generate_sql(question):

    prompt = f"""
    You are an expert PostgreSQL analyst.
    Convert the question into SQL using the schema below.
    IMPORTANT RULES:
    - month is INTEGER (1-12)
    - If question contains month name (e.g., March), convert it to number (March = 3)
    - Always prevent division by zero using NULLIF or CASE WHEN
    - If metric is NULL, treat it as 0
    - Always SELECT time column (month/year) when filtering by time
    - The dataset already reflects the correct filter conditions
    IMPORTANT RULES:
    -Always calculate metrics using aggregation:
    CPC = CASE WHEN SUM(clicks) = 0 THEN 0 ELSE SUM(amount_spent)/SUM(clicks) END
    CTR = CASE WHEN SUM(impressions) = 0 THEN 0 ELSE SUM(clicks)/SUM(impressions) END
    ROI = CASE WHEN SUM(amount_spent) = 0 THEN 0 ELSE (SUM(purchase_value) - SUM(amount_spent)) / SUM(amount_spent) END
    - Always GROUP BY relevant column (campaign, country, month etc.)
    - Never return raw table
    - Always return top results (LIMIT 5 or 10)
    - Always include numbers (spend, revenue, conversions)
    Schema:
    {SCHEMA}
    Return ONLY SQL.
    Question:
    {question}
    """

    response = model.generate_content(prompt)
    sql = response.text.strip()

    return sql


def clean_sql(sql):
    return sql.replace("```sql", "").replace("```", "").strip()