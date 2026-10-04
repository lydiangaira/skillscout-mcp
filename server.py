"""SkillScout: an MCP server for exploring skill demand in job postings."""
import difflib
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from data_loader import load_postings, resolve_data_path

mcp = MCPServer("SkillScout")

DATA_PATH = resolve_data_path()
DF = load_postings(DATA_PATH)
SKILL_VOCAB = sorted({s for skills in DF["skills_list"] for s in skills})
LEVELS = sorted(v for v in DF["job_level"].unique() if v)

def _check_int(name: str, value: int, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ToolError(f"'{name}' must be a whole number between {low} and {high}, got {value!r}.")
    return value

def _clean_skill(skill: str) -> str:
    if not isinstance(skill, str) or not skill.strip():
        raise ToolError("'skill' must be a non-empty text value, for example 'python'.")
    skill = skill.strip().lower()
    if len(skill) > 50:
        raise ToolError("'skill' is too long. Use a short skill name such as 'python' or 'react'.")
    return skill

def _matching_skills(skill: str) -> set[str]:
    exact = {s for s in SKILL_VOCAB if s == skill}
    found = exact or {s for s in SKILL_VOCAB if skill in s}
    if found:
        return found
    close = difflib.get_close_matches(skill, SKILL_VOCAB, n=3, cutoff=0.6)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    raise ToolError(f"No postings mention the skill '{skill}'.{hint}")

def _clean_level(level: str | None) -> str | None:
    if level is None or not level.strip():
        return None
    lookup = {v.lower(): v for v in LEVELS}
    key = level.strip().lower()
    if key not in lookup:
        raise ToolError(f"Unknown level '{level}'. Valid levels are: {', '.join(LEVELS)}.")
    return lookup[key]

def _rows_with_skill(skill: str):
    wanted = _matching_skills(skill)
    mask = DF["skills_list"].apply(lambda skills: any(s in wanted for s in skills))
    return DF[mask], wanted

@mcp.tool()
def search_postings_by_skill(
    skill: Annotated[str, Field(description="A skill or technology, e.g. 'python', 'react', 'oauth'.")],
    location: Annotated[str | None, Field(description="Optional text the job location must contain, e.g. 'Nairobi' or 'Remote'.")] = None,
    level: Annotated[str | None, Field(description="Optional job level, e.g. 'Entry level'. Invalid values return the list of valid ones.")] = None,
    limit: Annotated[int, Field(description="How many postings to return, 1 to 25.", ge=1, le=25)] = 10,
) -> dict:
    
    _check_int("limit", limit, 1, 25)
    rows, wanted = _rows_with_skill(_clean_skill(skill))
    level = _clean_level(level)
    if level:
        rows = rows[rows["job_level"] == level]
    if location and location.strip():
        rows = rows[rows["job_location"].str.contains(location.strip(), case=False, regex=False)]
    total = len(rows)
    results = [
        {
            "id": int(r.id),
            "title": r.job_title,
            "company": r.company,
            "location": r.job_location,
            "level": r.job_level,
            "type": r.job_type,
            "skills": r.skills_list[:8],
        }
        for r in rows.head(limit).itertuples()
    ]
    return {
        "matched_skills": sorted(wanted)[:5],
        "total_matches": total,
        "returned": len(results),
        "results": results,
    }


@mcp.tool()
def count_postings_by_company(
    skill: Annotated[str | None, Field(description="Optional skill to filter by, e.g. 'python'. Leave empty to count all postings.")] = None,
    top_n: Annotated[int, Field(description="How many companies to return, 1 to 20.", ge=1, le=20)] = 10,
) -> dict:
    _check_int("top_n", top_n, 1, 20)
    if skill is not None and skill.strip():
        rows, wanted = _rows_with_skill(_clean_skill(skill))
    else:
        rows, wanted = DF, set()
    counts = rows["company"].value_counts().head(top_n)
    return {
        "skill_filter": sorted(wanted)[:5] or None,
        "total_postings": len(rows),
        "companies": [{"company": c, "postings": int(n)} for c, n in counts.items()],
    }


@mcp.tool()
def get_posting(
    posting_id: Annotated[int, Field(description="The 'id' from search_postings_by_skill results.", ge=0)],
) -> dict:
    if not isinstance(posting_id, int) or isinstance(posting_id, bool) or not 0 <= posting_id < len(DF):
        raise ToolError(f"No posting with id {posting_id!r}. Valid ids are 0 to {len(DF) - 1}.")
    r = DF.iloc[posting_id]
    summary = r["job_summary"]
    return {
        "id": posting_id,
        "title": r["job_title"],
        "company": r["company"],
        "location": r["job_location"],
        "level": r["job_level"],
        "type": r["job_type"],
        "skills": r["skills_list"],
        "link": r["job_link"],
        "summary": summary[:1200] + ("..." if len(summary) > 1200 else ""),
    }

if __name__ == "__main__":
    mcp.run()