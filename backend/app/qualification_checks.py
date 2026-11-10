from collections.abc import Sequence
from datetime import date

from app.models import EmployeeQualification


def missing_qualification_requirements(
    *,
    shift_requirement: str | None,
    object_requirements: Sequence[str],
    qualifications: Sequence[EmployeeQualification],
    starts_on: date,
    ends_on: date,
) -> list[tuple[str, str]]:
    requirements: dict[str, tuple[str, str]] = {}
    if shift_requirement:
        requirements[shift_requirement.lower()] = (shift_requirement, "qualification_missing")
    for requirement in object_requirements:
        requirements.setdefault(
            requirement.lower(),
            (requirement, "object_qualification_missing"),
        )

    valid_names: set[str] = set()
    for qualification in qualifications:
        if qualification.archived_at is not None:
            continue
        if qualification.valid_from is not None and qualification.valid_from > starts_on:
            continue
        if qualification.expires_on is not None and qualification.expires_on < ends_on:
            continue
        valid_names.add(qualification.name.lower())
        valid_names.add(qualification.category.lower())

    return [requirement for key, requirement in requirements.items() if key not in valid_names]
