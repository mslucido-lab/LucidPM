"""
Lucido Property Manager - Reflex App
Entry point: registers all pages and shared app config.
"""

import reflex as rx
from LucidPM_Reflex.pages.dashboard import dashboard_page
from LucidPM_Reflex.pages.tenants import tenants_page

app = rx.App(
    theme=rx.theme(
        appearance="light",
        accent_color="blue",
        radius="medium",
    )
)

app.add_page(dashboard_page, route="/")
app.add_page(tenants_page, route="/tenants")
