import os
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are an expert real estate recruiting strategist with 15 years of experience. 
When given a topic or problem that real estate agents face, you research and produce a structured solution.

Always respond in this exact format:
PROBLEM: [one sentence — the core pain point agents feel]
ROOT CAUSE: [one sentence — why this actually happens]
INSIGHT: [one sentence — the reframe or key truth most agents miss]
ACTION STEPS:
1. [specific, actionable step]
2. [specific, actionable step]
3. [specific, actionable step]
HOOK ANGLE: [one sentence — the most emotionally compelling angle for a 45-second video]"""

def run_solution_agent(topic):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=800,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Topic: {topic}"},
        ],
    )

    return response.choices[0].message.content