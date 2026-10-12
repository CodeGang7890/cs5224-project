"""The chat flow, moved here from configuration-service's chat_app (the user asked): the parts that
need the LLM. Each module is a copy of its chat_app namesake with Django replaced by SQLAlchemy
(app/models.py); configuration-service keeps its own copy for now, so keep the two in step until
it's removed there. Everything else about chats (listing them, sandbox sessions, the settings,
answering questions) stays in configuration-service.
"""
