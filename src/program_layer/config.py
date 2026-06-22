import os

from dotenv import load_dotenv

load_dotenv()

PARSER_AGENT_MODEL: str = os.getenv("PARSER_AGENT_MODEL", "claude-sonnet-4-6")
PMO_AGENT_MODEL: str = os.getenv("PMO_AGENT_MODEL", "claude-sonnet-4-6")
CONTRACT_GATE_MODEL: str = os.getenv("CONTRACT_GATE_MODEL", "claude-sonnet-4-6")
PM_AGENT_MODEL: str = os.getenv("PM_AGENT_MODEL", "claude-sonnet-4-6")
FALLBACK_MODEL: str = os.getenv("FALLBACK_MODEL", "gpt-4o")

CHECKPOINT_DB_PATH: str = os.getenv("CHECKPOINT_DB_PATH", "./checkpoints.db")
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))

LANGSMITH_TRACING: bool = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "agile-agent-program")
