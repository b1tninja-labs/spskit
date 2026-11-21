"""The tlc: string the Techline Connect page hands to TLCLauncher.

TLCLauncher strips the ``tlc:,`` prefix and splits the rest on commas. This
module builds that string. It does not start a process and it does not store
the tokens.
"""

from __future__ import annotations

_NA = "NA"


class TlcLaunchError(ValueError):
    """A field would change how TLCLauncher splits the string."""


def browse_launch_url(
    access_token: str,
    refresh_token: str,
    *,
    admin: bool,
    environment: str = "prod",
) -> str:
    """The thirteen launch fields, prefixed with ``tlc:,``.

    ``TLC_LOGIN_AS_ADMIN`` is ``Y`` or ``N``. The session, security, jsession,
    SI auth, TDS rest token, and the three IBM fields are the literal ``NA``.
    """
    _plain("access token", access_token)
    _plain("refresh token", refresh_token)
    _plain("environment", environment)
    admin_flag = "Y" if admin else "N"
    fields = (
        "Y",
        environment,
        _NA,
        _NA,
        _NA,
        _NA,
        admin_flag,
        _NA,
        access_token,
        refresh_token,
        _NA,
        _NA,
        _NA,
    )
    return "tlc:," + ",".join(fields)


def _plain(name: str, value: str) -> None:
    if not isinstance(value, str) or value == "" or any(character.isspace() or character == "," for character in value):
        raise TlcLaunchError(f"the {name} cannot sit in the launch string")
