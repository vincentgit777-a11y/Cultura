# Cultura v1.0.0

**College Cultural Festival Management Platform**

A complete Flask-based web application for managing college cultural festivals. Cultura provides three connected experiences: a public website for discovering events and competitions, a student portal for registrations and team management, and an admin portal for festival administration.

## Features

### Public Website
- **Homepage** — Hero section, featured events, category browsing, schedule preview, festival highlights
- **Events Directory** — Search, filter by category, sort by title/date/status
- **Competitions Directory** — Dedicated competition listing with rules, prizes, judging criteria
- **Event/Competition Details** — Full descriptions, eligibility, team requirements, rules, prizes, FAQ
- **Festival Schedule** — Day-grouped view with time, venue, category filters
- **FAQ** — Accordion-style frequently asked questions

### Student Portal
- **Authentication** — Secure login/register with bcrypt password hashing
- **Dashboard** — Personalized stats, recent registrations, team memberships, upcoming events
- **My Registrations** — Table view with status, references, event links
- **My Teams** — Team cards with members, captain badge, competition links
- **My Schedule** — Personal festival schedule from registered events
- **Profile** — Editable profile with validation

### Admin Portal
- **Dashboard** — Real-time metrics (events, competitions, registrations, students, teams)
- **Event Management** — Full CRUD with publish/unpublish, validation
- **Competition Management** — CRUD with rules, eligibility, team sizes, prizes, judging criteria
- **Registration Management** — List, filter, status transitions
- **Team Management** — List with member details, captain identification
- **Schedule Management** — CRUD with conflict detection, publish control
- **Poster Management** — CRUD with download endpoint
- **Festival Settings** — Centralized configuration

### Technical Highlights
- **Authentication**: bcrypt password hashing, JWT tokens, Flask sessions, role-based decorators
- **Data Storage**: JSON files with atomic writes, file locking, upsert patterns
- **API Layer**: Standardized JSON responses, CulturaApi JavaScript client
- **Design System**: Neo-brutalist Cultura palette (cream, marigold, rose, mint, periwinkle, lavender, peach, deep-plum)
- **Accessibility**: focus-visible, ARIA labels, reduced-motion support, high-contrast mode
- **Responsive**: Mobile-first breakpoints, touch-friendly targets
- **Testing**: 44 backend tests covering routes, registration, validation, security

## Quick Start

### Prerequisites
- Python 3.10+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/vincentgit777-a11y/Cultura.git
cd Cultura

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set a secure CULTURA_SECRET_KEY (generate with: python -c "import secrets; print(secrets.token_hex(32))")

# Run the application
python app.py
```

### Access the Application
Open **http://127.0.0.1:5000** in your browser.

## Creating the First Admin Account

1. Register a student account at `/register`
2. Edit `data/users.json` and change `"role": "student"` to `"role": "admin"` for your user
3. Log in at `/admin/login`

Alternatively, create via API:
```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@college.edu",
    "password": "securepassword123",
    "full_name": "Festival Admin",
    "department": "Administration",
    "academic_year": "4th Year",
    "institution": "Your College"
  }'
```
Then manually update `data/users.json` to set `"role": "admin"`.

## Project Structure

```
Cultura/
├── app.py                 # Main Flask application
├── config.py              # Configuration with environment variables
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variable template
├── CULTURA_PROGRESS.md    # Development progress tracker
├── data/                  # JSON data files (git-ignored registrations)
│   ├── events.json        # Festival events
│   ├── competitions.json  # Competitions with rules/prizes
│   ├── users.json         # User accounts (bcrypt hashes)
│   ├── teams.json         # Team data
│   ├── registrations.json # Registration records
│   ├── schedule_entries.json
│   ├── posters.json
│   ├── notifications.json
│   └── settings.json      # Site settings & FAQ
├── lib/
│   ├── auth.py           # Authentication & authorization
│   ├── responses.py      # Standardized API responses
│   ├── security.py       # CSRF & rate limiting
│   └── storage.py        # Atomic JSON file operations
├── static/
│   ├── css/              # Modular CSS (tokens, base, layout, components, pages, responsive)
│   ├── js/               # JavaScript (api.js, events.js, main.js, registration.js)
│   └── images/           # Brand assets, textures
├── templates/
│   ├── base.html         # Base layout
│   ├── index.html        # Homepage
│   ├── events.html       # Events directory
│   ├── event_detail.html # Event detail
│   ├── competitions.html # Competitions directory
│   ├── competition_detail.html
│   ├── schedule.html     # Festival schedule
│   ├── faq.html          # FAQ page
│   ├── login.html        # Student login
│   ├── register_account.html
│   ├── admin/login.html  # Admin login
│   ├── student/          # Student portal templates
│   └── partials/         # Shared partials (header, footer, event_card)
└── tests/                # Unit tests
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CULTURA_SECRET_KEY` | Flask secret key (required for production) | dev key |
| `CULTURA_HOST` | Server host | 127.0.0.1 |
| `CULTURA_PORT` | Server port | 5000 |
| `CULTURA_HTTPS` | Enable secure cookies (1/0) | 0 |
| `CULTURA_DATA_DIR` | Data directory path | ./data |
| `CULTURA_RATE_LIMIT_MAX` | Registration attempts per window | 10 |
| `CULTURA_RATE_LIMIT_WINDOW` | Rate limit window (seconds) | 600 |

## API Endpoints

### Authentication
- `POST /api/auth/login` — Login, returns JWT
- `POST /api/auth/register` — Register student account
- `GET /api/auth/me` — Current user info

### Student API (requires auth)
- `GET /api/student/dashboard` — Dashboard data
- `GET /api/student/registrations` — User's registrations
- `GET /api/student/teams` — User's teams
- `POST /api/student/teams` — Create team
- `GET /api/student/profile` — Profile data
- `PUT /api/student/profile` — Update profile

### Admin API (requires admin role)
- `GET /api/admin/dashboard` — Metrics & recent activity
- `GET/POST /api/admin/events` — Event CRUD
- `GET/POST /api/admin/competitions` — Competition CRUD
- `GET /api/admin/registrations` — All registrations
- `PATCH /api/admin/registrations/<id>` — Update status
- `GET /api/admin/teams` — All teams
- `GET/POST/PUT/DELETE /api/admin/schedule` — Schedule CRUD
- `GET/POST/PUT/DELETE /api/admin/posters` — Poster CRUD
- `GET/PUT /api/admin/settings` — Festival settings

## Development

### Running Tests
```bash
python -m unittest discover tests -v
```

### Adding Sample Data
Edit the JSON files in `data/` to add events, competitions, and configure the festival.

## Production Deployment

For production deployment:
1. Set `CULTURA_HTTPS=1` and `CULTURA_SECRET_KEY` to a strong random value
2. Use a production WSGI server (gunicorn, uWSGI)
3. Configure a reverse proxy (nginx)
4. Set up proper logging and monitoring
5. Consider migrating to a database (PostgreSQL, MySQL) for scale

## License

MIT License — Feel free to use and modify for your college festival.

## Version History

### v1.0.0 (Initial Release)
- Complete public, student, and admin experiences
- JSON-based storage with atomic operations
- Neo-brutalist Cultura design system
- Role-based authentication (student/admin)
- Comprehensive test suite (44 tests)
- RESTful API with standardized responses

---

**Built for college cultural festivals everywhere.** 🎭🎵🎨