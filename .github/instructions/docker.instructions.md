---
applyTo: "docker-compose*.yml,backend/Dockerfile,frontend/Dockerfile,backend/.dockerignore,frontend/.dockerignore"
---

Folge der getrennten Produktionskonfiguration in `docker-compose.yml` und dem lokalen HTTP-Override in `docker-compose.dev.yml`. Geheimnisse ausschließlich über Umgebung/Secret Store bereitstellen und Beispielwerte klar als nicht produktiv behandeln. API und Worker erhalten keine Datenbank-Admin- oder Migrationszugänge; Migrationen laufen als eigener Release-Schritt. Keine unnötigen Ports, privilegierten Container, Runtime-Dependencies oder öffentlichen Dateipfade ergänzen. Compose-Konfiguration und beide Images gemäß CI prüfen.
