from datetime import date
from pathlib import Path

import pandas as pd

from services import pm_service


def test_validate_submission() -> None:
    errors = pm_service.validate_submission(
        technician="",
        customer_location=None,
        postal_code="",
        serial_number="",
        confirmed=False,
    )
    assert len(errors) == 5


def test_build_response_is_independent_of_streamlit_state() -> None:
    response = pm_service.build_response(
        service_date=date(2026, 7, 28),
        technician="Zihan",
        service_type="Preventive Maintenance (PM)",
        customer_location="SCDF / SAL",
        postal_code="123456",
        lift_lobby="A",
        loaner_unit="No",
        cabinet_inspection="Pass",
        cabinet_alarm="Pass",
        serial_number="AED-001",
        physical_condition="Pass",
        self_test_result="Pass",
        battery_expiry=None,
        aed_cover="Pass",
        adult_pads_expiry=None,
        adult_pads_lot="LOT-A",
        adult_pads_within_expiry="Yes",
        pediatric_pads_expiry=None,
        pediatric_pads_lot="LOT-P",
        pediatric_pads_within_expiry="Yes",
        aed_signage="Yes",
        final_check="Yes",
        aed_location="Test Lobby",
        original_serial_number="AED-001",
    )

    assert response["AED Location"] == "Test Lobby"
    assert response["Original Serial Number"] == "AED-001"
    assert response["Service Date"] == "28-07-2026"


def test_update_selected_aed_uses_excel_transaction(monkeypatch) -> None:
    from services import aed_repository

    dataframe = pd.DataFrame([
        {
            "Serial Number": "AED-001", "Postal Code": "123456", "Lift Lobby": "A",
            "Battery Expiry Date": "", "Adult Pads Expiry Date": "",
            "Adult Pads Lot Number": "", "Pediatric Pads Expiry Date": "",
            "Pediatric Pads Lot Number": "", "PM Completed Date": "",
            "Next PM Date": "", "Job Type": "", "Last Done By": "",
            "Service Report e-SR": "", "PM Interval Months": "12",
        }
    ])
    values = {
        "AED Serial Number": "AED-001", "Postal Code": "123456", "Lift Lobby": "A",
        "Battery Expiry Date": "28-07-2031", "Adult Pads Expiry Date": "28-07-2028",
        "Adult Pads Lot Number": "LOT-A", "Pediatric Pads Expiry Date": "28-07-2028",
        "Pediatric Pads Lot Number": "LOT-P", "Service Date": "28-07-2026",
        "Service Type": "Preventive Maintenance (PM)", "Self Test Result": "Pass",
        "Technician": "Zihan",
    }
    captured = {}

    class Result:
        status = "updated"
        success = True

    def fake_update_unit(**kwargs):
        captured.update(kwargs)
        return Result()

    monkeypatch.setattr(aed_repository, "update_unit", fake_update_unit)
    result = pm_service.update_selected_aed(
        dataframe, 0, values, user="Zihan", session_id="session-1"
    )

    assert result.status == "updated"
    assert captured["serial_number"] == "AED-001"
    assert captured["changes"]["Next PM Date"] == "28-07-2027"
    assert captured["changes"]["Last Done By"] == "Zihan"
    assert captured["source_page"] == "PM Checklist"

