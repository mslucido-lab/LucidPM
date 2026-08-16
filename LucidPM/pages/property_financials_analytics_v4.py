import reflex as rx
from LucidPM_Reflex.state import AppState, run_query, BRAND_DARK, BRAND_PRIMARY
from LucidPM_Reflex.components.sidebar import page_shell


class PropertyFinancialsAnalyticsState(AppState):
    selected_property: str = "All properties"
    cap_rate: float = 6.0
    active_tab: str = "summary"
    compare_period: str = ""

    financials_data: list[dict] = []
    property_sqft: dict = {}
    property_names_map: dict = {}
    property_id_by_name: dict = {}
    property_options: list[str] = ["All properties"]

    def set_cap_rate_value(self, v):
        try:
            self.cap_rate = float(v[0]) if isinstance(v, list) else float(v)
        except (TypeError, ValueError, IndexError):
            self.cap_rate = 6.0

    def on_load(self):
        rows = run_query(
            "SELECT pf.PropertyID, p.PropertyName, pf.FiscalYear, "
            "pf.TotalRevenue, pf.TotalOperatingExpenses "
            "FROM PropertyFinancials pf "
            "INNER JOIN Properties p ON pf.PropertyID = p.PropertyID "
            "ORDER BY pf.FiscalYear DESC",
            db=self.db,
        )

        normalized = []
        prop_map = {}
        id_by_name = {}
        sqft_map = {}

        prop_rows = run_query(
            "SELECT PropertyID, PropertyName FROM Properties ORDER BY PropertyName",
            db=self.db,
        )

        for p in prop_rows:
            pid = str(int(p["PropertyID"]))
            name = str(p["PropertyName"])
            prop_map[pid] = name
            id_by_name[name] = pid

        for r in rows:
            pid = str(int(r["PropertyID"]))
            if pid not in prop_map:
                prop_map[pid] = str(r["PropertyName"])
                id_by_name[str(r["PropertyName"])] = pid

            normalized.append({
                "PropertyID": pid,
                "FiscalYear": str(int(r["FiscalYear"])),
                "TotalRevenue": float(r["TotalRevenue"] or 0),
                "TotalOperatingExpenses": float(r["TotalOperatingExpenses"] or 0),
            })

        for pid in prop_map.keys():
            sqft_rows = run_query(
                "SELECT ISNULL(SUM(SquareFeet),0) AS total "
                "FROM PropertySuites WHERE PropertyID=? AND IsActive=1",
                (int(pid),),
                db=self.db,
            )
            sqft_map[pid] = float(sqft_rows[0]["total"] or 0) if sqft_rows else 0.0

        years = sorted({r["FiscalYear"] for r in normalized}, reverse=True)
        labels = ["All properties"] + sorted(id_by_name.keys())

        self.financials_data = normalized
        self.property_names_map = prop_map
        self.property_id_by_name = id_by_name
        self.property_sqft = sqft_map
        self.property_options = labels
        if self.selected_property not in labels:
            self.selected_property = "All properties"
        self.compare_period = years[0] if years else ""

    def reload_on_db_change(self):
        self.financials_data = []
        self.property_sqft = {}
        self.property_names_map = {}
        self.property_id_by_name = {}
        self.property_options = ["All properties"]
        yield PropertyFinancialsAnalyticsState.on_load()

    @rx.var
    def selected_property_id(self) -> str:
        if self.selected_property == "All properties":
            return "0"
        return str(self.property_id_by_name.get(self.selected_property, "0"))

    @rx.var
    def cap_rate_display(self) -> str:
        return f"{self.cap_rate:.2f}%"

    @rx.var
    def filtered_data(self) -> list[dict]:
        if self.selected_property_id == "0":
            return self.financials_data
        return [r for r in self.financials_data if r["PropertyID"] == self.selected_property_id]

    @rx.var
    def latest_year_data(self) -> dict:
        if not self.filtered_data:
            return {}

        latest = max(r["FiscalYear"] for r in self.filtered_data)
        rows = [r for r in self.filtered_data if r["FiscalYear"] == latest]

        revenue = sum(r["TotalRevenue"] for r in rows)
        opex = sum(r["TotalOperatingExpenses"] for r in rows)
        noi = revenue - opex

        return {
            "year": latest,
            "revenue": revenue,
            "opex": opex,
            "noi": noi,
        }

    @rx.var
    def metric_revenue(self) -> str:
        return f"${self.latest_year_data.get('revenue', 0):,.0f}"

    @rx.var
    def metric_opex(self) -> str:
        return f"${self.latest_year_data.get('opex', 0):,.0f}"

    @rx.var
    def metric_noi(self) -> str:
        return f"${self.latest_year_data.get('noi', 0):,.0f}"

    @rx.var
    def metric_margin(self) -> str:
        rev = self.latest_year_data.get("revenue", 0)
        noi = self.latest_year_data.get("noi", 0)
        margin = (noi / rev * 100.0) if rev > 0 else 0.0
        return f"{margin:.1f}%"

    @rx.var
    def metric_estimated_value(self) -> str:
        noi = self.latest_year_data.get("noi", 0)
        if self.cap_rate <= 0:
            return "$0"
        est = noi / (self.cap_rate / 100.0)
        return f"${est:,.0f}"


