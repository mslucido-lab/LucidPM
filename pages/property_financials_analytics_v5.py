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

    @rx.var
    def chart_data(self) -> list[dict]:
        """Aggregated by year for the selected property. Used by all chart views."""
        if not self.filtered_data:
            return []

        by_year: dict = {}
        for r in self.filtered_data:
            yr = r["FiscalYear"]
            if yr not in by_year:
                by_year[yr] = {"revenue": 0.0, "opex": 0.0}
            by_year[yr]["revenue"] += r["TotalRevenue"]
            by_year[yr]["opex"] += r["TotalOperatingExpenses"]

        result = []
        for yr in sorted(by_year.keys()):
            rev = by_year[yr]["revenue"]
            opex = by_year[yr]["opex"]
            noi = rev - opex
            est = (noi / (self.cap_rate / 100.0)) if self.cap_rate > 0 and noi > 0 else 0.0
            result.append({
                "year": yr,
                "revenue": round(rev),
                "opex": round(opex),
                "noi": round(noi),
                "valuation": round(est),
            })
        return result


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



def tab_button(label: str, tab_id: str) -> rx.Component:
    return rx.button(
        label,
        on_click=PropertyFinancialsAnalyticsState.set_active_tab(tab_id),
        variant=rx.cond(
            PropertyFinancialsAnalyticsState.active_tab == tab_id,
            "solid",
            "outline",
        ),
        color_scheme="blue",
        size="2",
    )


def placeholder_box(label: str) -> rx.Component:
    return rx.box(
        rx.text(label, size="3", color="#888"),
        style={
            "background": "white",
            "border": "1px solid #dfe6f0",
            "border_radius": "10px",
            "padding": "60px",
            "width": "100%",
            "text_align": "center",
        },
    )


def summary_chart() -> rx.Component:
    return rx.box(
        rx.recharts.composed_chart(
            rx.recharts.bar(
                data_key="revenue",
                fill="#185FA5",
                fill_opacity=0.22,
                stroke="#185FA5",
                stroke_width=1.2,
                y_axis_id="left",
                name="Revenue",
            ),
            rx.recharts.bar(
                data_key="opex",
                fill="#E24B4A",
                fill_opacity=0.22,
                stroke="#E24B4A",
                stroke_width=1.2,
                y_axis_id="left",
                name="Expenses",
            ),
            rx.recharts.line(
                data_key="noi",
                stroke="#1D9E75",
                stroke_width=3,
                dot={"fill": "#1D9E75", "stroke": "white", "strokeWidth": 2, "r": 5},
                y_axis_id="left",
                name="NOI",
            ),
            rx.recharts.line(
                data_key="valuation",
                stroke="#BA7517",
                stroke_width=1.5,
                stroke_dasharray="6 4",
                dot={"fill": "#BA7517", "r": 3},
                y_axis_id="right",
                name="Valuation (est.)",
            ),
            rx.recharts.x_axis(data_key="year"),
            rx.recharts.y_axis(
                y_axis_id="left",
                orientation="left",
            ),
            rx.recharts.y_axis(
                y_axis_id="right",
                orientation="right",
            ),
            rx.recharts.cartesian_grid(stroke_dasharray="3 3", vertical=False),
            rx.recharts.graphing_tooltip(),
            rx.recharts.legend(),
            data=PropertyFinancialsAnalyticsState.chart_data,
            width="100%",
            height=320,
        ),
        width="100%",
        style={
            "background": "white",
            "border": "1px solid #dfe6f0",
            "border_radius": "10px",
            "padding": "24px",
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
                    tab_button("Summary", "summary"),
                    tab_button("Trend", "trend"),
                    tab_button("Margins", "margins"),
                    tab_button("Valuation", "valuation"),
                    tab_button("Compare", "compare"),
                    spacing="2",
                    width="100%",
                ),

                rx.cond(
                    PropertyFinancialsAnalyticsState.active_tab == "summary",
                    summary_chart(),
                    rx.cond(
                        PropertyFinancialsAnalyticsState.active_tab == "trend",
                        placeholder_box("Trend — coming soon"),
                        rx.cond(
                            PropertyFinancialsAnalyticsState.active_tab == "margins",
                            placeholder_box("Margins — coming soon"),
                            rx.cond(
                                PropertyFinancialsAnalyticsState.active_tab == "valuation",
                                placeholder_box("Valuation — coming soon"),
                                placeholder_box("Compare — coming soon"),
                            ),
                        ),
                    ),
                ),

                width="100%",
                spacing="5",
            ),
            padding="24px",
            max_width="1400px",
        ),
        current_path="/property-financials-analytics",
    )
