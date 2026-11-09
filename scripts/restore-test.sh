#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
    echo "Verwendung: BACKUP_AGE_IDENTITY_FILE=<privater-schluessel> RESTORE_TEST_ACK=I_AM_USING_AN_ISOLATED_TEST_DATABASE bash scripts/restore-test.sh <backup-verzeichnis>" >&2
    exit 2
fi

: "${BACKUP_AGE_IDENTITY_FILE:?BACKUP_AGE_IDENTITY_FILE muss gesetzt sein}"
: "${RESTORE_TEST_ACK:?RESTORE_TEST_ACK muss vor einem Restore-Test ausdrücklich gesetzt werden}"
: "${COMPOSE_PROJECT_NAME:?Für den Restore-Test muss ein eigener Compose-Projektname gesetzt sein}"
if [[ "$RESTORE_TEST_ACK" != "I_AM_USING_AN_ISOLATED_TEST_DATABASE" ]]; then
    echo "RESTORE_TEST_ACK hat nicht den erwarteten Bestätigungswert." >&2
    exit 1
fi
if [[ "$COMPOSE_PROJECT_NAME" != *restore-test* ]]; then
    echo "COMPOSE_PROJECT_NAME muss 'restore-test' enthalten; Restore im Produktionsprojekt wird verweigert." >&2
    exit 1
fi
if [[ ! -r "$BACKUP_AGE_IDENTITY_FILE" ]]; then
    echo "Der age-Schlüssel ist nicht lesbar: $BACKUP_AGE_IDENTITY_FILE" >&2
    exit 1
fi
if [[ ! -s "$1/database.dump.age" || ! -s "$1/documents.tar.age" ]]; then
    echo "Datenbank- oder Dokumentenbackup fehlt oder ist leer: $1" >&2
    exit 1
fi
command -v docker >/dev/null || { echo "docker wurde nicht gefunden." >&2; exit 1; }
command -v age >/dev/null || { echo "age wurde nicht gefunden." >&2; exit 1; }

target_database=securityops_restore_test
db_user=$(docker compose exec -T db sh -ec 'printf "%s" "$POSTGRES_USER"')
source_database=$(docker compose exec -T db sh -ec 'printf "%s" "$POSTGRES_DB"')
if [[ "$source_database" == "$target_database" ]]; then
    echo "Die Quelldatenbank darf nicht die festgelegte Restore-Testdatenbank sein." >&2
    exit 1
fi
if [[ "$source_database" != *_test ]]; then
    echo "POSTGRES_DB muss für einen isolierten Restore-Test auf '_test' enden." >&2
    exit 1
fi

docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$db_user" -d postgres \
    -c "CREATE DATABASE $target_database"
age --decrypt --identity "$BACKUP_AGE_IDENTITY_FILE" "$1/database.dump.age" \
    | docker compose exec -T db pg_restore --exit-on-error --no-owner --no-acl \
        -U "$db_user" -d "$target_database"
POSTGRES_DB=$target_database docker compose --profile release run --rm provision-db
POSTGRES_DB=$target_database docker compose --profile release run --rm --no-deps migrate \
    python -m scripts.verify_audit_integrity

docker compose --profile restore-test build --quiet restore-documents >/dev/null
restore_container_id=$(
    docker compose --profile restore-test run --detach --rm --no-deps \
        --entrypoint sh restore-documents -c 'sleep infinity'
)
cleanup_restore_container() {
    status=$?
    trap - EXIT
    if [[ -n "$restore_container_id" ]]; then
        docker stop "$restore_container_id" >/dev/null || status=1
    fi
    exit "$status"
}
trap cleanup_restore_container EXIT

age --decrypt --identity "$BACKUP_AGE_IDENTITY_FILE" "$1/documents.tar.age" \
    | docker exec -i "$restore_container_id" \
        tar -C /var/lib/securityops/documents -tf - >/dev/null
age --decrypt --identity "$BACKUP_AGE_IDENTITY_FILE" "$1/documents.tar.age" \
    | docker exec -i "$restore_container_id" \
        tar -C /var/lib/securityops/documents --no-same-owner -xf -
docker stop "$restore_container_id" >/dev/null
restore_container_id=""

migration=$(docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$db_user" \
    -d "$target_database" -Atc "SELECT version_num FROM alembic_version")
permission_count=$(docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$db_user" \
    -d "$target_database" -Atc "SELECT count(*) FROM permissions")
if [[ -z "$migration" || ! "$permission_count" =~ ^[0-9]+$ || "$permission_count" -lt 1 ]]; then
    echo "Restore-Prüfung fehlgeschlagen: Migration oder Berechtigungsdaten fehlen." >&2
    exit 1
fi

echo "Restore-Test erfolgreich: Migration $migration, $permission_count Berechtigungsdatensätze."
echo "Die Testdatenbank $target_database und das separate Dokumenten-Testvolume bleiben zur Prüfung bestehen."
