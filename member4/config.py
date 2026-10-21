from pydantic_settings import BaseSettings
from pydantic import Field
import os

class Settings(BaseSettings):
    neo4j_uri: str = Field(default="bolt://localhost:7687", validation_alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", validation_alias="NEO4J_USERNAME")
    neo4j_password: str = Field(default="password", validation_alias="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="neo4j", validation_alias="NEO4J_DATABASE")
    server_host: str = Field(default="127.0.0.1", validation_alias="SERVER_HOST")
    server_port: int = Field(default=8000, validation_alias="SERVER_PORT")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
