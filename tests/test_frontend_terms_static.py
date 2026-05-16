from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_terms_page_owns_scroll_container_under_locked_body() -> None:
    terms_page = (REPO_ROOT / "frontend/app/terms/page.tsx").read_text()
    root_layout = (REPO_ROOT / "frontend/app/layout.tsx").read_text()

    assert "h-screen overflow-hidden" in root_layout
    assert '<main className="h-screen overflow-y-auto bg-background font-ui text-on-surface custom-scrollbar">' in terms_page