def analytics_metric(label: str, value):
    return rx.box(
        rx.vstack(
            rx.text(value, size="5", weight="bold", color=BRAND_DARK),
            rx.text(label, size="1", color="#666"),
            align_items="start",
        ),
        style={
            "background": "#f4f6fa",
            "border_radius": "8px",
            "padding": "14px 18px",
            "flex": "1",
        },
    )


def page_property_financials_analytics():
    return page_shell(
        rx.box(
            rx.vstack(
                rx.heading("Property Financials Analytics", size="6", color=BRAND_DARK),

                rx.hstack(
                    rx.select(
                        PropertyFinancialsAnalyticsState.property_options,
                        value=PropertyFinancialsAnalyticsState.selected_property,
                        on_change=PropertyFinancialsAnalyticsState.set_selected_property,
                    ),

                    rx.vstack(
                        rx.text(
                            "Cap Rate: ",
                            PropertyFinancialsAnalyticsState.cap_rate_display,
                            size="1",
                            color="#666",
                        ),
                        rx.slider(
                            value=[PropertyFinancialsAnalyticsState.cap_rate],
                            min=4.0,
                            max=10.0,
                            step=0.25,
                            on_change=PropertyFinancialsAnalyticsState.set_cap_rate_value,
                            width="240px",
                        ),
                    ),
                    width="100%",
                    justify="between",
                ),

                rx.hstack(
                    analytics_metric("Revenue", PropertyFinancialsAnalyticsState.metric_revenue),
                    analytics_metric("OPEX", PropertyFinancialsAnalyticsState.metric_opex),
                    analytics_metric("NOI", PropertyFinancialsAnalyticsState.metric_noi),
                    analytics_metric("NOI Margin", PropertyFinancialsAnalyticsState.metric_margin),
                    analytics_metric("Est. Value", PropertyFinancialsAnalyticsState.metric_estimated_value),
                    width="100%",
                ),

                rx.hstack(
                    rx.badge("Summary"),
                    rx.badge("Trend"),
                    rx.badge("Margins"),
                    rx.badge("Valuation"),
                    rx.badge("Compare"),
                ),

                rx.box(
                    rx.text("Charts coming soon", size="4", color="#666"),
                    style={
                        "background": "white",
                        "border": "1px solid #dfe6f0",
                        "border_radius": "10px",
                        "padding": "60px",
                        "width": "100%",
                        "text_align": "center",
                    },
                ),

                width="100%",
                spacing="5",
            ),
            padding="24px",
            max_width="1400px",
        ),
        current_path="/property-financials-analytics",
    )
