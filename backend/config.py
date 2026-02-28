from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    lm_studio_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = "local-model"
    ollama_url: str = "http://localhost:11434/v1"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    max_history_tokens: int = 2000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]
    tools_enabled: bool = True
    tool_call_max_iterations: int = 8

    class Config:
        env_file = ".env"


settings = Settings()
