"""Modules the permissions response says this subscription can see."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


class CatalogError(ValueError):
    """The permissions document is not the shape this client reads."""


@dataclass(frozen=True)
class LicensedModule:
    resource_id: str
    name: str
    description: str
    type_code: str
    version: str


def resource_id(value: str) -> str:
    if not value.isdigit():
        raise CatalogError("a resource id is decimal digits")
    return value


def parse_permissions(payload: Mapping[str, object]) -> list[LicensedModule]:
    """Read resourceVersions. The account id on the permission object is not kept."""
    versions = payload.get("resourceVersions")
    if not isinstance(versions, list):
        raise CatalogError("resourceVersions is missing")
    modules: list[LicensedModule] = []
    for item in versions:
        if not isinstance(item, Mapping):
            raise CatalogError("a resource version is not an object")
        modules.append(
            LicensedModule(
                resource_id=_text(item, "cdlResourceId"),
                name=_text(item, "cdlResourceName"),
                description=_text(item, "cdlResourceDescription"),
                type_code=_text(item, "cdlResourceTypeCode"),
                version=_text(item, "versionNumber"),
            )
        )
    return modules


def _text(item: Mapping[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{key} is missing")
    return value
