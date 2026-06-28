"""
Customer configuration loader.
Each handyman gets their own config dir with:
- config.yaml (company info, preferences)
- price_table.yaml (their service prices)
"""

import os
import yaml
from pathlib import Path

AGENT_DIR = Path(__file__).parent
CUSTOMERS_DIR = AGENT_DIR / "customers"


def list_customers() -> list[str]:
    """List all configured customer names."""
    if not CUSTOMERS_DIR.exists():
        return []
    return sorted(
        d.name for d in CUSTOMERS_DIR.iterdir()
        if d.is_dir() and (d / "config.yaml").exists()
    )


def load_config(customer_name: str) -> dict:
    """Load a customer's company configuration."""
    path = CUSTOMERS_DIR / customer_name / "config.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Customer '{customer_name}' not found at {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def load_price_table(customer_name: str) -> dict:
    """Load a customer's price table."""
    path = CUSTOMERS_DIR / customer_name / "price_table.yaml"
    if not path.exists():
        return {"standard_services": [], "hourly_rate": 0.0}
    with open(path) as f:
        return yaml.safe_load(f)


def get_customer_dir(customer_name: str) -> Path:
    """Get the customer's data directory."""
    return CUSTOMERS_DIR / customer_name