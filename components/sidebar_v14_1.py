"""
Shared sidebar navigation component.
"""

import reflex as rx
from LucidPM_Reflex.state import AppState, BRAND_PRIMARY, BRAND_DARK


SIDEBAR_DEFAULT_WIDTH = 220      # px — default expanded width
SIDEBAR_COLLAPSED_WIDTH = 48     # px — icon-only collapsed width
SIDEBAR_MIN_WIDTH = 48           # px — drag minimum
SIDEBAR_MAX_WIDTH = 320          # px — drag maximum
SIDEBAR_COLLAPSE_THRESHOLD = 80  # px — snap to collapsed below this


SIDEBAR_RESIZER_SCRIPT = """
(function() {
    var COLLAPSED = 48;
    var DEFAULT = 220;
    var MIN = 48;
    var MAX = 320;
    var THRESHOLD = 80;
    var STORAGE_KEY = 'lucid_sidebar_width';
    var LAST_EXPANDED_KEY = 'lucid_sidebar_last_expanded_width';

    function getSidebar() { return document.getElementById('lucid-sidebar'); }
    function getContent() { return document.getElementById('lucid-content'); }
    function getToggle() { return document.getElementById('lucid-sidebar-toggle'); }

    function readNumber(key, fallback) {
        try {
            var v = localStorage.getItem(key);
            var n = v ? parseInt(v, 10) : fallback;
            return isNaN(n) ? fallback : n;
        } catch(e) { return fallback; }
    }

    function saveNumber(key, value) {
        try { localStorage.setItem(key, String(value)); } catch(e) {}
    }

    function loadWidth() {
        return readNumber(STORAGE_KEY, DEFAULT);
    }

    function loadLastExpandedWidth() {
        var w = readNumber(LAST_EXPANDED_KEY, DEFAULT);
        if (w <= THRESHOLD) return DEFAULT;
        return Math.min(Math.max(w, 160), MAX);
    }

    function setLabelVisibility(sidebar, collapsed) {
        if (!sidebar) return;
        var labels = sidebar.querySelectorAll('.sidebar-label');
        var sections = sidebar.querySelectorAll('.sidebar-section-label');
        var appSubtitle = sidebar.querySelector('.sidebar-subtitle');
        var appTitle = sidebar.querySelector('.sidebar-title');

        labels.forEach(function(el) { el.style.display = collapsed ? 'none' : ''; });
        sections.forEach(function(el) { el.style.display = collapsed ? 'none' : ''; });
        if (appSubtitle) appSubtitle.style.display = collapsed ? 'none' : '';
        if (appTitle) appTitle.style.display = collapsed ? 'none' : '';
    }

    function applyWidth(w) {
        var sidebar = getSidebar();
        var content = getContent();
        if (!sidebar || !content) return null;

        var collapsed = w <= THRESHOLD;
        var finalW = collapsed ? COLLAPSED : Math.min(Math.max(w, MIN), MAX);

        sidebar.style.width = finalW + 'px';
        sidebar.style.minWidth = finalW + 'px';
        sidebar.style.maxWidth = finalW + 'px';
        content.style.marginLeft = finalW + 'px';
        var resizerEl = document.getElementById('lucid-sidebar-resizer');
        if (resizerEl) resizerEl.style.left = finalW + 'px';

        setLabelVisibility(sidebar, collapsed);

        var toggle = getToggle();
        if (toggle) {
            toggle.textContent = collapsed ? '▶' : '◀';
            toggle.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
        }

        if (!collapsed) saveNumber(LAST_EXPANDED_KEY, finalW);
        return finalW;
    }

    function applySavedWidth() {
        var applied = applyWidth(loadWidth());
        if (applied !== null) saveNumber(STORAGE_KEY, applied);
        return applied;
    }

    function applySavedWidthSoon() {
        applySavedWidth();
        setTimeout(applySavedWidth, 25);
        setTimeout(applySavedWidth, 150);
        setTimeout(applySavedWidth, 500);
    }

    // Always apply on script execution. Reflex may recreate the shell on navigation.
    applySavedWidthSoon();

    // Install delegated handlers only once. They survive Reflex page navigation.
    if (window.__lucidSidebarResizerInstalled !== true) {
        window.__lucidSidebarResizerInstalled = true;
        window.__lucidSidebarIsResizing = false;
        window.__lucidSidebarStartX = 0;
        window.__lucidSidebarStartWidth = 0;

        document.addEventListener('mousedown', function(e) {
            var target = e.target;
            if (!target || target.id !== 'lucid-sidebar-resizer') return;

            var sidebar = getSidebar();
            if (!sidebar) return;

            window.__lucidSidebarIsResizing = true;
            window.__lucidSidebarStartX = e.clientX;
            window.__lucidSidebarStartWidth = sidebar.offsetWidth || loadWidth();
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        });

        document.addEventListener('mousemove', function(e) {
            if (!window.__lucidSidebarIsResizing) return;
            var delta = e.clientX - window.__lucidSidebarStartX;
            var newWidth = window.__lucidSidebarStartWidth + delta;
            applyWidth(newWidth);
        });

        document.addEventListener('mouseup', function() {
            if (!window.__lucidSidebarIsResizing) return;
            window.__lucidSidebarIsResizing = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';

            var sidebar = getSidebar();
            if (sidebar) saveNumber(STORAGE_KEY, sidebar.offsetWidth || loadWidth());
        });

        document.addEventListener('click', function(e) {
            var target = e.target;
            if (!target) return;

            if (target.id === 'lucid-sidebar-toggle') {
                var sidebar = getSidebar();
                var current = sidebar ? sidebar.offsetWidth : loadWidth();
                var collapsed = current <= THRESHOLD;
                var targetWidth = collapsed ? loadLastExpandedWidth() : COLLAPSED;
                var applied = applyWidth(targetWidth);
                if (applied !== null) saveNumber(STORAGE_KEY, applied);
                e.preventDefault();
                return;
            }

            // Reflex route navigation can recreate the shell. Reapply after nav clicks.
            var link = target.closest ? target.closest('a') : null;
            if (link) {
                setTimeout(applySavedWidthSoon, 50);
            }
        }, true);

        window.addEventListener('popstate', applySavedWidthSoon);
        window.addEventListener('focus', applySavedWidthSoon);
        document.addEventListener('visibilitychange', function() {
            if (!document.hidden) applySavedWidthSoon();
        });
    }
})();
"""


