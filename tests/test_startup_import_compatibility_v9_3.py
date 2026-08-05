from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_single_entrypoint_does_not_import_user_is_editing() -> None:
    assert not (PROJECT_ROOT / "app.py").exists()
    source = (PROJECT_ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    assert "from utils.streamlit_utils import user_is_editing" not in source
    assert "import user_is_editing" not in source
    assert "def user_is_editing() -> bool:" in source
    assert '"Issues",' in source


def test_single_entrypoint_uses_module_imports_for_runtime_services() -> None:
    source = (PROJECT_ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    assert "import config as config" in source
    assert "import services.aed_repository as aed_repository" in source
    assert "from services.aed_repository import" not in source
    assert "from config import" not in source
