"""Small Cloud Run web app demonstrating a two-stage Vertex AI workflow."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

from flask import Flask, jsonify, render_template, request
from google import genai
from google.genai.types import GenerateContentConfig


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 2_000
MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

INTENT_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "intent": {"type": "STRING"},
        "summary": {"type": "STRING"},
        "facts": {"type": "ARRAY", "items": {"type": "STRING"}},
        "needs_human_review": {"type": "BOOLEAN"},
    },
    "required": ["intent", "summary", "facts", "needs_human_review"],
}

WORKFLOW_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "customer_reply": {"type": "STRING"},
        "suggested_action": {
            "type": "STRING",
            "enum": ["reply", "create_task", "update_record", "handoff", "no_action"],
        },
        "reason": {"type": "STRING"},
        "requires_human_approval": {"type": "BOOLEAN"},
    },
    "required": [
        "customer_reply",
        "suggested_action",
        "reason",
        "requires_human_approval",
    ],
}

DEFAULT_BUSINESS_RULES = (
    "Answer common questions clearly. If the request is unclear, hand it to a human. "
    "Do not promise refunds, discounts, or completed actions."
)


@lru_cache(maxsize=1)
def get_vertex_client() -> genai.Client:
    """Use Cloud Run's attached service account through Application Default Credentials."""
    if not PROJECT_ID:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is not configured.")
    return genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


def generate_json(instruction: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    response = get_vertex_client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config=GenerateContentConfig(
            system_instruction=instruction,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
            max_output_tokens=512,
        ),
    )
    if not response.text:
        raise RuntimeError("Vertex AI returned an empty response.")
    result = json.loads(response.text)
    if not isinstance(result, dict):
        raise RuntimeError("Vertex AI returned an unexpected response format.")
    return result


def run_workflow(message: str, business_rules: str) -> dict[str, Any]:
    """Understand a customer request, then propose a rule-based next action."""
    interpretation = generate_json(
        instruction=(
            "Interpret a customer's message for a small business. Extract only stated facts. "
            "Flag ambiguity or sensitive requests for human review. Do not answer the customer yet."
        ),
        prompt=f"Customer message:\n{message}",
        schema=INTENT_SCHEMA,
    )
    workflow = generate_json(
        instruction=(
            "Use the business rules to propose one next step and draft a customer reply. "
            "Do not claim an action was executed. Do not invent policies. Require human approval "
            "if the interpretation needs human review or the rules do not clearly cover the request."
        ),
        prompt=(
            f"Business rules:\n{business_rules}\n\n"
            f"Interpreted request:\n{json.dumps(interpretation, ensure_ascii=False)}"
        ),
        schema=WORKFLOW_SCHEMA,
    )
    return {"interpretation": interpretation, "workflow": workflow}


@app.get("/")
def index():
    return render_template("index.html", default_rules=DEFAULT_BUSINESS_RULES)


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Send a JSON object with a message."), 400

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify(error="Enter a message first."), 400
    message = message.strip()
    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify(error=f"Messages must be {MAX_MESSAGE_LENGTH} characters or fewer."), 413

    rules = payload.get("business_rules", DEFAULT_BUSINESS_RULES)
    if not isinstance(rules, str) or not rules.strip():
        rules = DEFAULT_BUSINESS_RULES
    rules = rules.strip()[:MAX_MESSAGE_LENGTH]

    try:
        return jsonify(run_workflow(message, rules))
    except Exception:
        logger.exception("Vertex AI workflow request failed")
        return jsonify(error="The AI request failed. Check the service logs and try again."), 502


if __name__ == "__main__":
    # Local development only. Cloud Run starts the app with Gunicorn in the Dockerfile.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=False)
