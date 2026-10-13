"""The chat flow, moved here from configuration-service's chat_app (the user asked): the parts that
need the LLM. Each module started as its chat_app namesake with Django replaced by SQLAlchemy
(app/models.py); they have been removed from configuration-service, so this is the only copy.
Everything else about chats (listing them, sandbox sessions, the settings,
answering questions) stays in configuration-service.
"""
