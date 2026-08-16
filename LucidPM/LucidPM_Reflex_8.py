"""
Lucido Property Manager - Reflex App
Entry point: registers all pages and shared app config.

v2.5.0 additions:
  - /admin/properties  →  PropertiesPage
  - /admin/vendors     →  VendorsPage
  - /admin/suites      →  SuitesPage
"""

import reflex as rx
from LucidPM_Reflex.pages.dashboard import dashboard_page
from LucidPM_Reflex.pages.tenants import tenants_page, TenantState

# Admin pages
from LucidPM_Reflex.pages.properties import properties_page, PropertyState
from LucidPM_Reflex.pages.vendors import vendors_page, VendorState
from LucidPM_Reflex.pages.suites import suites_page, SuiteState

app = rx.App(
    theme=rx.theme(
        appearance="light",
        accent_color="blue",
        radius="medium",
    )
)

app.add_page(dashboard_page, route="/")
app.add_page(tenants_page, route="/tenants", on_load=TenantState.on_load)

# Admin
app.add_page(properties_page, route="/admin/properties", on_load=PropertyState.on_load)
app.add_page(vendors_page,    route="/admin/vendors",    on_load=VendorState.on_load)
app.add_page(suites_page,     route="/admin/suites",     on_load=SuiteState.on_load)
