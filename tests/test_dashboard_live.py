from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = REPO_ROOT / "dashboard_live.py"


def read_dashboard() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def test_live_dashboard_keeps_memory_linkage_view():
    dashboard = read_dashboard()

    assert "['links','Links'" in dashboard
    assert "Ticket ↔ memory links" in dashboard
    assert "fileLinks" in dashboard


def test_live_dashboard_reads_current_ticket_index_shape():
    dashboard = read_dashboard()

    assert "Array.isArray(tickets)" in dashboard
    assert "ticketList.map" in dashboard


def test_live_dashboard_stays_local_first_and_mobile_safe():
    dashboard = read_dashboard()

    assert "fonts.googleapis.com" not in dashboard
    assert "fonts.gstatic.com" not in dashboard
    assert "@media (max-width: 860px)" in dashboard
    assert "html_escape(PROJECT_ROOT.name, quote=True)" in dashboard
    assert "json.dumps(PROJECT_ROOT.name)" in dashboard
