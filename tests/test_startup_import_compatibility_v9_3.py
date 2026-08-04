from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_entrypoints_do_not_import_user_is_editing() -> None:
    for filename in ("app.py", "streamlit_app.py"):
        source = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
        assert "from utils.streamlit_utils import user_is_editing" not in source
        assert "import user_is_editing" not in source
        assert "def user_is_editing() -> bool:" in source
        assert '"Issues",' in source
