from __future__ import annotations

from html import escape
from typing import Iterable

import streamlit as st


Capability = tuple[str, str]


def page_header(
    title: str,
    subtitle: str = "",
    *,
    eyebrow: str = "AED OPERATIONS SYSTEM",
    chip: str = "",
    capabilities: Iterable[Capability] | None = None,
) -> None:
    """Render the shared Lesson-style hero and optional capability cards."""

    safe_title = escape(title)
    safe_subtitle = escape(subtitle)
    safe_eyebrow = escape(eyebrow)
    safe_chip = escape(chip)

    chip_html = (
        f'<span class="aed-chip">{safe_chip}</span>'
        if safe_chip
        else ""
    )

    st.markdown(
        f"""
        <section class="aed-hero">
            <div class="aed-hero-eyebrow">{safe_eyebrow}</div>
            <h1>{safe_title}</h1>
            <p>{safe_subtitle}</p>
            {chip_html}
        </section>
        """,
        unsafe_allow_html=True,
    )

    card_items = list(capabilities or [])
    if not card_items:
        return

    cards_html = "".join(
        (
            '<div class="aed-capability-card">'
            f"<strong>{escape(card_title)}</strong>"
            f"<span>{escape(card_text)}</span>"
            "</div>"
        )
        for card_title, card_text in card_items
    )

    st.markdown(
        f'<div class="aed-capability-cards">{cards_html}</div>',
        unsafe_allow_html=True,
    )


def dashboard_hero(
    title: str,
    subtitle: str,
    *,
    status_text: str,
    source_text: str,
) -> None:
    """Render the more prominent home-page hero used by the management hub."""

    st.markdown(
        f"""
        <section class="dashboard-hero">
            <div class="dashboard-hero-grid">
                <div>
                    <div class="dashboard-kicker">AED OPERATIONS · COMMAND VIEW</div>
                    <h1>{escape(title)}</h1>
                    <p>{escape(subtitle)}</p>
                </div>
                <div class="dashboard-system-state">
                    <span><i></i>{escape(status_text)}</span>
                    <small>{escape(source_text)}</small>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def section_label(text: str) -> None:
    """Render a small uppercase section label."""

    st.markdown(
        f'<div class="aed-section-label">{escape(text)}</div>',
        unsafe_allow_html=True,
    )


def note_panel(label: str, text: str) -> None:
    """Render a compact contextual note panel."""

    st.markdown(
        '<div class="aed-note-panel">'
        f"<strong>{escape(label)}</strong>"
        f"{escape(text)}"
        "</div>",
        unsafe_allow_html=True,
    )


def empty_state(message: str) -> None:
    """Render a consistent empty-state message."""

    st.info(message)
