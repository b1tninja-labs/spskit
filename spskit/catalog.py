"""Modules the permissions response says this subscription can see."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


class CatalogError(ValueError):
    """The permissions document is not the shape this client reads."""


# The Techline Connect download button always asks for this CDL resource. The file is TLCSuite.
INSTALLER_RESOURCE_ID = "25"


@dataclass(frozen=True)
class LicensedModule:
    resource_id: str
    name: str
    description: str
    type_code: str
    version: str


@dataclass(frozen=True)
class ResourceAccess:
    """One launcher permission. An account id is not part of this."""

    resource_id: str
    runnable: bool


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


def parse_resource_access(payload: Mapping[str, object]) -> list[ResourceAccess]:
    """Read resourcePermissions. userId and the security group are not kept."""
    items = payload.get("resourcePermissions")
    if not isinstance(items, list):
        raise CatalogError("resourcePermissions is missing")
    found: list[ResourceAccess] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise CatalogError("a resource permission is not an object")
        identity = item.get("resourceId")
        runnable = item.get("runnable")
        if not isinstance(identity, str) or not identity.strip():
            raise CatalogError("resourceId is missing")
        if not isinstance(runnable, bool):
            raise CatalogError("runnable is missing")
        found.append(ResourceAccess(identity, runnable))
    return found


def download_ids(access: list[ResourceAccess]) -> list[str]:
    """The installer, then any other decimal resource the account is allowed to run.

    Launcher tabs are UUIDs. Those grant a page, not a file, so they are not downloaded.
    """
    chosen = [INSTALLER_RESOURCE_ID]
    for item in access:
        if item.runnable and item.resource_id.isdigit() and item.resource_id not in chosen:
            chosen.append(item.resource_id)
    return chosen


def _text(item: Mapping[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{key} is missing")
    return value
