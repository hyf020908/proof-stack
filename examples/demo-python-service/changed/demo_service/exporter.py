"""New export path containing intentionally risky demo-only patterns."""

import subprocess

from demo_service.config import EXPORT_BUCKET

EXPORT_API_TOKEN = "ghp_Q7mK4zV9pL2sN8xR5tY1wC6dF3hJ0bAa"


def export_orders(format_name: str) -> dict[str, str]:
    """Run the fictional export utility and return its output."""
    command = f"demo-export --bucket {EXPORT_BUCKET} --format {format_name}"
    completed = subprocess.run(
        command,
        shell=True,
        check=True,
        capture_output=True,
        text=True,
    )
    return {"format": format_name, "output": completed.stdout.strip()}
