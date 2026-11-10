from pathlib import Path

import yaml


def test_api_waits_for_clamav_database_ready_healthcheck() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    clamav = compose["services"]["clamav"]
    api = compose["services"]["api"]

    assert api["depends_on"]["clamav"]["condition"] == "service_healthy"
    assert "ports" not in clamav
    assert clamav["healthcheck"]["start_period"] == "30m"
    assert clamav["healthcheck"]["timeout"] == "5s"
    healthcheck = clamav["healthcheck"]["test"]
    assert healthcheck[0] == "CMD-SHELL"
    assert "PING" in healthcheck[1]
    assert "VERSION" in healthcheck[1]
    assert "/[1-9][0-9]*/" in healthcheck[1]


def test_notification_worker_is_a_separate_healthy_service() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    worker = compose["services"]["notification-worker"]

    assert worker["command"] == ["python", "-m", "app.notification_worker", "run"]
    assert worker["depends_on"]["db"]["condition"] == "service_healthy"
    assert worker["healthcheck"]["test"] == [
        "CMD",
        "python",
        "-m",
        "app.notification_worker",
        "health",
    ]
    assert "ports" not in worker
    assert worker["environment"]["NOTIFICATION_WORKER_MAX_ATTEMPTS"] == (
        "${NOTIFICATION_WORKER_MAX_ATTEMPTS:-8}"
    )


def test_production_api_uses_shared_redis_and_explicit_release_migration() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    api = compose["services"]["api"]
    migration = compose["services"]["migrate"]

    assert api["environment"]["RATE_LIMIT_STORAGE_URI"] == (
        "${RATE_LIMIT_STORAGE_URI:-redis://redis:6379/0}"
    )
    assert api["depends_on"]["redis"]["condition"] == "service_healthy"
    assert api["environment"]["SESSION_COOKIE_SECURE"] == "true"
    assert "migrate" not in api["depends_on"]
    assert api.get("command") is None

    assert migration["profiles"] == ["release"]
    assert migration["command"] == ["alembic", "upgrade", "head"]
    assert migration["environment"]["POSTGRES_USER"] == "securityops_migrator"
    assert 'CMD ["uvicorn"' in (root / "backend" / "Dockerfile").read_text(encoding="utf-8")


def test_only_frontend_and_api_publish_loopback_ports() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    published_ports = {
        service_name: service["ports"]
        for service_name, service in compose["services"].items()
        if service.get("ports")
    }

    assert set(published_ports) == {"api", "frontend"}
    assert all(
        port.startswith("127.0.0.1:")
        for service_ports in published_ports.values()
        for port in service_ports
    )
    assert compose["networks"]["data"]["internal"] is True


def test_mfa_encryption_key_is_passed_only_to_api() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    development = yaml.safe_load((root / "docker-compose.dev.yml").read_text(encoding="utf-8"))
    api_environment = compose["services"]["api"]["environment"]
    development_api_environment = development["services"]["api"]["environment"]
    worker_environment = compose["services"]["notification-worker"]["environment"]
    effective_api_environment = {**api_environment, **development_api_environment}

    assert api_environment["MFA_ENCRYPTION_KEY"] == "${MFA_ENCRYPTION_KEY:-}"
    assert "MFA_ENCRYPTION_KEY" not in development_api_environment
    assert effective_api_environment["MFA_ENCRYPTION_KEY"] == "${MFA_ENCRYPTION_KEY:-}"
    assert "MFA_ENCRYPTION_KEY" not in worker_environment


def test_production_frontend_is_static_nginx_with_security_headers() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    frontend = compose["services"]["frontend"]
    dockerfile = (root / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    nginx = (root / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    assert frontend["ports"] == ["127.0.0.1:5173:8080"]
    assert "RUN npm run build" in dockerfile
    assert "FROM nginx:" in dockerfile
    assert "COPY --from=build /app/dist /usr/share/nginx/html" in dockerfile
    assert "USER 101:101" in dockerfile
    assert "listen 8080;" in nginx
    assert "try_files $uri $uri/ /index.html;" in nginx
    for header in (
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Content-Security-Policy",
    ):
        assert f'add_header {header} "' in nginx
