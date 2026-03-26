"""CRM pipeline stages (distinct from legacy ``Lead.status`` enum)."""

# Canonical pipeline for admin UI and Zoho alignment
VALID_LEAD_STAGES = frozenset(
    {
        "new",
        "contacted",
        "interested",
        "visit_scheduled",
        "closed",
        "lost",
    }
)
