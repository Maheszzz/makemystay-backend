"""CRM pipeline stages (distinct from legacy ``Lead.status`` enum)."""

# Canonical pipeline for admin UI and Zoho alignment
VALID_LEAD_STAGES = frozenset(
    {
        "New Lead / Prospect",
        "Engaged",
        "Follow Up",
        "Visit Scheduled",
        "Reserved",
        "Dead",
        "new",
        "contacted",
        "interested",
        "visit_scheduled",
        "closed",
        "lost",
    }
)
