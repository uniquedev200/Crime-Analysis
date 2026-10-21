import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # App
    app_name: str = "ATLAS Crime Intelligence Backend"
    environment: str = os.getenv("ENVIRONMENT", "development")
    secret_key: str = os.getenv("SECRET_KEY", "atlas_super_secret_jwt_key_2026_sih_hackathon")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Supabase Database
    supabase_password: str = os.getenv("SUPABASE_PASSWORD", "")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./atlas_fallback.db"
    )

    # Upstash Vector
    upstash_url: str = os.getenv("UPSTASH_URL", "")
    upstash_token: str = os.getenv("UPSTASH_TOKEN", "")

    # Local Ollama
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

    # Neo4j Settings (Member 4 - Knowledge Graph)
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "password")
    neo4j_database: str = os.getenv("NEO4J_DATABASE", "neo4j")

    # Groq & Member 3 Document Extraction LLM Settings
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
    atlas_synthetic_only: str = os.getenv("ATLAS_SYNTHETIC_ONLY", "false")
    atlas_require_tesseract: str = os.getenv("ATLAS_REQUIRE_TESSERACT", "false")
    seed_sample_data: bool = os.getenv("SEED_SAMPLE_DATA", "false").lower() in ("true", "1", "yes")

    # Storage paths
    data_dir: Path = BASE_DIR / "data"
    uploads_dir: Path = BASE_DIR / "data" / "uploads"
    originals_dir: Path = BASE_DIR / "data" / "originals"
    outputs_dir: Path = BASE_DIR / "outputs"
    frontend_dist_dir: Path = BASE_DIR / "member1" / "dist"

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

# Ensure directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
settings.originals_dir.mkdir(parents=True, exist_ok=True)
settings.outputs_dir.mkdir(parents=True, exist_ok=True)

# Propagate settings to process environment for imported submodules (e.g. member3 doc module, member4 graph module)
os.environ["GROQ_API_KEY"] = settings.groq_api_key
os.environ["LLM_PROVIDER"] = settings.llm_provider
os.environ["LLM_MODEL"] = settings.llm_model
os.environ["ATLAS_SYNTHETIC_ONLY"] = settings.atlas_synthetic_only
os.environ["ATLAS_REQUIRE_TESSERACT"] = settings.atlas_require_tesseract
