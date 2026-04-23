"""ApplyPilot configuration: paths, platform detection, user data."""

import os
from pathlib import Path

# User data directory — all user-specific files live here
APP_DIR = Path(os.environ.get("APPLYPILOT_DIR", Path.home() / ".applypilot"))

# Core paths
DB_PATH = APP_DIR / "applypilot.db"
PROFILE_PATH = APP_DIR / "profile.json"
RESUME_PATH = APP_DIR / "resume.txt"
RESUME_PDF_PATH = APP_DIR / "resume.pdf"
SEARCH_CONFIG_PATH = APP_DIR / "searches.yaml"
ENV_PATH = APP_DIR / ".env"

# Generated output
TAILORED_DIR = APP_DIR / "tailored_resumes"
COVER_LETTER_DIR = APP_DIR / "cover_letters"
LOG_DIR = APP_DIR / "logs"

# Package-shipped config (YAML registries)
PACKAGE_DIR = Path(__file__).parent
CONFIG_DIR = PACKAGE_DIR / "config"


def ensure_dirs():
    """Create all required directories."""
    for d in [APP_DIR, TAILORED_DIR, COVER_LETTER_DIR, LOG_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_profile(user_id: int | None = None) -> dict:
    """Load user profile. If user_id is given, reads from users.profile_json in DB."""
    import json
    if user_id is not None:
        from applypilot.database import get_connection
        conn = get_connection()
        row = conn.execute("SELECT profile_json FROM users WHERE id = ?", (user_id,)).fetchone()
        if row and row[0]:
            return json.loads(row[0])
        # Fall through to filesystem if no DB profile yet
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(
            f"Profile not found at {PROFILE_PATH}. Run `applypilot init` first."
        )
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def load_search_config(user_id: int | None = None) -> dict:
    """Load search config. If user_id is given, reads from users.searches_json in DB."""
    import yaml, json
    if user_id is not None:
        from applypilot.database import get_connection
        conn = get_connection()
        row = conn.execute("SELECT searches_json FROM users WHERE id = ?", (user_id,)).fetchone()
        if row and row[0]:
            return json.loads(row[0])
    if not SEARCH_CONFIG_PATH.exists():
        example = CONFIG_DIR / "searches.example.yaml"
        if example.exists():
            return yaml.safe_load(example.read_text(encoding="utf-8"))
        return {}
    return yaml.safe_load(SEARCH_CONFIG_PATH.read_text(encoding="utf-8"))


def get_resume_text(user_id: int | None = None) -> str:
    """Load resume text. If user_id is given, reads from users.resume_text in DB."""
    if user_id is not None:
        from applypilot.database import get_connection
        conn = get_connection()
        row = conn.execute("SELECT resume_text FROM users WHERE id = ?", (user_id,)).fetchone()
        if row and row[0]:
            return row[0]
    if RESUME_PATH.exists():
        return RESUME_PATH.read_text(encoding="utf-8")
    return ""


def load_sites_config() -> dict:
    """Load sites.yaml configuration (sites list, manual_ats, blocked, etc.)."""
    import yaml
    path = CONFIG_DIR / "sites.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def is_manual_ats(url: str | None) -> bool:
    """Check if a URL routes through an ATS that requires manual application."""
    if not url:
        return False
    sites_cfg = load_sites_config()
    domains = sites_cfg.get("manual_ats", [])
    url_lower = url.lower()
    return any(domain in url_lower for domain in domains)


def load_blocked_sites() -> tuple[set[str], list[str]]:
    """Load blocked sites and URL patterns from sites.yaml.

    Returns:
        (blocked_site_names, blocked_url_patterns)
    """
    cfg = load_sites_config()
    blocked = cfg.get("blocked", {})
    sites = set(blocked.get("sites", []))
    patterns = blocked.get("url_patterns", [])
    return sites, patterns


def load_blocked_sso() -> list[str]:
    """Load blocked SSO domains from sites.yaml."""
    cfg = load_sites_config()
    return cfg.get("blocked_sso", [])


def load_base_urls() -> dict[str, str | None]:
    """Load site base URLs for URL resolution from sites.yaml."""
    cfg = load_sites_config()
    return cfg.get("base_urls", {})


# ---------------------------------------------------------------------------
# Default values — referenced across modules instead of magic numbers
# ---------------------------------------------------------------------------

DEFAULTS = {
    "min_score": 7,
    "max_tailor_attempts": 5,
    "poll_interval": 60,
}


def load_env():
    """Load environment variables from ~/.applypilot/.env and project-root .env."""
    from dotenv import load_dotenv
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    # Walk up from this file's location to find a repo-root .env
    # (handles running `uvicorn` from backend/ or any subdirectory)
    search = Path(__file__).resolve()
    for parent in [search, *search.parents]:
        candidate = parent / ".env"
        if candidate.exists():
            load_dotenv(candidate)
            break
    # Final fallback: CWD
    load_dotenv()


# ---------------------------------------------------------------------------
# Tier system — feature gating by installed dependencies
# ---------------------------------------------------------------------------

TIER_LABELS = {
    1: "Discovery",
    2: "AI Scoring & Tailoring",
}

TIER_COMMANDS: dict[int, list[str]] = {
    1: ["init", "run discover", "run enrich", "status"],
    2: ["run score", "run tailor", "run cover", "run pdf", "run"],
}


def get_tier() -> int:
    """Detect the current tier based on available dependencies.

    Tier 1 (Discovery):               Python + pip
    Tier 2 (AI Scoring & Tailoring):  + LLM API key
    """
    load_env()

    has_llm = any(os.environ.get(k) for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL"))
    return 2 if has_llm else 1


def check_tier(required: int, feature: str) -> None:
    """Raise SystemExit with a clear message if the current tier is too low."""
    current = get_tier()
    if current >= required:
        return

    from rich.console import Console
    _console = Console(stderr=True)

    missing: list[str] = []
    if required >= 2 and not any(os.environ.get(k) for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL")):
        missing.append("LLM API key — run [bold]applypilot init[/bold] or set GEMINI_API_KEY")

    _console.print(
        f"\n[red]'{feature}' requires {TIER_LABELS.get(required, f'Tier {required}')} (Tier {required}).[/red]\n"
        f"Current tier: {TIER_LABELS.get(current, f'Tier {current}')} (Tier {current})."
    )
    if missing:
        _console.print("\n[yellow]Missing:[/yellow]")
        for m in missing:
            _console.print(f"  - {m}")
    _console.print()
    raise SystemExit(1)
