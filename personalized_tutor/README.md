# Personalized Learning Tutor

A full-stack Django application that provides an adaptive, memory-enabled AI tutor. The tutor remembers what you struggle with, tracks mastery over weeks, adjusts difficulty in real time, schedules spaced repetition review sessions, and proactively guides your learning path.

## Architecture

```
Browser (Chat UI + Dashboard)
    ↕ WebSocket (streaming)  ↕ HTTP
Django + Channels (Daphne ASGI server)
    ↓
Tutor Agent Core
  ├── Orchestrator       — decides what to teach next
  ├── Pedagogy Engine    — explains, quizzes, detects gaps
  └── Feedback Analyzer  — scores answers, updates mastery
    ↓
Memory System
  ├── Short-term (Redis) — session context window
  └── Long-term (PostgreSQL) — mastery map, struggle areas, history
    ↓
LLM Backend (Anthropic Claude or OpenAI GPT-4)
    ↕
Celery Workers
  ├── Spaced-repetition scheduler (SM-2)
  ├── Daily review email reminders
  ├── Progress snapshots
  └── Dormant learner nudges
```

## Quick Start (Docker — recommended)

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY or OPENAI_API_KEY

# 2. Start everything
docker-compose up --build

# 3. Run migrations & create superuser
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser

# 4. Open http://localhost:8000
```

## Manual Setup (local development)

### Prerequisites
- Python 3.12+
- PostgreSQL 15+
- Redis 7+

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your database credentials and API key

# 4. Run migrations
python manage.py migrate

# 5. Create superuser
python manage.py createsuperuser

# 6. Start Redis (separate terminal)
redis-server

# 7. Start Celery worker (separate terminal)
celery -A tutor worker -l info

# 8. Start Celery beat scheduler (separate terminal)
celery -A tutor beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler

# 9. Start the ASGI server
daphne -p 8000 tutor.asgi:application
# or for development: python manage.py runserver (HTTP only, no WebSockets)
```

## Features

### Core Tutor Agent
- **Streaming responses** via WebSockets — tokens appear as they're generated
- **Adaptive difficulty** — the orchestrator reads mastery scores and adjusts in real time
- **Gap detection** — structured LLM analysis of every learner response
- **Socratic teaching** — the tutor asks before explaining
- **Session summaries** — auto-generated after each session with mastery updates

### Memory System
- **Short-term (Redis)** — sliding context window keeps conversations coherent without hitting token limits
- **Long-term (PostgreSQL)** — mastery map, struggle areas, goals, session history persist across weeks
- **Mastery updates** — exponential moving average ensures smooth tracking: `new = 0.7×old + 0.3×score`

### Spaced Repetition
- **SM-2 algorithm** — industry-standard algorithm (used by Anki/SuperMemo)
- **Auto-card generation** — tutor creates flashcards at session end for key concepts
- **Quality scoring (0–5)** — learner rates recall difficulty; interval adjusts accordingly
- **Daily reminders** — Celery beat sends email at preferred review time

### Dashboard
- **Progress charts** — mastery trend lines per subject over time
- **Struggle areas** — visual list of detected weak spots
- **Active goals** — track learning objectives with progress %
- **Recent sessions** — quick access to continue any conversation

## LLM Configuration

Set `LLM_PROVIDER` in `.env`:

| Provider | Model string | Notes |
|---|---|---|
| `anthropic` | `claude-sonnet-4-20250514` | Default; best for tutoring |
| `openai` | `gpt-4o` | Alternative |

## Adding Topics (Knowledge Graph)

Via Django Admin → Topics, or via management command:

```python
# In Django shell: python manage.py shell
from apps.learning.models import Topic
python_basics = Topic.objects.create(
    name="Python Basics",
    slug="python-basics",
    subject="Python",
    difficulty_level=1,
    estimated_minutes=20,
)
functions = Topic.objects.create(
    name="Functions",
    slug="python-functions",
    subject="Python",
    difficulty_level=2,
)
functions.prerequisites.add(python_basics)
```

## Periodic Tasks

Set up in Django Admin → Periodic Tasks (django-celery-beat):

| Task | Schedule | Description |
|---|---|---|
| `scheduler.daily_review_reminder` | Every day 08:00 | Email users with due cards |
| `scheduler.take_progress_snapshot` | Every night 00:00 | Snapshot mastery for trend charts |
| `scheduler.detect_dormant_learners` | Every day 10:00 | Nudge learners inactive for 3+ days |

## Project Structure

```
tutor_project/
├── tutor/                  # Django project config
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py             # WebSocket routing
│   └── celery.py
├── apps/
│   ├── accounts/           # Custom User model + LearnerProfile
│   ├── learning/           # Sessions, Messages, Topics, ReviewCards
│   │   ├── consumers.py    # WebSocket consumer
│   │   ├── routing.py      # WS URL patterns
│   │   └── views.py        # HTTP views + REST API
│   ├── agent/              # AI tutor brain
│   │   ├── orchestrator.py # Main coordinator
│   │   ├── memory.py       # Short + long term memory
│   │   ├── feedback.py     # Answer analysis
│   │   ├── prompts.py      # All prompt templates
│   │   └── pedagogy.py     # Teaching strategies
│   └── scheduler/          # Background tasks
│       ├── tasks.py        # Celery tasks
│       └── spaced_repetition.py  # SM-2 algorithm
├── templates/
│   ├── chat/chat.html      # Streaming chat interface
│   └── dashboard/home.html # Progress dashboard
├── requirements.txt
├── docker-compose.yml
└── Dockerfile
```
