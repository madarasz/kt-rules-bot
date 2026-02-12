"""Reusable server selector component for the admin dashboard."""

import streamlit as st


def render_server_selector(servers: list[tuple[str, str]]) -> tuple[str, str]:
    """Render server selector and return selected server.

    Args:
        servers: List of (server_id, server_name) tuples (sorted by recency)

    Returns:
        Selected (server_id, server_name) tuple. server_id is "All" for all servers.
    """
    servers_with_all = [("All", "All")] + servers

    # Default to specific server if present
    default_server = "Sector Hungaricus - Skirmish wargame community"
    default_idx = next(
        (i for i, (_, name) in enumerate(servers_with_all) if name == default_server),
        0,
    )

    return st.selectbox(
        "Discord Server",
        options=servers_with_all,
        format_func=lambda x: x[1],
        index=default_idx,
    )
