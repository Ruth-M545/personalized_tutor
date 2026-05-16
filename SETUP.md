# Personalized Tutor — Quick Start Guide

## ✅ Setup Complete

Your Django environment is ready! The app has:
- ✓ SQLite database configured (`db.sqlite3`)
- ✓ Admin user created (`admin` / password required on first login)
- ✓ All migrations applied
- ✓ Development server tested

---

## 🚀 Running the Application

### Option 1: Simple Dev Server (HTTP only, limited features)

```bash
# Using the run script
bash run.sh

# Or manually
./.venv/bin/python manage.py runserver 0.0.0.0:8000
```

Then visit: **http://localhost:8000**

**Limitations:** 
- No real-time streaming chat (WebSockets require Redis + Daphne)
- No background tasks (Celery tasks won't run)

### Option 2: Full Stack with Docker (Recommended for testing)

Requires Docker and Docker Compose installed.

```bash
# Configure your .env with API keys
cp .env.example .env
nano .env  # Add ANTHROPIC_API_KEY or OPENAI_API_KEY

# Start everything
docker-compose up --build

# In another terminal, create superuser
docker-compose exec web python manage.py createsuperuser
```

Then visit: **http://localhost:8000**

---

## 🔑 Configuration

### Required: LLM API Key

Edit `.env` and add **one** of:

```env
# Option A: Anthropic Claude (recommended for tutoring)
ANTHROPIC_API_KEY=sk-ant-...

# Option B: OpenAI GPT-4
OPENAI_API_KEY=sk-...
```

### Optional: Email Notifications

For daily spaced-repetition reminders:

```env
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

---

## 📚 Features

| Feature | Dev Server | Docker |
|---------|-----------|--------|
| Dashboard & UI | ✓ | ✓ |
| REST API | ✓ | ✓ |
| Streaming Chat | ✗ | ✓ |
| Spaced Repetition | ✗ | ✓ |
| Background Tasks | ✗ | ✓ |
| Email Reminders | ✗ | ✓ |

---

## 👤 Admin Access

1. Visit: **http://localhost:8000/admin**
2. Login: `admin` / (use `python manage.py changepassword admin` to set password)

### Add Learning Topics

In Django Admin → Learning → Topics:

1. Create topics for your subject (e.g., "Python Basics", "Functions")
2. Link prerequisites: "Functions" → requires "Python Basics"
3. Set difficulty (1-5) and estimated time

Once topics exist, they'll appear in the "Start Session" dropdown.

---

## 🧪 Testing the Tutor

1. **Dashboard**: http://localhost:8000/
2. **Start a Session**: Click "Start Session", pick a topic
3. **Chat**: WebSocket chat works with Docker. HTTP mode shows REST API.

---

## 🐛 Common Issues

### "ModuleNotFoundError: No module named 'celery'"
- **Fix**: Use the venv Python: `./.venv/bin/python manage.py ...`

### "FATAL: password authentication failed for user 'tutor'"
- **Fix**: We switched to SQLite. If you need PostgreSQL:
  - Install & start PostgreSQL locally
  - Update `.env` with correct credentials

### "Redis connection refused"
- **Fix**: Redis is only needed for full features. Dev server uses in-memory cache.

### WebSocket connection fails (404)
- **Expected** in dev server. Full streaming requires Docker.

---

## 📖 Project Structure

```
personalized_tutor/
├── apps/
│   ├── accounts/        # User profiles, preferences
│   ├── learning/        # Sessions, topics, messages
│   ├── agent/           # AI tutor brain (orchestrator, memory, feedback)
│   └── scheduler/       # Spaced repetition, background tasks
├── templates/           # HTML pages
├── tutor/               # Django settings & routing
├── requirements.txt     # Python dependencies
├── docker-compose.yml   # Full stack setup
└── .env                 # Configuration (API keys, DB, email)
```

---

## 🤖 How It Works

1. **User starts a chat session** for a topic
2. **Orchestrator** reads user message + learner profile from long-term memory
3. **LLM streaming** sends tokens to browser in real-time
4. **Feedback analyzer** (after message) detects knowledge gaps
5. **Spaced repetition** schedules review cards based on SM-2 algorithm
6. **Background tasks** (Celery) send daily email reminders, progress snapshots

---

## 📞 Support

- Django Admin: http://localhost:8000/admin
- REST API: http://localhost:8000/api/
- Logs: Check terminal output for errors

---

**Happy learning! 🚀**
