"""Refresh sanantonio_landing.json cards from built <slug>_data.json files.

Flips `soon` cards live and refreshes stale stats on already-live cards
(raised / donors / empPct / topGroups) so the landing always matches the
published profiles. Run after build_candidate.py, before publish.
"""
import json
import sys

SLUGS = sys.argv[1:] or ["jones", "galvan", "kaur"]
LANDING = "sanantonio/sanantonio_landing.json"

landing = json.load(open(LANDING, encoding="utf-8"))

def fmt_money(n):
    return f"${n/1e6:.1f}M" if n >= 1e6 else f"${round(n/1e3)}K"

for m in landing["candidates"]:
    slug = m["slug"]
    if slug not in SLUGS:
        continue
    try:
        d = json.load(open(f"sanantonio/{slug}_data.json", encoding="utf-8"))
    except FileNotFoundError:
        continue
    hero = d["hero"]
    groups = [g for g in d["interest_groups"] if g["label"] != "Unknown"][:4]
    top = max(g["total"] for g in groups) if groups else 1
    m.pop("soon", None)
    m["href"] = f"/sanantonio/{slug}/"
    m["raised"] = fmt_money(hero["total_raised"])
    m["donors"] = f"{hero['unique_donors']:,}"
    m["empPct"] = f"{hero['employer_affiliated_pct']:.1f}%"
    m["topGroups"] = [{"label": g["label"], "amt": fmt_money(g["total"]),
                       "w": max(1, round(100 * g["total"] / top))} for g in groups]
    print(f"{slug}: {m['raised']} / {m['donors']} donors / {m['empPct']} affiliated")

json.dump(landing, open(LANDING, "w", encoding="utf-8", newline="\n"),
          indent=1, ensure_ascii=False)
print("landing updated")
