import reflex as rx
from LucidPM_Reflex.state import AppState, run_query, BRAND_DARK, BRAND_PRIMARY
from LucidPM_Reflex.components.sidebar import page_shell


# Analytics chart color palette — locked standard for all chart views
CHART_REVENUE_FILL = "#6FA8DC"
CHART_REVENUE_STROKE = "#3D85C6"
CHART_OPEX_FILL = "#F4A6A6"
CHART_OPEX_STROKE = "#D96B6B"
CHART_NOI_STROKE = "#4AA384"
CHART_VAL_STROKE = "#C78A35"
CHART_MARGIN_GREEN = "#4AA384"
CHART_MARGIN_AMBER = "#C78A35"
CHART_MARGIN_RED = "#D96B6B"
COMPARE_BROADWAY_FILL = "#2B6CB0"
COMPARE_WALNUT_FILL = "#2AA37A"
COMPARE_EULESS_FILL = "#C47A16"
COMPARE_DEFAULT_FILL = "#8A8A8A"


class PropertyFinancialsAnalyticsState(AppState):
    selected_property: str = "All properties"
    cap_rate: float = 6.0
    active_tab: str = "summary"
    compare_period: str = ""
    compare_metric: str = "all"

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

    def set_compare_period(self, v: str):
        self.compare_period = v

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

    @rx.var
    def margin_chart_data(self) -> list[dict]:
        """NOI margin % by year with pre-computed threshold display colors."""
        result = []
        for row in self.chart_data:
            rev = float(row.get("revenue", 0))
            noi = float(row.get("noi", 0))
            margin = round((noi / rev * 100.0), 1) if rev > 0 else 0.0

            if margin >= 60:
                fill = "rgba(42, 163, 122, 0.22)"
                stroke = COMPARE_WALNUT_FILL
            elif margin >= 45:
                fill = "rgba(196, 122, 22, 0.22)"
                stroke = COMPARE_EULESS_FILL
            else:
                fill = "rgba(244, 166, 166, 0.40)"
                stroke = CHART_MARGIN_RED

            result.append({
                "year": row["year"],
                "margin": margin,
                "fill": fill,
                "stroke": stroke,
            })
        return result

    @rx.var
    def compare_year_options(self) -> list[str]:
        years = sorted({r["FiscalYear"] for r in self.financials_data}, reverse=True)
        return years

    @rx.var
    def compare_chart_data(self) -> list[dict]:
        if not self.compare_period or not self.financials_data:
            return []

        result = []

        for pid, name in self.property_names_map.items():
            rows = [
                r for r in self.financials_data
                if r["PropertyID"] == pid and r["FiscalYear"] == self.compare_period
            ]

            if not rows:
                continue

            revenue = sum(r["TotalRevenue"] for r in rows)
            opex = sum(r["TotalOperatingExpenses"] for r in rows)
            noi = revenue - opex

            result.append({
                "property": name,
                "revenue": round(revenue),
                "opex": round(opex),
                "noi": round(noi),
            })

        return sorted(result, key=lambda x: x["property"])

    @rx.var
    def compare_revenue_share_data(self) -> list[dict]:
        """Revenue as % of portfolio total for the selected compare year."""
        if not self.compare_chart_data:
            return []

        total = sum(float(row.get("revenue", 0)) for row in self.compare_chart_data)
        if total == 0:
            return []

        result = []
        for row in self.compare_chart_data:
            prop = str(row.get("property", ""))
            revenue = float(row.get("revenue", 0))
            pct = round(revenue / total * 100, 1)
            fill = (
                COMPARE_BROADWAY_FILL if prop == "Broadway"
                else COMPARE_WALNUT_FILL if prop == "Walnut"
                else COMPARE_EULESS_FILL if prop == "Euless"
                else COMPARE_DEFAULT_FILL
                )
            result.append({
                "property": prop,
                "value": pct,
                "fill": fill
            })
        return result

    @rx.var
    def compare_margin_by_property_data(self) -> list[dict]:
        if not self.compare_chart_data:
            return []

        result = []
        for row in self.compare_chart_data:
            revenue = float(row.get("revenue", 0))
            noi = float(row.get("noi", 0))
            margin = round((noi / revenue * 100.0), 1) if revenue > 0 else 0.0
            prop = str(row.get("property", ""))
            fill = (
                "rgba(43, 108, 176, 0.22)" if prop == "Broadway"
                else "rgba(42, 163, 122, 0.22)" if prop == "Walnut"
                else "rgba(196, 122, 22, 0.22)" if prop == "Euless"
                else "rgba(138, 138, 138, 0.22)"
            )
            stroke = (
                COMPARE_BROADWAY_FILL if prop == "Broadway"
                else COMPARE_WALNUT_FILL if prop == "Walnut"
                else COMPARE_EULESS_FILL if prop == "Euless"
                else COMPARE_DEFAULT_FILL
            )
            result.append({
                "property": prop,
                "margin": margin,
                "fill": fill,
                "stroke": stroke,
            })
        return result

    @rx.var
    def valuation_chart_data(self) -> list[dict]:
        """Estimated value and price per SF by year for Valuation tab."""
        if self.selected_property_id == "0":
            total_sqft = sum(float(v) for v in self.property_sqft.values())
        else:
            total_sqft = float(self.property_sqft.get(self.selected_property_id, 0))

        result = []
        for row in self.chart_data:
            est = float(row.get("valuation", 0))
            psf = round(est / total_sqft, 2) if total_sqft > 0 and est > 0 else 0.0
            result.append({
                "year": row["year"],
                "valuation": est,
                "price_per_sf": psf,
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



def chart_container(chart_component: rx.Component) -> rx.Component:
    """Standard wrapper for all analytics chart views."""
    return rx.box(
        chart_component,
        width="100%",
        style={
            "background": "white",
            "border": "1px solid #dfe6f0",
            "border_radius": "10px",
            "padding": "24px",
        },
    )


def summary_chart() -> rx.Component:
    return chart_container(
        rx.recharts.composed_chart(
            rx.recharts.bar(
                data_key="revenue",
                fill="rgba(111, 168, 220, 0.40)",
                stroke=CHART_REVENUE_STROKE,
                stroke_width=1.0,
                y_axis_id="left",
                name="Revenue",
            ),
            rx.recharts.bar(
                data_key="opex",
                fill="rgba(244, 166, 166, 0.40)",
                stroke=CHART_OPEX_STROKE,
                stroke_width=1.0,
                y_axis_id="left",
                name="Expenses",
            ),
            rx.recharts.line(
                data_key="noi",
                stroke=CHART_NOI_STROKE,
                stroke_width=2.4,
                dot={"fill": CHART_NOI_STROKE, "stroke": "white", "strokeWidth": 2, "r": 4},
                y_axis_id="left",
                name="NOI",
            ),
            rx.recharts.line(
                data_key="valuation",
                stroke=CHART_VAL_STROKE,
                stroke_width=1.4,
                stroke_dasharray="6 4",
                dot={"fill": CHART_VAL_STROKE, "r": 3},
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
            margin={"top": 10, "right": 30, "left": 10, "bottom": 0},
        )
    )



def trend_chart() -> rx.Component:
    return chart_container(
        rx.recharts.composed_chart(
            rx.recharts.bar(
                data_key="revenue",
                fill="rgba(111, 168, 220, 0.40)",
                stroke=CHART_REVENUE_STROKE,
                stroke_width=1.0,
                y_axis_id="left",
                name="Revenue",
            ),
            rx.recharts.bar(
                data_key="opex",
                fill="rgba(244, 166, 166, 0.40)",
                stroke=CHART_OPEX_STROKE,
                stroke_width=1.0,
                y_axis_id="left",
                name="Expenses",
            ),
            rx.recharts.line(
                data_key="noi",
                stroke=CHART_NOI_STROKE,
                stroke_width=2.4,
                dot={"fill": CHART_NOI_STROKE, "stroke": "white", "strokeWidth": 2, "r": 4},
                y_axis_id="left",
                name="NOI",
            ),
            rx.recharts.x_axis(data_key="year"),
            rx.recharts.y_axis(
                y_axis_id="left",
                orientation="left",
            ),
            rx.recharts.cartesian_grid(stroke_dasharray="3 3", vertical=False),
            rx.recharts.graphing_tooltip(),
            rx.recharts.legend(),
            data=PropertyFinancialsAnalyticsState.chart_data,
            width="100%",
            height=320,
            margin={"top": 10, "right": 30, "left": 10, "bottom": 0},
        )
    )



def margin_bar_cell(row) -> rx.Component:
    return rx.recharts.cell(fill=row["fill"], stroke=row["stroke"])

def margins_chart() -> rx.Component:
    return chart_container(
        rx.recharts.bar_chart(
            rx.recharts.bar(
                rx.foreach(
                    PropertyFinancialsAnalyticsState.margin_chart_data,
                    margin_bar_cell,
                ),
                data_key="margin",
                name="NOI Margin %",
            ),
            rx.recharts.x_axis(data_key="year"),
            rx.recharts.y_axis(
                domain=[0, 100],
                unit="%",
            ),
            rx.recharts.cartesian_grid(stroke_dasharray="3 3", vertical=False),
            rx.recharts.graphing_tooltip(),
            rx.recharts.reference_line(
                y=60,
                stroke="#1F4E79",
                stroke_dasharray="4 2",
                stroke_width=2.0,
                label="60%",
            ),
            rx.recharts.reference_line(
                y=45,
                stroke=CHART_MARGIN_AMBER,
                stroke_dasharray="4 2",
                stroke_width=2.0,
                label="45%",
            ),
            data=PropertyFinancialsAnalyticsState.margin_chart_data,
            width="100%",
            height=320,
            margin={"top": 10, "right": 30, "left": 10, "bottom": 0},
        )
    )


def valuation_chart() -> rx.Component:
    return chart_container(
        rx.recharts.composed_chart(
            rx.recharts.area(
                data_key="valuation",
                stroke=CHART_VAL_STROKE,
                stroke_width=2.0,
                fill="rgba(196, 122, 22, 0.22)",
                dot={"fill": CHART_VAL_STROKE, "stroke": "white", "strokeWidth": 2, "r": 4},
                y_axis_id="left",
                name="Est. Value",
            ),
            rx.recharts.line(
                data_key="price_per_sf",
                stroke=CHART_NOI_STROKE,
                stroke_width=1.8,
                stroke_dasharray="5 3",
                dot={"fill": CHART_NOI_STROKE, "r": 3},
                y_axis_id="right",
                name="Price / SF",
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
            data=PropertyFinancialsAnalyticsState.valuation_chart_data,
            width="100%",
            height=320,
            margin={"top": 10, "right": 30, "left": 10, "bottom": 0},
        )
    )



def compare_revenue_cell(row) -> rx.Component:
    return rx.recharts.cell(fill=row["fill"])


def compare_margin_cell(row) -> rx.Component:
    return rx.recharts.cell(fill=row["fill"], stroke=row["stroke"])


def compare_chart_card(title: str, subtitle: str, content: rx.Component) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.vstack(
                rx.text(title, size="4", weight="bold", color="#222"),
                rx.text(subtitle, size="2", color="#444"),
                align_items="start",
                spacing="1",
            ),
            content,
            width="100%",
            spacing="3",
        ),
        style={
            "background": "white",
            "border": "1px solid #dfe6f0",
            "border_radius": "10px",
            "padding": "20px 24px",
            "flex": "1",
            "min_width": "420px",
        },
    )


def compare_chart() -> rx.Component:
    return chart_container(
        rx.vstack(
            rx.hstack(
                rx.text("Year:", size="2", color="#666"),
                rx.select(
                    PropertyFinancialsAnalyticsState.compare_year_options,
                    value=PropertyFinancialsAnalyticsState.compare_period,
                    on_change=PropertyFinancialsAnalyticsState.set_compare_period,
                ),
                align="center",
                spacing="2",
            ),
            rx.recharts.bar_chart(
                rx.recharts.bar(
                    data_key="revenue",
                    fill="rgba(111, 168, 220, 0.40)",
                    stroke=CHART_REVENUE_STROKE,
                    stroke_width=1.0,
                    name="Revenue",
                ),
                rx.recharts.bar(
                    data_key="opex",
                    fill="rgba(244, 166, 166, 0.40)",
                    stroke=CHART_OPEX_STROKE,
                    stroke_width=1.0,
                    name="Expenses",
                ),
                rx.recharts.bar(
                    data_key="noi",                    
                    fill="rgba(42, 163, 122, 0.22)",
                    stroke=COMPARE_WALNUT_FILL,
                    stroke_width=1.0,
                    name="NOI",
                ),
                rx.recharts.x_axis(data_key="property"),
                rx.recharts.y_axis(),
                rx.recharts.cartesian_grid(stroke_dasharray="3 3", vertical=False),
                rx.recharts.graphing_tooltip(),
                rx.recharts.legend(),
                data=PropertyFinancialsAnalyticsState.compare_chart_data,
                bar_category_gap="30%",
                bar_gap=2,
                width="100%",
                height=320,
                margin={"top": 10, "right": 30, "left": 10, "bottom": 0},
            ),
            rx.hstack(
                compare_chart_card(
                    "Revenue share",
                    "% of combined portfolio revenue",
                    rx.recharts.pie_chart(
                        rx.recharts.pie(
                            rx.foreach(
                                PropertyFinancialsAnalyticsState.compare_revenue_share_data,
                                compare_revenue_cell,
                            ),
                            data=PropertyFinancialsAnalyticsState.compare_revenue_share_data,
                            data_key="value",
                            name_key="property",
                            inner_radius=60,
                            outer_radius=105,
                            padding_angle=0,
                        ),
                        rx.recharts.graphing_tooltip(),
                        rx.recharts.legend(),
                        width="100%",
                        height=250,
                    ),
                ),
                compare_chart_card(
                    "NOI margin by property",
                    "NOI as % of revenue, selected year",
                    rx.recharts.bar_chart(
                        rx.recharts.bar(
                            rx.foreach(
                                PropertyFinancialsAnalyticsState.compare_margin_by_property_data,
                                compare_margin_cell,
                            ),
                            data_key="margin",
                            name="NOI Margin %",
                        ),
                        rx.recharts.x_axis(data_key="property"),
                        rx.recharts.y_axis(domain=[0, 100], unit="%"),
                        rx.recharts.cartesian_grid(stroke_dasharray="3 3", vertical=False),
                        rx.recharts.graphing_tooltip(),
                        data=PropertyFinancialsAnalyticsState.compare_margin_by_property_data,
                        width="100%",
                        height=250,
                        margin={"top": 10, "right": 10, "left": 0, "bottom": 0},
                    ),
                ),
                width="100%",
                spacing="4",
                align="stretch",
                flex_wrap="wrap",
            ),
            width="100%",
            spacing="4",
        )
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
                        trend_chart(),
                        rx.cond(
                            PropertyFinancialsAnalyticsState.active_tab == "margins",
                            margins_chart(),
                            rx.cond(
                                PropertyFinancialsAnalyticsState.active_tab == "valuation",
                                valuation_chart(),
                                compare_chart(),
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
