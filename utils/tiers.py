# =============================================================================
# RootForgeKit — Membership Tier Helper
# Free < Paid < Diamond. Tier is set by Nick via direct DB edit for now (no
# payment processor wired up yet — see RevLog 2026-08-13). Server is always
# the source of truth; the desktop client never assigns or upgrades a tier
# itself, only reads what /auth/register, /auth/login, and /auth/verify hand
# it back.
# =============================================================================

TIER_ORDER = {"free": 0, "paid": 1, "diamond": 2}


def tier_at_least(tier: str, minimum: str) -> bool:
    """True if `tier` meets or exceeds `minimum` in Free < Paid < Diamond order."""
    return TIER_ORDER.get(tier, 0) >= TIER_ORDER.get(minimum, 0)


def has_tier_access(display_role: str, tier: str, minimum: str) -> bool:
    """
    True if this session should be treated as meeting `minimum` tier.

    Admins always pass regardless of their stored tier value — being the
    account owner shouldn't depend on remembering to also keep tier=diamond
    in sync. `display_role` is the server-reported role ("admin"/"technician"
    from AuthResult.role / components/auth_dialog.py's server_role), not the
    app-level gating role (which is "technician" for both).
    """
    if display_role == "admin":
        return True
    return tier_at_least(tier, minimum)
