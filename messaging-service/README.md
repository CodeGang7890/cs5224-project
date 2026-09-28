# Messaging Service

Flask backend for Ansera Business Admin. It's a minimal boilerplate for now, with no database or other dependencies. It runs on **port 8001**, because 8000 is used by `configuration-service` (Django).

## Tech stack

| Concern | Library |
| --- | --- |
| Web framework | [Flask](https://flask.palletsprojects.com/) 3.1 |
| Tests | Python's built-in `unittest` + Flask's test client |

## Prerequisites

- **Python 3.9+** (developed with 3.14). Check with `python3 --version`.

## Getting started

Run all commands from the `messaging-service/` folder.

```bash
cd messaging-service

# 1. Create and activate a virtual environment (first time only)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the development server
python run.py                      # http://127.0.0.1:8001
```

Check that it's running:

```bash
curl http://127.0.0.1:8001/
# {"message": "Hello, World!"}
```

When you come back later, reactivate the virtual environment and start the server:

```bash
source .venv/bin/activate
python run.py
```

### Options

`run.py` reads these environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` | `8001` | Port to listen on, e.g. `PORT=8002 python run.py` |
| `HOST` | `127.0.0.1` | Interface to bind. Use `0.0.0.0` to accept connections from other machines or containers. |
| `FLASK_DEBUG` | `1` | `1` enables debug mode (auto-reload and a detailed error page). Set it to `0` otherwise. |

You can also use Flask's own CLI, which finds the `create_app()` factory automatically:

```bash
flask --app app run --port 8001 --debug
flask --app app routes              # list all routes
```

## Endpoints

| Method | URL | Response |
| --- | --- | --- |
| `GET` | `/` | `{"message": "Hello, World!"}` |

## Running tests

```bash
python -m unittest -v
```

## Project structure

```
messaging-service/
├── app/
│   ├── __init__.py     # create_app(): application factory, registers blueprints
│   └── routes.py       # Blueprint with the routes (GET /)
├── tests/
│   └── test_routes.py
├── run.py              # Dev server entry point (port 8001)
└── requirements.txt
```

## Adding a route

Add a function to `app/routes.py`:

```python
@bp.get('/ping')
def ping():
    return jsonify(status='ok')
```

For a larger group of routes, create a new blueprint module in `app/` and register it in `create_app()`.

> [!NOTE]
> Deployment: `python run.py` / `flask run` start Flask's development server, which isn't meant for production. In production, run the app under a WSGI server such as gunicorn (`gunicorn "app:create_app()" -b 0.0.0.0:8001`) once it's added as a dependency.
