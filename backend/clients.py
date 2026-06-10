from groq import Groq
from config import config

groq_client = Groq(api_key=config.GROQ_API_KEY)