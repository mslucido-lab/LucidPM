"""
Dashboard page — placeholder.
"""

import reflex as rx
from LucidPM_Reflex.components.sidebar import page_shell
from LucidPM_Reflex.state import BRAND_DARK, BRAND_PRIMARY


def dashboard_content() -> rx.Component:
    return rx.vstack(
        rx.heading("Dashboard", size="7", color=BRAND_DARK),
        rx.text("Coming soon — work items, lease expirations, follow-ups at a glance.",
                color="#666", size="3"),

        # Placeholder metric cards
        rx.grid(
            _metric_card("Active Tenants", "—", "👥"),
            _metric_card("Open Work Items", "—", "🛠"),
            _metric_card("Leases Expiring (90d)", "—", "📄"),
            _metric_card("Overdue Follow-ups", "—", "⏰"),
            columns="4",
            spacing="4",
            width="100%",
        ),

        spacing="6",
        width="100%",
        max_width="1100px",
        align_items="start",
    )


def _metric_card(label: str, value: str, icon: str) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(icon, size="6"),
            rx.text(value, size="8", weight="bold", color=BRAND_DARK),
            rx.text(label, size="2", color="#666"),
            spacing="1",
            align_items="start",
        ),
        style={
            "background": "white",
            "border": "1px solid #dde3f0",
            "border_radius": "12px",
            "padding": "20px",
            "box_shadow": "0 1px 4px rgba(74,99,168,0.07)",
        },
    )


def dashboard_page() -> rx.Component:
    return page_shell(dashboard_content(), current_path="/")
