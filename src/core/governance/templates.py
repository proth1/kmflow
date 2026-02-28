"""Knowledge boundary templates for governance flags (Story #381).

Templates are defined here — never hardcoded in the flag detector.
Each template describes what the system cannot assess.
"""

from __future__ import annotations

# ── Segregation of Duties ────────────────────────────────────────────

SOD_DESCRIPTION = (
    "Merging roles '{role_a}' and '{role_b}' into a single role may violate "
    "segregation of duties requirements. This is a known constraint identified "
    "by the system based on role separation rules."
)

SOD_KNOWLEDGE_BOUNDARY = (
    "The system identifies potential segregation of duties conflicts based on "
    "configured role separation rules, but cannot determine whether your "
    "organization's specific control framework permits this combination or "
    "whether compensating controls exist."
)

# ── Regulatory Compliance ────────────────────────────────────────────

REGULATORY_DESCRIPTION = (
    "Automating element '{element_name}' may impact compliance with "
    "{regulation}. This change removes human oversight from a "
    "regulated activity. This is a possible impact requiring legal review."
)

REGULATORY_KNOWLEDGE_BOUNDARY = (
    "The system flags elements tagged with regulatory references, but cannot "
    "determine whether automation satisfies your organization's specific "
    "compliance controls or whether the regulation permits automated processing "
    "under certain conditions."
)

# ── Authorization Level Change ───────────────────────────────────────

AUTHORIZATION_DESCRIPTION = (
    "Changing the role for element '{element_name}' from '{original_role}' "
    "to '{new_role}' alters the authorization level. This is a known "
    "constraint identified by the system."
)

AUTHORIZATION_KNOWLEDGE_BOUNDARY = (
    "The system detects changes to role assignments on approval-gated elements, "
    "but cannot assess whether the new role has equivalent authorization in "
    "your organization's specific delegation of authority framework."
)
