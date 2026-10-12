"""Django's ValidationError, for the validators copied from configuration-service."""


class ValidationError(Exception):
    """A value breaks the rules; `messages` lists every problem (like Django's ValidationError)."""

    def __init__(self, message):
        self.messages = list(message) if isinstance(message, list) else [message]
        super().__init__('; '.join(str(m) for m in self.messages))
