"""Central AED field definitions shared by table, detail and Add AED forms."""
from __future__ import annotations

TABLE_EDITABLE_COLUMNS = [
    "Model",
    "Block / Locations",
    "Street Name",
    "Postal Code",
    "Level",
    "Lift Lobby",
    "Adult Pads Expiry Date",
    "Adult Pads Lot Number",
    "Pediatric Pads Expiry Date",
    "Pediatric Pads Lot Number",
    "Battery Expiry Date",
    "PM Completed Date",
    "Next PM Date",
    "Job Type",
    "Last Done By",
    "Service Report e-SR",
    "Repaired?",
]

TABLE_READ_ONLY_COLUMNS = [
    "Serial Number",
    "Location",
    "Latitude",
    "Longitude",
    "OneMap Address",
    "Geocoding Status",
]

DETAIL_ONLY_COLUMNS = [
    "Installation Date",
    "Installed Phase / Month",
    "PO Number",
    "Zone",
    "Adult Pads Replacement Date",
    "Pediatric Pads Replacement Date",
    "Battery Replacement History",
    "Remarks",
]

DETAIL_EDITABLE_COLUMNS = [
    "Installation Date",
    "Model",
    "Installed Phase / Month",
    "PO Number",
    "Zone",
    "Block / Locations",
    "Street Name",
    "Postal Code",
    "Level",
    "Lift Lobby",
    "Adult Pads Replacement Date",
    "Adult Pads Expiry Date",
    "Adult Pads Lot Number",
    "Pediatric Pads Replacement Date",
    "Pediatric Pads Expiry Date",
    "Pediatric Pads Lot Number",
    "Battery Replacement History",
    "Battery Expiry Date",
    "PM Completed Date",
    "Next PM Date",
    "Job Type",
    "Last Done By",
    "Service Report e-SR",
    "Repaired?",
    "Remarks",
]

ADD_FIELDS = ["Serial Number", *DETAIL_EDITABLE_COLUMNS]

REQUIRED_FIELDS = {
    "Serial Number",
    "Model",
    "Block / Locations",
    "Street Name",
    "Postal Code",
    "Next PM Date",
}

DATE_FIELDS = {
    "Installation Date",
    "Adult Pads Replacement Date",
    "Adult Pads Expiry Date",
    "Pediatric Pads Replacement Date",
    "Pediatric Pads Expiry Date",
    "Battery Expiry Date",
    "PM Completed Date",
    "Next PM Date",
}

JOB_TYPE_OPTIONS = [
    "",
    "PM",
    "Commissioning",
    "Repair",
    "Incoming Check",
    "Outgoing Check",
    "Activation",
    "Consumable Replenishment",
    "Other",
    # Combined PM types are appended at the end, while PM and Commissioning
    # remain in their original positions. Existing workbook wording is kept.
    "PM+batt",
    "PM+glass",
    "PM +batt +glass",
]

REPAIRED_OPTIONS = ["", "Yes", "No", "Not applicable"]

FIELD_LABELS = {
    "Model": "Model / Related Object",
    "Job Type": "Service Type",
    "Service Report e-SR": "Service Report / e-SR",
    "Installed Phase / Month": "Installed Phase / Month",
    "PO Number": "PO Number",
}

APP_TO_EXCEL_COLUMNS = {
    "Installation Date": "INSTALLATION DATE",
    "Model": "RELATED OBJECTS",
    "Serial Number": "SERIAL NUMBER",
    "Installed Phase / Month": "Installed Phase/Month",
    "PO Number": "PO#",
    "Zone": "Zone",
    "Block / Locations": "Block / Locations",
    "Street Name": "Street Name",
    "Postal Code": "Postal Code",
    "Lift Lobby": "Lift Lobby",
    "Level": "Level",
    "Adult Pads Replacement Date": "Adult CPR-D Padz Replacement Date",
    "Adult Pads Expiry Date": "Adult CPR-D Padz",
    "Adult Pads Lot Number": "Adult CPR-D Padz Lot Number",
    "Pediatric Pads Replacement Date": "Children Pedi-Padz Replacement Date",
    "Pediatric Pads Expiry Date": "Children Pedi-Padz",
    "Pediatric Pads Lot Number": "Children Pedi-Padz Lot Number",
    "Battery Replacement History": "Battery Replacement History",
    "Battery Expiry Date": "Battery Expiry Date",
    "PM Completed Date": "PM Completed On",
    "Next PM Date": "Next PM Due",
    "Job Type": "JOB TYPE",
    "Last Done By": "Last done by",
    "Service Report e-SR": "Service Report / e-SR",
    "Remarks": "Remarks",
    "Repaired?": "Repaired?",
}
