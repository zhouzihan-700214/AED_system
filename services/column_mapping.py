"""Column names shared by the external IB List and the Streamlit application."""
from __future__ import annotations

# Keys are accepted Excel headers; values are stable application headers.
# Header matching is spacing-insensitive and case-insensitive.
EXCEL_TO_APP_COLUMNS = {
    "INSTALLATION DATE": "Installation Date",
    "Installation Date": "Installation Date",
    "RELATED OBJECTS": "Model",
    "Related Objects": "Model",
    "Model": "Model",
    "SERIAL NUMBER": "Serial Number",
    "Serial Number": "Serial Number",
    "Serial No": "Serial Number",
    "Serial No.": "Serial Number",
    "Installed Phase/Month": "Installed Phase / Month",
    "Installed Phase / Month": "Installed Phase / Month",
    "PO#": "PO Number",
    "PO Number": "PO Number",
    "Zone": "Zone",
    "Block / Locations": "Block / Locations",
    "Street Name": "Street Name",
    "Location": "Location",
    "Postal Code": "Postal Code",
    "Postal code": "Postal Code",
    "PostalCode": "Postal Code",
    "Lift Lobby": "Lift Lobby",
    "Level": "Level",
    "Adult CPR-D Padz Replacement Date": "Adult Pads Replacement Date",
    "Adult Pads Replacement Date": "Adult Pads Replacement Date",
    "Adult CPR-D Padz": "Adult Pads Expiry Date",
    "Adult Pads Expiry Date": "Adult Pads Expiry Date",
    "Adult CPR-D Padz Lot Number": "Adult Pads Lot Number",
    "Adult Pads Lot Number": "Adult Pads Lot Number",
    "Children Pedi-Padz Replacement Date": "Pediatric Pads Replacement Date",
    "Pediatric Pads Replacement Date": "Pediatric Pads Replacement Date",
    "Children Pedi-Padz": "Pediatric Pads Expiry Date",
    "Pediatric Pads Expiry Date": "Pediatric Pads Expiry Date",
    "Children Pedi-Padz Lot Number": "Pediatric Pads Lot Number",
    "Pediatric Pads Lot Number": "Pediatric Pads Lot Number",
    "Battery Replacement History": "Battery Replacement History",
    "Battery Expiry Date": "Battery Expiry Date",
    "PM Completed On": "PM Completed Date",
    "PM Completed Date": "PM Completed Date",
    "Next PM Due": "Next PM Date",
    "Next PM Date": "Next PM Date",
    "PM Interval Months": "PM Interval Months",
    "JOB TYPE": "Job Type",
    "Job Type": "Job Type",
    "Last done by": "Last Done By",
    "Last Done By": "Last Done By",
    "Service Report / e-SR": "Service Report e-SR",
    "Service Report e-SR": "Service Report e-SR",
    "Service Report eSR": "Service Report e-SR",
    "Remarks": "Remarks",
    "Patrol Schedule": "Patrol Schedule",
    "PM Schedule (H1)": "PM Schedule (H1)",
    "PM Schedule (H2)": "PM Schedule (H2)",
    "Repaired?": "Repaired?",
    "Status": "Status",
    "Latitude": "Latitude",
    "Longitude": "Longitude",
    "OneMap Address": "OneMap Address",
    "Geocoding Status": "Geocoding Status",
}


def normalise_header(value: object) -> str:
    """Return a spacing-insensitive, case-insensitive header key."""
    return " ".join(str(value).strip().split()).casefold()


_NORMALISED_MAPPING = {
    normalise_header(excel_name): app_name
    for excel_name, app_name in EXCEL_TO_APP_COLUMNS.items()
}


def clean_excel_header(value: object) -> str:
    """Remove accidental whitespace while preserving readable capitalization."""
    return " ".join(str(value).strip().split())


def map_excel_header(value: object) -> str:
    """Map a workbook header to the application name, preserving unknown fields."""
    cleaned = clean_excel_header(value)
    return _NORMALISED_MAPPING.get(normalise_header(cleaned), cleaned)
