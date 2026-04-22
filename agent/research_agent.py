import os
import json
import requests
from groq import Groq

# ── clients ──────────────────────────────────────────────────────────────────
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
SERPER_API_KEY = os.environ.get("SERPER_API_KEY")

# ── Step 1: web search via Serper ─────────────────────────────────────────────
def search_web(query: str, num_results: int = 5) -> str:
    """
    Hits Serper.dev and returns a clean text block
    that the LLM can read directly.
    Get your free key (2,500 queries, no card): https://serper.dev
    """
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"q": query, "num": num_results}

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()

    # flatten results into readable text for the LLM
    lines = []

    # knowledge graph snippet (if Google has a direct answer)
    if "knowledgeGraph" in data:
        kg = data["knowledgeGraph"]
        if "description" in kg:
            lines.append(f"QUICK FACT: {kg['description']}")

    # answer box (featured snippet)
    if "answerBox" in data:
        ab = data["answerBox"]
        snippet = ab.get("answer") or ab.get("snippet", "")
        if snippet:
            lines.append(f"FEATURED ANSWER: {snippet}")

    # organic results
    for item in data.get("organic", [])[:num_results]:
        title   = item.get("title", "")
        snippet = item.get("snippet", "")
        link    = item.get("link", "")
        lines.append(f"- {title}: {snippet} ({link})")

    return "\n".join(lines) if lines else "No results found."


# ── Step 2: solution research agent ──────────────────────────────────────────
RESEARCH_SYSTEM_PROMPT = """You are an expert real estate recruiting strategist with 15 years of experience.
You are given a topic/problem that real estate agents face, plus live web search results for context.

Using BOTH your expertise AND the search results, produce a structured solution.

Respond in this EXACT format — no extra text:

PROBLEM: [one sentence — the core pain point agents feel]
ROOT CAUSE: [one sentence — why this actually happens]
INSIGHT: [one sentence — the key truth most agents miss]
ACTION STEPS:
1. [specific, actionable step]
2. [specific, actionable step]
3. [specific, actionable step]
HOOK ANGLE: [one sentence — the most emotionally compelling angle for a 45-second video]"""


def run_solution_agent(topic: str) -> str:
    """
    Searches the web for the topic, then asks Groq to produce
    a structured solution using those results as context.
    """
    print(f"\n🔍 Searching web for: '{topic}'...")
    search_results = search_web(topic)
    print("   Search done.\n")

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=600,
        messages=[
            {
                "role": "system",
                "content": RESEARCH_SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": (
                    f"TOPIC: {topic}\n\n"
                    f"LIVE WEB SEARCH RESULTS:\n{search_results}\n\n"
                    f"Now produce the structured solution."
                )
            }
        ]
    )

    return response.choices[0].message.content


# ── Step 3: script writer agent ───────────────────────────────────────────────
CLIENT_FORMULA = """
HOOK (0-5 sec): Bold, provocative statement or question targeting a real estate agent's frustration. No fluff.
PROBLEM (5-15 sec): Name the specific problem. Make the agent feel deeply understood.
SOLUTION (15-35 sec): Deliver the fix. Concrete. One clear idea. Max 2-3 sentences.
CTA (35-45 sec): One low-friction call to action. Example: "Follow for more" or "Drop a comment below."

RULES:
- Conversational tone, never corporate
- Speak directly as "you"
- Never use: leverage, synergy, game-changer
- Total word count: 90-120 words
- Written to be spoken out loud
"""

SCRIPT_SYSTEM_PROMPT = f"""You are a professional short-form video scriptwriter for real estate recruiting content.
You write 45-second scripts for Instagram Reels, Facebook, and YouTube Shorts.

Follow this formula exactly:
{CLIENT_FORMULA}

Write ONLY the script. No labels, no explanations. Just the words to be spoken."""


def run_script_agent(topic: str, solution: str) -> str:
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=400,
        messages=[
            {
                "role": "system",
                "content": SCRIPT_SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": (
                    f"TOPIC: {topic}\n\n"
                    f"RESEARCH & SOLUTION:\n{solution}\n\n"
                    f"Write the 45-second script now."
                )
            }
        ]
    )
    return response.choices[0].message.content


# ── Step 4: your existing rating agent (unchanged) ────────────────────────────
RATING_SYSTEM_PROMPT = """You are a harsh but fair short-form video script editor. Your job is to rate and improve scripts for real estate recruiting videos.

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


def run_rating_agent(script: str) -> dict:
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1200,
        messages=[
            {"role": "system", "content": RATING_SYSTEM_PROMPT},
            {"role": "user",   "content": f"Rate and optimize this script:\n\n{script}"}
        ]
    )
    raw = response.choices[0].message.content
    return json.loads(raw)


# ── full pipeline ─────────────────────────────────────────────────────────────
def run_pipeline(topic: str):
    print("=" * 55)
    print(f"  TOPIC: {topic}")
    print("=" * 55)

    # Step 2 — research with live web context
    print("\n📡 STEP 2: Solution Research Agent...")
    solution = run_solution_agent(topic)
    print(solution)

    # Step 3 — write script from research
    print("\n✍️  STEP 3: Scriptwriting Agent...")
    script = run_script_agent(topic, solution)
    print(script)

    # Step 4 — rate and optimize
    print("\n⭐ STEP 4: Rating & Optimization Agent...")
    result = run_rating_agent(script)

    print("\n📊 SCORES:")
    for section, score in result["scores"].items():
        print(f"   {section.capitalize():<10} {score}/10")

    print("\n💬 FEEDBACK:")
    for section, note in result["feedback"].items():
        print(f"   {section.capitalize()}: {note}")

    print("\n📝 FINAL OPTIMIZED SCRIPT:")
    print("-" * 55)
    print(result["optimized_script"])
    print("-" * 55)

    # save output
    os.makedirs("scripts", exist_ok=True)
    import time
    filename = f"scripts/script_{int(time.time())}.json"
    with open(filename, "w") as f:
        json.dump({
            "topic":           topic,
            "solution":        solution,
            "draft_script":    script,
            "scores":          result["scores"],
            "feedback":        result["feedback"],
            "final_script":    result["optimized_script"]
        }, f, indent=2)

    print(f"\n✅ Saved to {filename}")
    return result


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "why real estate agents plateau at $100k"
    run_pipeline(topic)