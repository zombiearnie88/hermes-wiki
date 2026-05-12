from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
import shlex
import shutil
import subprocess
import sys


@dataclass(frozen=True)
class DependencyStatus:
    label: str
    module_name: str
    available: bool


@dataclass(frozen=True)
class CapabilityStatus:
    label: str
    ready: bool
    detail: str


@dataclass(frozen=True)
class DependencySpec:
    label: str
    module_name: str
    package_spec: str | None = None
    group: str | None = None


@dataclass(frozen=True)
class DependencyInstallResult:
    group: str
    packages: tuple[str, ...]
    command: str
    exit_code: int
    stdout: str
    stderr: str


_INSTALL_GROUPS = ("core", "pdf", "office", "all")
_DEPENDENCY_SPECS = (
    DependencySpec(label="Hermes runtime", module_name="run_agent"),
    DependencySpec(label="json-repair", module_name="json_repair", package_spec="json-repair", group="core"),
    DependencySpec(label="PyMuPDF", module_name="pymupdf", package_spec="pymupdf", group="pdf"),
    DependencySpec(
        label="MarkItDown",
        module_name="markitdown",
        package_spec="markitdown[all]",
        group="office",
    ),
)


def _probe(module_name: str, label: str) -> DependencyStatus:
    return DependencyStatus(label=label, module_name=module_name, available=find_spec(module_name) is not None)


def runtime_python_path() -> str:
    return sys.executable


def install_groups() -> tuple[str, ...]:
    return _INSTALL_GROUPS


def dependency_specs() -> list[DependencySpec]:
    return list(_DEPENDENCY_SPECS)


def package_specs_for_group(group: str, *, missing_only: bool = False) -> list[str]:
    if group not in _INSTALL_GROUPS:
        raise ValueError(f"Unsupported dependency group: {group}")

    statuses = {entry.module_name: entry.available for entry in dependency_statuses()} if missing_only else {}
    packages: list[str] = []
    for spec in _DEPENDENCY_SPECS:
        if spec.package_spec is None:
            continue
        if group != "all" and spec.group != group:
            continue
        if missing_only and statuses.get(spec.module_name, False):
            continue
        packages.append(spec.package_spec)
    return packages


def package_specs_for_groups(groups: set[str] | list[str] | tuple[str, ...], *, missing_only: bool = False) -> list[str]:
    packages: list[str] = []
    for group in groups:
        for package in package_specs_for_group(group, missing_only=missing_only):
            if package not in packages:
                packages.append(package)
    return packages


def build_uv_install_command_for_packages(package_specs: list[str] | tuple[str, ...]) -> str | None:
    packages = [package for package in package_specs if package]
    if not packages:
        return None
    return shlex.join(["uv", "pip", "install", "--python", runtime_python_path(), *packages])


def build_uv_install_command(group: str = "all", *, missing_only: bool = False) -> str | None:
    return build_uv_install_command_for_packages(package_specs_for_group(group, missing_only=missing_only))


def install_dependency_group(group: str, *, missing_only: bool = True, timeout: int = 600) -> DependencyInstallResult:
    packages = tuple(package_specs_for_group(group, missing_only=missing_only))
    command = build_uv_install_command(group, missing_only=missing_only) or ""
    if not packages:
        return DependencyInstallResult(
            group=group,
            packages=(),
            command=command,
            exit_code=0,
            stdout="",
            stderr="",
        )

    uv_path = shutil.which("uv")
    if uv_path is None:
        raise RuntimeError("uv is not available in PATH for this Hermes runtime.")

    result = subprocess.run(
        [uv_path, "pip", "install", "--python", runtime_python_path(), *packages],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return DependencyInstallResult(
        group=group,
        packages=packages,
        command=command,
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def dependency_statuses() -> list[DependencyStatus]:
    return [_probe(spec.module_name, spec.label) for spec in _DEPENDENCY_SPECS]


def capability_statuses() -> list[CapabilityStatus]:
    deps = {entry.module_name: entry.available for entry in dependency_statuses()}
    hermes_ready = deps.get("run_agent", False)
    json_ready = deps.get("json_repair", False)
    pymupdf_ready = deps.get("pymupdf", False)
    markitdown_ready = deps.get("markitdown", False)

    return [
        CapabilityStatus(label="markdown/text/csv ingest", ready=True, detail="built in"),
        CapabilityStatus(
            label="pdf ingest",
            ready=pymupdf_ready,
            detail="PyMuPDF" if pymupdf_ready else "missing PyMuPDF",
        ),
        CapabilityStatus(
            label="office/html ingest",
            ready=markitdown_ready,
            detail="MarkItDown" if markitdown_ready else "missing MarkItDown",
        ),
        CapabilityStatus(
            label="summary and concept generation",
            ready=hermes_ready and json_ready,
            detail=(
                "Hermes runtime + json-repair"
                if hermes_ready and json_ready
                else "missing Hermes runtime or json-repair"
            ),
        ),
    ]
