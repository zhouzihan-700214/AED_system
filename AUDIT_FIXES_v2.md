# v2 Audit Fixes

## Why v1 could feel like functions were missing

The v1 package passed source-oriented tests, but several tests only checked that labels
or function names existed. They did not prove that the Streamlit page could safely reach
and complete the workflow.

## Corrections

### Dashboard runtime

Removed the nested `Data source health` expander. The component now owns its single
expander and is called directly by the dashboard.

### Unit Profile Add Service

Replaced Remarks-based storage with `manual_service_records.csv`. Each event receives a
stable Service Record ID and is included in the separate OneDrive system-state archive.
The same event is visible from Unit Profile Service History and the Service Records page.
Legacy `[SERVICE]` lines already written by older drafts are still parsed for backward
compatibility.

### Safe editing

Remote workbook and system-state downloads are deferred while the user is in PM Planning,
PM Checklist, Report Issue, Issues, AED Map, Master Table edit/review, or Unit Profile Edit
Details/Add Service. The initial storage check also respects active editors when a cache
already exists.

### Deployment entrypoint

`streamlit_app.py` contains full startup composition and a visible v2 build marker. It no
longer depends on `from app import main`.

### Data ownership

`aed_data.csv` is the working cache of the official IB List and is synchronized only by the
official workbook path. It is no longer bundled into `AED_System_State.zip`.
