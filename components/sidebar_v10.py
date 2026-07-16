"""
Shared sidebar navigation component.
"""

import reflex as rx
from LucidPM_Reflex.state import AppState, BRAND_PRIMARY, BRAND_DARK


def nav_link(label: str, icon: str, href: str, active_path: str) -> rx.Component:
    is_active = href == active_path
    return rx.link(
        rx.hstack(
            rx.text(icon, size="3"),
            rx.text(label, size="2", weight="bold" if is_active else "regular"),
            spacing="2",
            align="center",
        ),
        href=href,
        style={
            "display": "block",
            "padding": "8px 14px",
            "border_radius": "8px",
            "text_decoration": "none",
            "background": "rgba(255,255,255,0.18)" if is_active else "transparent",
            "border_left": f"4px solid white" if is_active else "4px solid transparent",
            "color": "white",
            "margin_bottom": "2px",
            "_hover": {"background": "rgba(255,255,255,0.10)"},
        },
    )


def nav_section_label(label: str) -> rx.Component:
    return rx.text(
        label,
        size="1",
        weight="bold",
        style={
            "color": "rgba(255,255,255,0.60)",
            "text_transform": "uppercase",
            "letter_spacing": "0.08em",
            "padding": "12px 14px 4px 14px",
            "border_top": "1px solid rgba(255,255,255,0.16)",
            "margin_top": "8px",
        },
    )


def sidebar(current_path: str = "/") -> rx.Component:
    return rx.box(
        rx.vstack(
            # Logo / app name
            rx.box(
                rx.vstack(
                    rx.text(
                        "Lucid Property Manager",
                        size="3",
                        weight="bold",
                        color="white",
                    ),
                    rx.text(
                        "Commercial RE Operations",
                        size="1",
                        color="rgba(255,255,255,0.65)",
                    ),
                    spacing="0",
                    align_items="start",
                ),
                padding="16px 14px 12px 14px",
            ),

            # DB environment indicator
            rx.box(
                rx.hstack(
                    rx.box(
                        style={
                            "width": "8px", "height": "8px", "border_radius": "50%",
                            "background": rx.cond(AppState.use_test_db, "#4caf50", "#f44336"),
                            "flex_shrink": "0",
                        }
                    ),
                    rx.text(
                        AppState.db_label,
                        size="1",
                        color="rgba(255,255,255,0.85)",
                        weight="bold",
                    ),
                    rx.spacer(),
                    rx.button(
                        "Switch",
                        on_click=AppState.toggle_db,
                        size="1",
                        variant="ghost",
                        style={"color": "rgba(255,255,255,0.70)", "font_size": "11px"},
                    ),
                    align="center",
                    width="100%",
                ),
                style={
                    "background": "rgba(0,0,0,0.20)",
                    "border_radius": "8px",
                    "padding": "6px 10px",
                    "margin": "0 10px 12px 10px",
                },
            ),

            # Main nav
            rx.box(
                # Dashboards
                nav_section_label("Dashboards"),
                nav_link("Dashboard", "🏠", "/", current_path),
                nav_link("Rent Roll", "📋", "/rent-roll", current_path),
                nav_link("Property Financials", "💰", "/property-financials", current_path),
                nav_link("Analytics", "📈", "/property-financials-analytics", current_path),
                nav_link("Proforma", "📊", "/proforma", current_path),

                # Tenants
                nav_section_label("Tenants"),
                nav_link("Tenants", "👥", "/tenants", current_path),
                nav_link("Waiting List", "⏳", "/waiting-list", current_path),
                nav_link("Communications", "📨", "/communications", current_path),
                nav_link("Lease Packages", "🧾", "/lease-package-builder", current_path),

                # Operations
                nav_section_label("Operations"),
                nav_link("Work Items", "🛠", "/work-items", current_path),
                nav_link("Leases Expiring", "📄", "/leases-expiring", current_path),
                nav_link("Documents Expiring", "📑", "/documents-expiring", current_path),
                nav_link("Follow Ups", "⏰", "/follow-ups", current_path),

                # Admin
                nav_section_label("Admin"),
                nav_link("Properties", "🏢", "/admin/properties", current_path),
                nav_link("Vendors", "🔧", "/admin/vendors", current_path),
                nav_link("Suites", "🚪", "/admin/suites", current_path),
                nav_link("Lease Templates", "📂", "/admin/lease-templates", current_path),
                nav_link("Settings", "⚙️", "/admin/settings", current_path),

                width="100%",
                padding_bottom="24px",
            ),

            spacing="0",
            width="100%",
            align_items="start",
        ),

        style={
            "width": "220px",
            "min_width": "220px",
            "height": "100vh",
            "background": f"linear-gradient(180deg, {BRAND_DARK} 0%, {BRAND_PRIMARY} 100%)",
            "position": "fixed",
            "top": "0",
            "left": "0",
            "overflow_y": "auto",
            "z_index": "100",
        },
    )


def page_shell(content: rx.Component, current_path: str = "/") -> rx.Component:
    """Wraps any page content with the sidebar layout."""
    return rx.box(
        sidebar(current_path),
        rx.box(
            content,
            style={
                "margin_left": "220px",
                "min_height": "100vh",
                "background": "#F4F6FA",
                "padding": "32px",
            },
        ),
        style={"display": "flex", "min_height": "100vh"},
    )
