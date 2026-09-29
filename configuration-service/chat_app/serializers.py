from rest_framework import serializers

from .llm import CHAT_PROMPT_MAX_LENGTH, OLLAMA_MODEL, OLLAMA_OPTIONS


class ChatRequestSerializer(serializers.Serializer):
    # trim_whitespace + allow_blank=False rejects empty and whitespace-only prompts.
    prompt = serializers.CharField(
        max_length=CHAT_PROMPT_MAX_LENGTH,
        help_text=f'Your message to the assistant (max {CHAT_PROMPT_MAX_LENGTH} characters).',
    )


class ChatResponseSerializer(serializers.Serializer):
    reply = serializers.CharField(help_text="The model's answer.")
    model = serializers.CharField(help_text=f'The Ollama model used, e.g. `{OLLAMA_MODEL}`.')
    options = serializers.DictField(
        help_text=f'Sampling hyperparameters sent to Ollama (hardcoded): `{OLLAMA_OPTIONS}`.',
    )
