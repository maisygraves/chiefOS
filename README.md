# Coach — Process Scheduler for Humans
### A chiefOS Component | Kaggle 5-Day AI Agents Capstone

Coach is a local-first AI agent that acts as an external process scheduler for humans. It answers one question: **"What should I be doing right now?"**

Inspired by the parallel between human cognition and operating systems, Coach functions as a kernel assistant — compensating for moments when executive function struggles to prioritize, start, or sequence tasks. It manages a 14-day capacity window, detects conflicts, and provides context-aware coaching grounded in your actual schedule and energy state.

## Project Demo Video


---

## The Human OS Parallel

A personal operating system maps to human cognition like this:

| OS Component | Human Equivalent |
|---|---|
| Hardware | Body — sleep, nutrition, movement |
| Kernel | Nervous system — executive function |
| CPU | Attention — your scarcest resource |
| Process Scheduler | **Coach — what gets attention and when** |
| Memory | Working memory + long-term knowledge |
| Power Management | Energy and recovery |

Coach is the process scheduler. It manages what runs when, detects conflicts, allocates time across competing demands, and monitors capacity — externally supporting the moments when the internal scheduler needs help.

---

## Course Concepts Applied

Built as the capstone for the Kaggle 5-Day AI Agents Intensive Course with Google.

**Intro to Agents & Vibe Coding**
Built using Google's Antigravity IDE and Claude as the vibe-coding orchestrator. The output is a personal AI agent that orchestrates its own tasks, tools, and API calls. `AGENTS.md` defines the agent's identity and rules. `agent.py` defines the agent's logic and harness.

**Day 2: Agent Tools & Interoperability**
Following a local-first workflow, the agent orchestrates across multiple tools (`parse_input`, `place_item`, `check_deadline`, `coach_response`, `breakdown_tasks`, `roll_window`) and persistent data stored in local JSON files — limiting external LLM API calls to non-deterministic reasoning tasks only.

**Day 3: Agent Skills**
Modular, discrete skills handle specific reasoning tasks. The agent picks the right skill based on context. Skills adjust persistent memory files (`schedule.json`, `changelog.json`, `dailylogs.json`, `settings.json`) and never modify state without user confirmation.

**Day 4: Security & Evaluation**
The harness architecture is built with security in mind. Only non-deterministic tasks call the Gemini API. Personal schedule data never leaves the local machine. An append-only logger provides full observability — every agent action is recorded with before/after state. 41 automated tests validate the system.

---

## How the Agent Has Context

The agent builds context from three sources before every response:

**1. Real-time conversation** — what the person says right now
**2. `schedule.json`** — all confirmed commitments in the 14-day window
**3. `dailylogs.json`** — today's energy, sleep quality, and mood

This means coaching responses are grounded in reality:

```
Today is Monday. Current time: 2pm.
Schedule: deep work 1-3pm, team meeting 3-4pm.
Today's log: sleep 6hrs (5/10), energy 4/10.
User: "I can't focus."
```

The agent sees all of that and responds with a specific, honest recommendation — not generic advice.

---

## Features

**Capacity Management**
Natural language input, confirmation before placement, conflict detection across 14 days, never places over a Need, append-only changelog.

**AI Coaching**
Context-aware chat that knows your schedule, your energy levels, and your deadlines. Operational voice — direct, honest, no fluff. Returns concrete options and a confirmation prompt. Breaks priorities into actionable tasks with time estimates.

---

## Agent Harness

| Harness Component | Implementation |
|---|---|
| **Instructions & rules** | `AGENTS.md` — agent identity, voice, confirmation rule |
| **Tools** | `/backend/tools/` — 6 discrete skill functions |
| **Sandbox** | Local Python environment — data never leaves the machine |
| **Orchestration** | `agent.py` — the agent loop; `routers/` — HTTP endpoints |
| **Guardrails** | Confirmation rule — nothing placed without user approval |
| **Observability** | `logger.py` — append-only changelog of every action |

---

## Project Structure

```
coach/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── agent.py             # Agent loop and orchestration
│   ├── AGENTS.md            # Agent identity and rules
│   ├── routers/             # HTTP endpoints (7 routers)
│   ├── tools/               # Agent skills — what the agent can do
│   ├── models/              # Pydantic v2 data models
│   ├── memory/              # Session and long-term storage
│   ├── observability/       # Append-only changelog
│   ├── data/                # Local JSON storage (gitignored)
│   └── tests/               # 41 automated tests

```

---

## Getting Started

### Prerequisites

- Python 3.14.6 ([download](https://www.python.org/downloads/))
- Node.js 18+ ([download](https://nodejs.org))
- A Google AI Studio API key — free at [aistudio.google.com](https://aistudio.google.com)

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/coach.git
cd coach
```

### 2. Set up the backend

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file in the `backend` folder:

```
GOOGLE_API_KEY=your-gemini-api-key
MODEL=gemini-3.1-flash-lite
ALLOWED_ORIGINS=http://localhost:5173
VAPID_PUBLIC_KEY=placeholder
VAPID_PRIVATE_KEY=placeholder
VAPID_EMAIL=placeholder
```

Start the backend:

```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Run the tests

```bash
cd backend
python -m pytest tests/ -v
```

---

## Known Limitations

- Backend must be running for notifications — APScheduler only fires when the Python process is active
- Push notifications require VAPID keys — generate with `py-vapid` and add to `.env`
- Single-user local deployment — do not expose to the public internet without adding authentication
- JSON storage — suitable for local use; Postgres migration path is ready (all keys map to table names)

---

## Part of chiefOS

Coach is the process scheduler component of chiefOS — a personal operating system for human beings managing three domains: physical and mental needs, education and skill development, and civic commitments. chiefOS is in active development.