def nav_link(label: str, icon: str, href: str, active_path: str) -> rx.Component:
    is_active = href == active_path
    return rx.link(
        rx.hstack(
            rx.text(icon, size="3"),
            rx.text(
                label,
                size="2",
                weight="bold" if is_active else "regular",
                class_name="sidebar-label",
            ),
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
        class_name="sidebar-section-label",
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
            rx.box(
                rx.vstack(
                    rx.text(
                        "Lucid Property Manager",
                        size="3",
                        weight="bold",
                        color="white",
                        class_name="sidebar-title",
                    ),
                    rx.text(
                        "Commercial RE Operations",
                        size="1",
                        color="rgba(255,255,255,0.65)",
                        class_name="sidebar-subtitle",
                    ),
                    spacing="0",
                    align_items="start",
                ),
                padding="16px 14px 12px 14px",
            ),

            rx.box(
                rx.hstack(
                    rx.box(
                        style={
                            "width": "8px",
                            "height": "8px",
                            "border_radius": "50%",
                            "background": rx.cond(AppState.use_test_db, "#4caf50", "#f44336"),
                            "flex_shrink": "0",
                        }
                    ),
                    rx.text(
                        AppState.db_label,
                        size="1",
                        color="rgba(255,255,255,0.85)",
                        weight="bold",
                        class_name="sidebar-label",
                    ),
                    rx.spacer(),
                    rx.button(
                        "Switch",
                        on_click=AppState.toggle_db,
                        size="1",
                        variant="ghost",
                        class_name="sidebar-label",
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

            rx.box(
                nav_section_label("Dashboards"),
                nav_link("Dashboard", "🏠", "/", current_path),
                nav_link("Rent Roll", "📋", "/rent-roll", current_path),
                nav_link("Property Financials", "💰", "/property-financials", current_path),
                nav_link("Analytics", "📈", "/property-financials-analytics", current_path),
                nav_link("Proforma", "📊", "/proforma", current_path),

                nav_section_label("Tenants"),
                nav_link("Tenants", "👥", "/tenants", current_path),
                nav_link("Waiting List", "⏳", "/waiting-list", current_path),
                nav_link("Communications", "📨", "/communications", current_path),
                nav_link("Lease Packages", "🧾", "/lease-package-builder", current_path),

                nav_section_label("Operations"),
                nav_link("Work Items", "🛠", "/work-items", current_path),
                nav_link("Leases Expiring", "📄", "/leases-expiring", current_path),
                nav_link("Documents Expiring", "📑", "/documents-expiring", current_path),
                nav_link("Follow Ups", "⏰", "/follow-ups", current_path),

                nav_section_label("Admin"),
                nav_link("Properties", "🏢", "/admin/properties", current_path),
                nav_link("Vendors", "🔧", "/admin/vendors", current_path),
                nav_link("Suites", "🚪", "/admin/suites", current_path),
                nav_link("Lease Templates", "📂", "/admin/lease-templates", current_path),
                nav_link("Settings", "⚙️", "/admin/settings", current_path),

                width="100%",
                padding_bottom="24px",
            ),

            rx.box(
                rx.text(
                    "◀",
                    id="lucid-sidebar-toggle",
                    title="Collapse sidebar",
                    style={
                        "cursor": "pointer",
                        "color": "rgba(255,255,255,0.70)",
                        "font_size": "12px",
                        "padding": "8px 14px",
                        "display": "block",
                        "text_align": "center",
                        "_hover": {"color": "white"},
                        "transition": "color 0.15s",
                    },
                ),
                width="100%",
                padding_bottom="8px",
            ),

            spacing="0",
            width="100%",
            align_items="start",
        ),
        rx.box(
            id="lucid-sidebar-resizer",
            style={
                "position": "fixed",
                "top": "0",
                "left": f"{SIDEBAR_DEFAULT_WIDTH}px",
                "width": "6px",
                "height": "100vh",
                "cursor": "col-resize",
                "z_index": "200",
                "_hover": {"background": "rgba(255,255,255,0.20)"},
                "transition": "background 0.15s",
            },
        ),
        id="lucid-sidebar",
        style={
            "width": f"{SIDEBAR_DEFAULT_WIDTH}px",
            "min_width": f"{SIDEBAR_DEFAULT_WIDTH}px",
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
        rx.script(SIDEBAR_RESIZER_SCRIPT),
        sidebar(current_path),
        rx.box(
            content,
            id="lucid-content",
            style={
                "margin_left": f"{SIDEBAR_DEFAULT_WIDTH}px",
                "min_height": "100vh",
                "background": "#F4F6FA",
                "padding": "32px",
                "transition": "margin-left 0.15s ease",
            },
        ),
        style={"display": "flex", "min_height": "100vh"},
    )
