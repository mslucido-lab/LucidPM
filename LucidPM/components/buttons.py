"""
Shared button components.
"""

import reflex as rx


# Radix has no olive accent scale, so the Edit button sets its colors directly.
EDIT_OLIVE = "#6B7F2A"
EDIT_OLIVE_HOVER_BG = "rgba(107, 127, 42, 0.10)"


def edit_button(label: str = "Edit", **props) -> rx.Component:
    """Outline button in the app's distinct Edit color (olive)."""
    # !important: Radix's outline rule (.rt-BaseButton:where(.rt-variant-outline))
    # ties our class on specificity and loads later, so plain values lose.
    style = {
        "color": f"{EDIT_OLIVE} !important",
        "box_shadow": f"inset 0 0 0 1px {EDIT_OLIVE} !important",
        "background": "transparent",
        "cursor": "pointer",
        "_hover": {"background": f"{EDIT_OLIVE_HOVER_BG} !important"},
    }
    style.update(props.pop("style", {}) or {})
    props.setdefault("size", "1")
    return rx.button(rx.icon("pencil", size=14), label, variant="outline", color_scheme="gray", style=style, **props)


def delete_button(label: str = "Delete", **props) -> rx.Component:
    """Red outline button with a trash icon, the companion to edit_button."""
    props.setdefault("size", "1")
    return rx.button(rx.icon("trash-2", size=14), label, variant="outline", color_scheme="red", **props)
