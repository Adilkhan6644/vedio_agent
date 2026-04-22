import os
import sys
import json
import time
from datetime import datetime
from dotenv import load_dotenv

# Load env vars FIRST (before importing agents that need GROQ_API_KEY)
load_dotenv()

from research_agent import run_solution_agent, run_script_agent, run_rating_agent, search_web

def run_script_pipeline(topic):
    print("\n🔍 STEP 1: Web Search Agent running...")
    search_results = search_web(topic)
    print(f"   Found search results for: '{topic}'")
    print("\n📋 WEB SEARCH RESULTS:")
    print("─" * 50)
    print(search_results)
    print("─" * 50)

    print("\n📡 STEP 2: Solution Research Agent running...")
    solution = run_solution_agent(topic)
    print(solution)

    print("\n✍️  STEP 3: Scriptwriting Agent running...")
    script = run_script_agent(topic, solution)
    print(script)

    print("\n⭐ STEP 4: Rating & Optimization Agent running...")
    result = run_rating_agent(script)

    print("\n📊 SCORES:")
    print(f"  Hook:     {result['scores']['hook']}/10")
    print(f"  Problem:  {result['scores']['problem']}/10")
    print(f"  Solution: {result['scores']['solution']}/10")
    print(f"  CTA:      {result['scores']['cta']}/10")
    print(f"  Overall:  {result['scores']['overall']}/10")

    print("\n📝 FINAL OPTIMIZED SCRIPT:")
    print("─" * 50)
    print(result['optimized_script'])
    print("─" * 50)

    # Save to file — this is what gets passed to HeyGen in Step 5
    output = {
        "topic": topic,
        "timestamp": datetime.now().isoformat(),
        "solution": solution,
        "search_results": search_results,
        "original_script": script,
        "scores": result['scores'],
        "feedback": result['feedback'],
        "final_script": result['optimized_script'],
    }

    filename = f"scripts/script-{int(time.time() * 1000)}.json"
    os.makedirs("scripts", exist_ok=True)
    with open(filename, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n✅ Saved to {filename}")

    return output


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "agents afraid to ask for referrals"
    run_script_pipeline(topic)