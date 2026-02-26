from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    lm_studio_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = "local-model"
    max_history_tokens: int = 2000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]
    tools_enabled: bool = True
    tool_call_max_iterations: int = 3

    class Config:
        env_file = ".env"


settings = Settings()
