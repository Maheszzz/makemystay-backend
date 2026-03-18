from typing import List, Optional

from app.models.agent import Agent
from app.models.lead import Lead


def assign_lead(lead: Lead, agents: List[Agent]) -> Optional[Agent]:
    """
    Core assignment logic for leads.
    Pure function - does not interact with the database.
    """
    # 1. Filter active agents
    active_agents = [a for a in agents if a.is_active]
    if not active_agents:
        return None

    # 2. Filter by location (if lead has location)
    if lead.location:
        location_matched = [
            a for a in active_agents
            if a.location and lead.location.lower() in a.location.lower()
        ]
        # If no agents match location, fall back to all active agents
        # (or should we strictly match? Prompt says "Filter by location if lead has location")
        # I'll fall back to all active if no match, to ensure lead gets handled,
        # but prioritize matching location.
        if location_matched:
            active_agents = location_matched

    # 3. Filter agents under capacity
    available_agents = [a for a in active_agents if a.current_load < a.max_capacity]
    if not available_agents:
        return None

    # 4. Assignment Logic
    # If priority == 3 -> pick highest conversion_rate
    if getattr(lead, "priority", 1) == 3:
        # Sort by conversion rate descending
        available_agents.sort(key=lambda x: x.conversion_rate, reverse=True)
        return available_agents[0]

    # Else (priority 1 or 2) -> pick least loaded agent
    # Sort by current_load ascending
    available_agents.sort(key=lambda x: x.current_load)
    return available_agents[0]
