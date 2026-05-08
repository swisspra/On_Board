from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_live_dashboard_exposes_memory_linkage_tab():
    dashboard = (REPO_ROOT / "dashboard_live.py").read_text(encoding="utf-8")

    assert 'data-tab="links"' in dashboard
    assert 'id="linksList"' in dashboard
    assert "function renderLinks" in dashboard
    assert "buildLinkData" in dashboard
