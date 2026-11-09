import ast
import re
import sys
import tomllib
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
DOCUMENTATION_FILES = ("docs/PROJECT_STATUS.md", "docs/IMPLEMENTATION_ROADMAP.md")
TEST_COMMANDS = (
    "python -m pytest -q",
    "ruff check app tests migrations scripts",
    "ruff format --check app tests migrations scripts",
    "npm run build",
    "npm test",
)


def registered_api_modules(main_path: Path) -> list[str]:
    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    router_imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not node.module.startswith("app."):
            continue
        for alias in node.names:
            if alias.name == "router":
                router_imports[alias.asname or alias.name] = node.module.removeprefix("app.")

    registered: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not (
            isinstance(function, ast.Attribute)
            and function.attr == "include_router"
            and isinstance(function.value, ast.Name)
            and function.value.id == "app"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            continue
        module = router_imports.get(node.args[0].id)
        if module:
            registered.add(module)
    return sorted(registered)


def validate_documentation_facts(
    *,
    status_text: str,
    roadmap_text: str,
    ci_text: str,
    requires_python: str,
    python_version: str,
    node_version: str,
    postgres_version: str,
    alembic_head: str,
    migration_count: int,
    api_modules: list[str],
) -> list[str]:
    errors: list[str] = []
    for name, text in (
        ("PROJECT_STATUS.md", status_text),
        ("IMPLEMENTATION_ROADMAP.md", roadmap_text),
    ):
        if f"**Alembic-Head:** `{alembic_head}`" not in text:
            errors.append(
                f"{name}: dokumentierter Alembic-Head stimmt nicht mit {alembic_head} überein"
            )
        if f"**Alembic-Migrationen:** {migration_count}" not in text:
            errors.append(
                f"{name}: dokumentierte Migrationsanzahl stimmt nicht mit {migration_count} überein"
            )
        if re.search(r"\b[0-9a-f]{40}\b", text, re.IGNORECASE):
            errors.append(
                f"{name}: aktuelle Momentaufnahme darf keinen festen Commit-SHA enthalten"
            )

    module_match = re.search(r"\*\*Registrierte API-Router:\*\* `([^`]+)`", status_text)
    expected_modules = ", ".join(api_modules)
    if not module_match or module_match.group(1) != expected_modules:
        errors.append(
            "PROJECT_STATUS.md: Routerinventar stimmt nicht mit den Registrierungen in app/main.py überein"
        )

    for command in TEST_COMMANDS:
        if command not in status_text:
            errors.append(f"PROJECT_STATUS.md: CI-Befehl fehlt in der Dokumentation: {command}")
        if command not in ci_text:
            errors.append(f"CI-Workflow führt den dokumentierten Befehl nicht aus: {command}")

    python_requirement = re.search(r">=\s*(\d+\.\d+)", requires_python)
    if not python_requirement:
        errors.append(
            "backend/pyproject.toml: requires-python muss eine Mindestversion >= X.Y angeben"
        )
    elif (
        f"Python `{requires_python}` (CI: {python_version})" not in status_text
        or python_requirement.group(1) != python_version
    ):
        errors.append(
            "PROJECT_STATUS.md: Python-Voraussetzung stimmt nicht mit pyproject.toml und CI überein"
        )

    for phrase, description in (
        (f"PostgreSQL {postgres_version} (CI)", "PostgreSQL"),
        (f"Node.js {node_version} (CI)", "Node.js"),
    ):
        if phrase not in status_text:
            errors.append(
                f"PROJECT_STATUS.md: technische CI-Voraussetzung {description} stimmt nicht überein"
            )
    return errors


def validate_project_status() -> list[str]:
    status_text = (REPOSITORY_ROOT / DOCUMENTATION_FILES[0]).read_text(encoding="utf-8")
    roadmap_text = (REPOSITORY_ROOT / DOCUMENTATION_FILES[1]).read_text(encoding="utf-8")
    ci_text = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    project = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    backend_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    backend_config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    migrations = ScriptDirectory.from_config(backend_config)
    heads = migrations.get_heads()
    if len(heads) != 1:
        return [f"Alembic-Migrationsgraph muss genau einen Head haben; gefunden: {heads}"]

    revisions = list(migrations.walk_revisions())
    migration_files = [
        path
        for path in (BACKEND_ROOT / "migrations/versions").glob("*.py")
        if path.name != "__init__.py"
    ]
    errors = []
    if len(migration_files) != len(revisions):
        errors.append(
            "Anzahl der Migrationsdateien stimmt nicht mit den Revisionen im Alembic-Graphen überein"
        )

    workflow_python = re.search(r'python-version:\s*"([^"]+)"', ci_text)
    workflow_node = re.search(r'node-version:\s*"([^"]+)"', ci_text)
    workflow_postgres = re.search(r"image:\s*postgres:(\d+)", ci_text)
    if not workflow_python or not workflow_node or not workflow_postgres:
        return errors + [
            "CI-Workflow: Python-, Node.js- oder PostgreSQL-Version konnte nicht gelesen werden"
        ]

    return errors + validate_documentation_facts(
        status_text=status_text,
        roadmap_text=roadmap_text,
        ci_text=ci_text,
        requires_python=project["project"]["requires-python"],
        python_version=workflow_python.group(1),
        node_version=workflow_node.group(1),
        postgres_version=workflow_postgres.group(1),
        alembic_head=heads[0],
        migration_count=len(revisions),
        api_modules=registered_api_modules(BACKEND_ROOT / "app/main.py"),
    )


def main() -> int:
    errors = validate_project_status()
    if errors:
        print("Projektstatus-Prüfung fehlgeschlagen:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Projektstatus-Dokumentation stimmt mit Migrationsgraph, Routern und CI überein.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
