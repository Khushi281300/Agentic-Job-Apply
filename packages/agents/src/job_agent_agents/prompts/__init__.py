"""Prompt template engine - separates prompt logic from agent logic.

Uses Jinja2 templates so prompts can be modified without touching code.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape([]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template_name: str, **kwargs) -> str:
    """Render a prompt template with the given variables."""
    template = _env.get_template(template_name)
    return template.render(**kwargs)
