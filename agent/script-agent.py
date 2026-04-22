import os
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# This is the client's formula — you fill this in after the call
CLIENT_FORMULA = """
HOOK (0-5 sec): Start with a bold, provocative statement or question that speaks directly to a real estate agent's frustration or desire. No fluff. Hit hard immediately.

PROBLEM (5-15 sec): Name the specific problem. Make the agent feel deeply understood. Use language they use themselves.

SOLUTION (15-35 sec): Deliver the insight or fix. Be concrete. One clear idea. No more than 2-3 sentences. 

CTA (35-45 sec): One single call to action. Keep it low friction. Example: "Drop a comment below" or "Follow for more."

RULES:
- Conversational tone, never corporate
- Speak directly to the viewer as "you"
- Never use the words "leverage", "synergy", "game-changer"
- Total word count: 90-120 words maximum
- Written to be spoken out loud naturally
"""

SYSTEM_PROMPT = f"""You are a professional short-form video scriptwriter specializing in real estate recruiting content.
You write 45-second scripts that perform on Instagram Reels, Facebook, and YouTube Shorts.

You must follow this exact formula provided by the client:
{CLIENT_FORMULA}

Write ONLY the script. No explanations, no labels, no meta-commentary. Just the words to be spoken."""

def run_script_agent(topic, solution_output):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=600,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Topic: {topic}\n\nResearch and solution context:\n{solution_output}\n\nWrite the 45-second script now."},
        ],
    )

    return response.choices[0].message.content