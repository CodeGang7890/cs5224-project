"""Two-stage Gemini example for the Ansera workflow.

Install the SDK with: python -m pip install google-genai

For local development, authenticate with Application Default Credentials:
  gcloud auth application-default login
  $env:GOOGLE_CLOUD_PROJECT = "cs5224-ansera"
  $env:GOOGLE_CLOUD_LOCATION = "us-central1"
  $env:GOOGLE_GENAI_USE_VERTEXAI = "True"

In Cloud Run, use an attached runtime service account with roles/aiplatform.user;
do not put a service-account key or API key in the application.
This example proposes a business action only. The application must validate,
authorize, and execute any action itself.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from google import genai
from google.genai.types import GenerateContentConfig


INTENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "intent": {"type": "STRING"},
        "summary": {"type": "STRING"},
        "extracted_facts": {"type": "ARRAY", "items": {"type": "STRING"}},
        "missing_information": {"type": "ARRAY", "items": {"type": "STRING"}},
        "confidence": {"type": "NUMBER"},
        "needs_human": {"type": "BOOLEAN"},
    },
    "required": [
        "intent",
        "summary",
        "extracted_facts",
        "missing_information",
        "confidence",
        "needs_human",
    ],
}

ACTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "action": {
            "type": "STRING",
            "enum": ["reply", "create_task", "update_record", "handoff", "no_action"],
        },
        "reason": {"type": "STRING"},
        "reply_to_customer": {"type": "STRING"},
        "required_inputs": {"type": "ARRAY", "items": {"type": "STRING"}},
        "requires_human_approval": {"type": "BOOLEAN"},
    },
    "required": [
        "action",
        "reason",
        "reply_to_customer",
        "required_inputs",
        "requires_human_approval",
    ],
}


def generate_json(
    client: genai.Client,
    model: str,
    instruction: str,
    prompt: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Ask Gemini for schema-constrained JSON and parse its text response."""
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=GenerateContentConfig(
            system_instruction=instruction,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.1,
        ),
    )
    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")
    try:
        result = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini response was not valid JSON.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Gemini response must be a JSON object.")
    return result


def handle_message(
    client: genai.Client,
    model: str,
    customer_message: str,
    workflow_rules: str,
) -> dict[str, Any]:
    """Interpret a customer message, then map it to a configured workflow."""
    intent = generate_json(
        client=client,
        model=model,
        instruction=(
            "You are the first stage of a business support workflow. Interpret the customer message. "
            "Extract only facts supported by the message; do not invent missing details. "
            "Flag ambiguity or sensitive cases for a human. Return only the requested JSON."
        ),
        prompt=f"Customer message:\n{customer_message}",
        schema=INTENT_SCHEMA,
    )

    action = generate_json(
        client=client,
        model=model,
        instruction=(
            "You are the second stage of a business support workflow. Map the interpreted request "
            "to the business rules provided below. Propose one action only. Do not claim that an "
            "action was executed, do not invent a policy, and require human approval when rules "
            "are unclear or the first stage flagged the case for a human. Return only the requested JSON."
        ),
        prompt=(
            f"Business workflow rules:\n{workflow_rules}\n\n"
            f"Interpreted customer request:\n{json.dumps(intent, ensure_ascii=False)}"
        ),
        schema=ACTION_SCHEMA,
    )
    return {"interpretation": intent, "proposed_action": action}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", help="Customer message to process")
    parser.add_argument(
        "--rules",
        default="If the request is unclear, hand it to a human. Do not issue refunds automatically.",
        help="Business workflow rules to give the second model call",
    )
    args = parser.parse_args()

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise SystemExit("Set GOOGLE_CLOUD_PROJECT to your Google Cloud project ID.")

    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
    client = genai.Client(vertexai=True, project=project, location=location)
    result = handle_message(client, model, args.message, args.rules)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
