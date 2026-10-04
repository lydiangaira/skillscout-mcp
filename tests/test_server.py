import os
from pathlib import Path

os.environ["SKILLSCOUT_DATA"] = str(Path(__file__).parent.parent / "data" / "sample_postings.csv")

import pytest  

import server  
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

def test_search_finds_python_postings():
    out = server.search_postings_by_skill("python", limit=5)
    assert out["total_matches"] > 0
    assert out["returned"] <= 5
    assert all("python" in r["skills"] for r in out["results"])

def test_search_is_case_insensitive_and_trims():
    assert server.search_postings_by_skill("  PyThOn ")["total_matches"] > 0

def test_search_filters_by_level_and_location():
    out = server.search_postings_by_skill("python", level="entry level", location="kenya")
    assert out["total_matches"] >= 1
    assert all(r["level"] == "Entry level" and "Kenya" in r["location"] for r in out["results"])

def test_typo_suggests_close_match():
    with pytest.raises(ToolError, match="Did you mean: python"):
        server.search_postings_by_skill("pyhton")

def test_unknown_skill_errors_clearly():
    with pytest.raises(ToolError, match="No postings mention"):
        server.search_postings_by_skill("cobol-9000")

def test_empty_skill_rejected():
    with pytest.raises(ToolError, match="non-empty"):
        server.search_postings_by_skill("   ")

def test_bad_level_lists_valid_values():
    with pytest.raises(ToolError, match="Valid levels are"):
        server.search_postings_by_skill("python", level="wizard")

@pytest.mark.parametrize("limit", [0, 26, -1])
def test_limit_out_of_range(limit):
    with pytest.raises(ToolError, match="between 1 and 25"):
        server.search_postings_by_skill("python", limit=limit)

def test_count_by_company_orders_results():
    out = server.count_postings_by_company(top_n=3)
    counts = [c["postings"] for c in out["companies"]]
    assert len(counts) == 3 and counts == sorted(counts, reverse=True)

def test_count_by_company_with_skill_filter():
    out = server.count_postings_by_company(skill="rust")
    assert {c["company"] for c in out["companies"]} == {"Ironwood Systems", "Ferrous Labs"}

def test_top_n_out_of_range():
    with pytest.raises(ToolError, match="between 1 and 20"):
        server.count_postings_by_company(top_n=21)

def test_get_posting_roundtrip():
    first = server.search_postings_by_skill("rust", limit=1)["results"][0]
    full = server.get_posting(first["id"])
    assert full["title"] == first["title"] and "summary" in full

def test_get_posting_bad_id():
    with pytest.raises(ToolError, match="No posting with id"):
        server.get_posting(9999)