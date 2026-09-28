# CLAUDE.md: messaging-service

Guidance for Claude Code when working in `messaging-service/`.

## What this is

A **Flask** backend for Ansera Business Admin. It's a boilerplate for now: one route, `GET /`, which returns `{"message": "Hello, World!"}`. Its purpose (messaging) isn't built yet. The sibling services are `../configuration-service` (Django, port 8000) and `../frontend-app` (Vite/React, port 5173).

The user named the folder "messaing-service"; it was created as `messaging-service`, assumed to be a typo.

## Stack and constraints

- **Flask 3.1** (Python 3.9+; the local venv uses 3.14). Flask is the **only** dependency.
  - The user said no database or other dependencies for now. Don't add any (SQLAlchemy, flask-cors, python-dotenv, pytest, …) without asking.
  - Add new dependencies to `requirements.txt` with a version range.
- **Default port 8001**, because 8000 is taken by configuration-service. Keep it that way. `run.py` reads `PORT`, `HOST` and `FLASK_DEBUG` from the environment, using `os.getenv`.
- **Tests:** stdlib `unittest` with Flask's test client (`create_app({'TESTING': True}).test_client()`). Run them with `python -m unittest -v`.

## Structure and conventions

- **App factory:** `app/__init__.py` defines `create_app(config=None)`, which creates the Flask app, applies config overrides and registers blueprints. Nothing should create a global `app` except `run.py`.
- **Routes** live in blueprints. `app/routes.py` has `bp` (named `main`). Add a new module per area of functionality (e.g. `app/messages.py`) and register it in `create_app()`.
- **JSON only:** return `jsonify(...)` from every route. `app.json.sort_keys = False` keeps keys in the order written.
- **Entry points:**
  - `python run.py`: the dev server on 127.0.0.1:8001, debug on by default.
  - `flask --app app run --port 8001`: Flask's CLI finds `create_app` automatically.
- **Not set up yet** (add only when asked):
  - **CORS.** `frontend-app` at `http://localhost:5173` will need it before calling this service from the browser, e.g. via flask-cors.
  - **Auth.** To accept the frontend's JWTs, the service would need to verify configuration-service's SimpleJWT tokens (HS256, signed with Django's `SECRET_KEY`).
  - **A production WSGI server** (e.g. gunicorn).

## Commands (run from `messaging-service/`, with `.venv` active or via `.venv/bin/python`)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # http://127.0.0.1:8001
python -m unittest -v         # tests
flask --app app routes        # list routes
```

Before finishing a change, run `python -m unittest -v`; it must pass.

## Environment notes for Claude

- The sandbox blocks listening on ports, so `python run.py` can't be smoke-tested from inside Claude. Use the Flask test client (the unit tests) instead.
- The user's shell sets `PYTHONPATH` to a Spark install, so `pip freeze` shows `pyspark`. Don't add it to `requirements.txt`.
