from __future__ import annotations

from pathlib import Path

from hermes_wiki import register
from hermes_wiki import schemas


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "hermes_wiki"


class FakeContext:
    def __init__(self) -> None:
        self.tools = []
        self.commands = []
        self.cli_commands = []
        self.skills = []

    def register_tool(self, **kwargs) -> None:
        self.tools.append(kwargs)

    def register_command(self, name, **kwargs) -> None:
        self.commands.append({"name": name, **kwargs})

    def register_cli_command(self, **kwargs) -> None:
        self.cli_commands.append(kwargs)

    def register_skill(self, name, path: Path, description: str = "") -> None:
        self.skills.append({"name": name, "path": path, "description": description})


def test_register_wires_tools_commands_and_skills() -> None:
    ctx = FakeContext()

    register(ctx)

    assert [tool["name"] for tool in ctx.tools] == [
        "wiki_init",
        "wiki_add",
        "wiki_status",
        "wiki_config",
        "wiki_list",
        "wiki_deps",
    ]
    assert all(tool["toolset"] == "hermes_wiki" for tool in ctx.tools)
    assert [command["name"] for command in ctx.commands] == [
        "wiki-init",
        "wiki-add",
        "wiki-status",
        "wiki-config",
        "wiki-list",
        "wiki-deps",
    ]
    wiki_add_command = next(command for command in ctx.commands if command["name"] == "wiki-add")
    assert wiki_add_command["args_hint"] == "<path> [--workspace DIR] [--model MODEL] [--provider PROVIDER] [--language LANG]"
    assert len(ctx.cli_commands) == 1
    assert ctx.cli_commands[0]["name"] == "wiki"
    assert len(ctx.skills) == 1
    assert ctx.skills[0]["name"] == "wiki-operator"
    assert ctx.skills[0]["path"].name == "SKILL.md"
    assert ctx.skills[0]["path"].exists()
    assert schemas.WIKI_ADD["parameters"]["required"] == ["path"]
    assert "provider" in schemas.WIKI_CONFIG["parameters"]["properties"]


def test_plugin_directory_is_self_contained() -> None:
    plugin_yaml = (PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8")

    assert "name: hermes-wiki" in plugin_yaml
    assert "provides_tools:" in plugin_yaml
    assert not (ROOT / "plugin.yaml").exists()
    assert not (ROOT / "__init__.py").exists()
    assert (PLUGIN_DIR / "__init__.py").exists()
    assert (PLUGIN_DIR / "schemas.py").exists()
    assert (PLUGIN_DIR / "tools.py").exists()
    assert (PLUGIN_DIR / "requirements.txt").exists()
    assert (PLUGIN_DIR / "skills" / "wiki-operator" / "SKILL.md").exists()


def test_docker_compose_mounts_plugin_directory_directly() -> None:
    compose_text = (ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")

    assert "- ../hermes_wiki:/opt/data/profiles/clinic/plugins/hermes-wiki:ro" in compose_text
    assert "- ../hermes_wiki:/home/hermeswebui/.hermes/plugins/hermes-wiki" in compose_text
    assert "uv pip install --python /opt/hermes/.venv/bin/python -r /opt/data/profiles/clinic/plugins/hermes-wiki/requirements.txt" in compose_text
    assert "- ..:/opt/hermes-wiki:ro" not in compose_text
    assert "cp /opt/hermes-wiki" not in compose_text
