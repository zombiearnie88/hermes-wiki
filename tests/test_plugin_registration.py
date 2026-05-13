from __future__ import annotations

import importlib.util
import sys
import types
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
        "get_document_structure",
        "get_page_content",
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
    wiki_init_command = next(command for command in ctx.commands if command["name"] == "wiki-init")
    assert "--domain DOMAIN" in wiki_init_command["args_hint"]
    wiki_add_command = next(command for command in ctx.commands if command["name"] == "wiki-add")
    assert wiki_add_command["args_hint"] == "<path> [--workspace DIR] [--model MODEL] [--provider PROVIDER] [--language LANG]"
    assert len(ctx.cli_commands) == 1
    assert ctx.cli_commands[0]["name"] == "wiki"
    assert len(ctx.skills) == 1
    assert ctx.skills[0]["name"] == "wiki-operator"
    assert ctx.skills[0]["path"].name == "SKILL.md"
    assert ctx.skills[0]["path"].exists()
    assert "domain" in schemas.WIKI_INIT["parameters"]["properties"]
    assert "translate the answer to concise English" in schemas.WIKI_INIT["description"]
    assert "written into wiki/SCHEMA.md exactly as provided" in schemas.WIKI_INIT["parameters"]["properties"]["domain"]["description"]
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


def test_plugin_loads_under_hermes_directory_module_name() -> None:
    module_name = "hermes_plugins.hermes_wiki"

    def is_target_module(name: str) -> bool:
        return (
            name == "hermes_wiki"
            or name.startswith("hermes_wiki.")
            or name == "hermes_plugins"
            or name.startswith("hermes_plugins.")
        )

    class BlockTopLevelHermesWiki:
        def find_spec(self, fullname, path=None, target=None):
            del path, target
            if fullname == "hermes_wiki" or fullname.startswith("hermes_wiki."):
                raise ModuleNotFoundError("blocked top-level hermes_wiki import")
            return None

    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if is_target_module(name)
    }
    for name in saved_modules:
        sys.modules.pop(name, None)

    parent = types.ModuleType("hermes_plugins")
    parent.__path__ = []
    blocker = BlockTopLevelHermesWiki()

    sys.modules["hermes_plugins"] = parent
    sys.meta_path.insert(0, blocker)
    try:
        spec = importlib.util.spec_from_file_location(
            module_name,
            PLUGIN_DIR / "__init__.py",
            submodule_search_locations=[str(PLUGIN_DIR)],
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        ctx = FakeContext()
        module.register(ctx)

        assert [tool["name"] for tool in ctx.tools] == [
            "wiki_init",
            "wiki_add",
            "wiki_status",
            "wiki_config",
            "wiki_list",
            "wiki_deps",
            "get_document_structure",
            "get_page_content",
        ]
    finally:
        sys.meta_path.remove(blocker)
        for name in list(sys.modules):
            if is_target_module(name):
                sys.modules.pop(name, None)
        sys.modules.update(saved_modules)


def test_docker_compose_mounts_plugin_directory_directly() -> None:
    compose_text = (ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")

    assert "- ../hermes_wiki:/opt/data/profiles/clinic/plugins/hermes-wiki:ro" in compose_text
    assert "- ../hermes_wiki:/home/hermeswebui/.hermes/plugins/hermes-wiki" in compose_text
    assert "uv pip install --python /opt/hermes/.venv/bin/python -r /opt/data/profiles/clinic/plugins/hermes-wiki/requirements.txt" in compose_text
    assert "uv pip install --python /app/venv/bin/python3 -r /home/hermeswebui/.hermes/plugins/hermes-wiki/requirements.txt" in compose_text
    assert "- ..:/opt/hermes-wiki:ro" not in compose_text
    assert "cp /opt/hermes-wiki" not in compose_text


def test_wiki_operator_skill_tells_agent_to_translate_domain_to_english() -> None:
    skill_text = (PLUGIN_DIR / "skills" / "wiki-operator" / "SKILL.md").read_text(encoding="utf-8")

    assert "translate the domain to concise English before initialization" in skill_text
    assert "init writes that value into `wiki/SCHEMA.md`" in skill_text
