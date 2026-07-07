# Coach — Process Scheduler for Humans
### A chiefOS Component | Kaggle 5-Day AI Agents Capstone

Coach answers one question: **"What should I be doing right now?"**

This repo contains a terminal demo of the agent harness — a single-file walkthrough of how the agent reasons about a person's schedule, energy, and commitments to make one grounded recommendation at a time.

## Project Demo Video


## Course Concepts Applied
This project was built as the capstone for the Kaggle 5-Day AI Agents Intensive Course with Google. Here's how the course concepts show up in `agent_demo.py`:

**Day 1 — Instructions (the "Brain"):** The `BRAIN` prompt defines the agent's identity and hard rules — it can only make ONE recommendation per response, drawn from a fixed set of categories (START, PROTECT, DEFER, RECOVER, PREPARE, TRIAGE, PROTECT_CAPACITY), and must respond in a strict, parseable format.

**Day 2 — Agent Tools & Interoperability:** The agent calls discrete tools rather than reasoning blind: `get_current_time()` grounds every decision in the real clock, and `assess_capacity()` computes free minutes, energy-adjusted effective capacity, and upcoming commitments from raw input — all deterministic, no LLM call required.

**Day 3 — Agent Skills:** The reasoning is split into modular skills chained together in the loop: `parse_situation_with_gemini()` extracts structured commitments/energy/concerns from free-text input, `get_recommendation()` generates the grounded recommendation, and an optional follow-up skill breaks a task down into its single smallest first step.

**Day 4 — Security & Evaluation:** Only the two genuinely non-deterministic steps (parsing free text, generating the recommendation) call the Gemini API; capacity math stays local and deterministic. Every recommendation is written to an append-only observability log (`log_recommendation()`) so the reasoning behind each decision stays inspectable and trustworthy. LLM calls are wrapped in try/except so a failed API call degrades gracefully instead of crashing the loop.

## Features
- **Time-grounded reasoning:** every recommendation is anchored to the actual current time and day
- **Capacity assessment:** calculates free minutes remaining today, adjusts effective capacity downward when energy is low, and surfaces upcoming commitments
- **Structured recommendation categories:** START, PROTECT, DEFER, RECOVER, PREPARE, TRIAGE, PROTECT_CAPACITY
- **One recommendation at a time:** no lists, no hedging — a single situation, a single action, a single next step
- **Task breakdown follow-up:** optionally decomposes a task into its smallest first physical step with a realistic time estimate
- **Observability:** every recommendation is logged to `demo_coach_log.json`, append-only, with timestamp, situation, recommendation, and category

## Project Structure
```
coach/
├── agent_demo.py          # The full harness: tools, soul, agent loop, observability
├── demo_coach_log.json    # Append-only log of recommendations (created on first run)
└── .env                   # API key and model config (not committed)
```

## Getting Started

**Prerequisites**
- Python 3.10+ ([download](https://www.python.org/downloads/))
- A Google AI Studio API key — free at [aistudio.google.com](https://aistudio.google.com)

1. Clone the repo
```bash
git clone https://github.com/yourusername/coach.git
cd coach
```

2. Install dependencies
```bash
pip install google-genai python-dotenv
```

3. Create a `.env` file in the project root
```
GOOGLE_API_KEY=your-gemini-api-key
MODEL=gemini-3.1-flash-lite
```

4. Run the demo
```bash
python agent_demo.py
```

5. Tell Coach what's on your plate
The demo will ask you what's going on right now — meetings, deadlines, how long you've been working, how you're feeling. It parses that into structured commitments and energy level, assesses your remaining capacity, and gives you one clear recommendation. You can optionally ask it to break the recommendation down into a first physical step.

Every recommendation is logged to `demo_coach_log.json` so you can review the agent's reasoning over time.
