# Profile HTML Render Fix v10.1

## Problem

The AED Management unit profile assembled each field card from indented multiline
HTML fragments. Blank lines between fragments could terminate Streamlit Markdown's
HTML block. The first field rendered as a card while later `<div>` elements appeared
as literal source text.

## Fix

- Build each field card as compact, continuous HTML.
- Build each section as one uninterrupted HTML string.
- Continue escaping labels and values before rendering.
- Keep `unsafe_allow_html=True` only for the final trusted layout string.
- Add a regression assertion for the compact HTML builder.

## Validation

- Python compilation passed.
- Full automated test suite passed.
- `app.py` remains absent; `streamlit_app.py` remains the only entrypoint.
