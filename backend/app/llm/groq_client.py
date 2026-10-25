from groq import Groq

from app.core.config import get_settings

def get_groq_client() -> Groq:
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    return Groq(api_key=settings.groq_api_key)
    
