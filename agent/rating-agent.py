import os
import json
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are a harsh but fair short-form video script editor. Your job is to rate and improve scripts for real estate recruiting videos.

Rate each section on a scale of 1-10 where:
1-4 = weak, needs full rewrite
5-7 = decent, needs improvement  
8-10 = strong, minor tweaks only

Scoring criteria:
- HOOK: Does it stop the scroll in under 3 seconds? Is it provocative enough?
- PROBLEM: Does it make the agent feel deeply understood? Is it specific?
- SOLUTION: Is it clear, concrete, and genuinely useful?
- CTA: Is it low-friction and natural?

You MUST respond in this exact JSON format and nothing else:
{
  "scores": {
    "hook": <number>,
    "problem": <number>,
    "solution": <number>,
    "cta": <number>,
    "overall": <number>
  },
  "feedback": {
    "hook": "<one sentence of specific feedback>",
    "problem": "<one sentence of specific feedback>",
    "solution": "<one sentence of specific feedback>",
    "cta": "<one sentence of specific feedback>"
  },
  "optimized_script": "<the full rewritten script, improved based on your feedback, 90-120 words>"
}"""

def run_rating_agent(script):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1200,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Rate and optimize this script:\n\n{script}"},
        ],
    )

    raw = response.choices[0].message.content
    return json.loads(raw)