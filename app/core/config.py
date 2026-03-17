from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Claude
    anthropic_api_key: str = ""

    # GitHub
    github_pat: str = ""

    # Azure DevOps
    azure_devops_pat: str = ""
    azure_devops_org: str = ""

    # GitLab
    gitlab_token: str = ""

    # Jira
    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = ""

    # Azure Boards
    azure_boards_org: str = ""
    azure_boards_project: str = ""
    azure_boards_pat: str = ""

    # GitHub Issues
    github_issues_pat: str = ""
    github_issues_repo: str = ""

    # Linear
    linear_api_key: str = ""
    linear_team_id: str = ""

    # JWT / Auth
    jwt_secret_key: str = "change-this-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/reporat"

    # Server
    port: int = 8000
    scan_temp_dir: str = "/tmp/reporat"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
