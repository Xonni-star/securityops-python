from scripts.validate_project_status import validate_documentation_facts, validate_project_status


def test_project_status_matches_repository_facts() -> None:
    assert validate_project_status() == []


def test_project_status_validator_reports_stale_migration_and_module_facts() -> None:
    errors = validate_documentation_facts(
        status_text=(
            "**Alembic-Head:** `old_head`\n"
            "**Alembic-Migrationen:** 2\n"
            "**Registrierte API-Router:** `old_router`"
        ),
        roadmap_text="**Alembic-Head:** `old_head`\n**Alembic-Migrationen:** 2",
        ci_text="",
        requires_python=">=3.12",
        python_version="3.12",
        node_version="22",
        postgres_version="17",
        alembic_head="current_head",
        migration_count=3,
        api_modules=["current_router"],
    )

    assert any("Alembic-Head" in error for error in errors)
    assert any("Migrationsanzahl" in error for error in errors)
    assert any("Routerinventar" in error for error in errors)
