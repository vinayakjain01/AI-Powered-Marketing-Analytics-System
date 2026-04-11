import google.generativeai as genai

# Configure API
genai.configure(api_key="AIzaSyBXA0syjMMLs8lHgeAukZWtWnA3M-08Wvw")

# Load model
model = genai.GenerativeModel("models/gemini-2.5-flash")

def generate_answer(question, data):

    prompt = f"""
    You are a senior marketing analyst.
    STRICT RULES:
    - ONLY use the data provided below
    - DO NOT infer anything from campaign names
    - DO NOT assume dates from campaign names
    - The SQL query has already filtered the correct time period
    - If data is present, you MUST answer the question
    - Never say "data not available" if rows exist
    Answer the question using the data.

    Question:
    {question}

    Data:
    {data}

    Format your answer like this:

    1. Final Answer (1 line)
    2. Key Numbers (important values)
    3. Insight (business meaning)
    4. Recommendation (what to do)

    Keep it simple, professional and clear.
    """

    response = model.generate_content(prompt)
    return response.text