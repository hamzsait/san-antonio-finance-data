"""Seed the two NEW affiliation categories (arena_venue, charter_school) from
evidence already in the DB, ahead of the unknowns re-scrub.

Two passes, both curated (no broad LIKE auto-tagging — 'Elegant Limousine &
Charter' and the 'City of San Antonio Charter Review Commission' must NOT be
touched):

1. RECAT — existing civic_affiliations rows whose organization is a charter-
   sector org or the Spurs ownership group were filed under generic
   'civic'/'political'/'business' before these categories existed. Flip their
   category so they render in the new buckets.

2. SEED — donors whose FILER-REPORTED employer (schedule data, public record)
   is a direct-stake org: Spurs Sports & Entertainment / the Holt principal /
   the arena's design architect (leadership only for project firms), or a
   charter operator/advocacy org (any role — the org type itself is the
   contested-policy stake, per v4 instructions). Names are exact
   canonical_name strings verified against donor_identities. Rows carry the
   employer string provenance in notes; source_url only where a real public
   URL documents the org's arena role.

Deliberately NOT seeded (needs a sourced position, not just employment):
Visit San Antonio / Centro SA staff, Zachry, Goldman Sachs, Hixon,
McCombs Enterprises employment (only the already-sourced Spurs-group rows
are recategorized), rank-and-file at project firms.

Usage:
    python _seed_new_category_affiliations.py            # dry-run report
    python _seed_new_category_affiliations.py --apply    # write
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "..", "san_antonio_finance.db")
APPLY = "--apply" in sys.argv

ARCHPAPER = ("https://www.archpaper.com/2026/05/"
             "spurs-downtown-arena-overland-international-sasaki-marquee/")

# (org substring to match in existing civic_affiliations rows, new category)
RECAT = [
    ("Futuro San Antonio", "charter_school"),
    ("Charter Moms", "charter_school"),
    ("Charter Schools Now", "charter_school"),
    ("California Charter Schools Association", "charter_school"),
    ("KIPP Foundation", "charter_school"),
    ("Promesa Academy", "charter_school"),
    ("Freedom Coalition of Charter Schools", "charter_school"),
    ("Boston Preparatory Charter", "charter_school"),
    ("Choose to Succeed", "charter_school"),
    ("Great Hearts", "charter_school"),
    ("San Antonio Spurs", "arena_venue"),
    ("Overland Partners", "arena_venue"),
]

EMP_NOTE = ("Filer-reported employer in San Antonio campaign-finance "
            "schedule filings (public record).")

# (canonical_name, organization, role, category, source_url, notes)
SEED = [
    # ── Arena / Project Marvel: direct-beneficiary employment & leadership ──
    ("Holt, Peter J", "Spurs Sports & Entertainment / HOLT CAT",
     "Spurs chairman & managing partner; CEO, HOLT CAT (filer-reported: CEO, HOLT)",
     "arena_venue", None,
     EMP_NOTE + " SS&E/the Holt family is the arena's direct beneficiary."),
    ("Perez, Bobby", "Spurs Sports & Entertainment",
     "Attorney (filer-reported employer: Spurs Sports & Entertainment)",
     "arena_venue", None,
     EMP_NOTE + " SS&E is the arena's direct beneficiary."),
    ("Farias, Danny", "Spurs Sports & Entertainment",
     "Sales (filer-reported)", "arena_venue", None,
     EMP_NOTE + " SS&E is the arena's direct beneficiary."),
    ("Smith, Madison", "Overland Partners",
     "Senior Principal (filer-reported)", "arena_venue", ARCHPAPER,
     EMP_NOTE + " Overland is the design architect of the downtown Spurs arena."),
    # ── Charter-school sector: filer-reported employment at operators/advocacy ──
    ("fishman, daniel", "Choose to Succeed",
     "Staff (filer-reported: Education)", "charter_school", None,
     EMP_NOTE + " Choose to Succeed recruits charter networks to San Antonio."),
    ("Morrissey, Paul", "Compass Rose Education",
     "Founder & CEO (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Chavez, Melissa", "Compass Rose Public Schools",
     "Assistant Principal (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Chambers, Chae", "Compass Rose Public Schools",
     "Educator (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Felan, Amy Rose", "Compass Rose Public Schools",
     "Educator (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Alanis, Jessica", "Brooks Academy",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Coleman, Austin", "IDEA Public Schools",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Padron, Ana Lisa", "IDEA Public Schools",
     "Chief of Staff (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Limon, John", "IDEA Public Schools",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Ward, Zoey", "IDEA Public Schools",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Crayton, Breane", "KIPP San Antonio",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Carlisle, Geoffrey", "KIPP Texas Public Schools",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Mitchell, Kimani", "KIPP Texas",
     "Assistant Principal (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Haughton, Andre", "KIPP",
     "Principal (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Murphy, Andrew", "KIPP San Antonio",
     "Development Coordinator (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Breviglia, emily", "KIPP Texas",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Chaudoir, Verena", "Great Hearts Texas",
     "Advocacy Manager (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Kindel, Aaron", "BASIS.ed",
     "Staff (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Langston, Robert", "BASIS",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Strickland, Senait", "BASIS",
     "Educator (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Serrano, Arlene", "Jubilee Academies",
     "Coordinator (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Gonzales, Lauren", "Jubilee Academy",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Garcia, Miguel", "Jubilee Academies",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Ellis, Tanisha", "San Antonio Prep Charter School",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
    ("Waisel, Elizabeth", "Excel Academy Charter School",
     "Teacher (filer-reported)", "charter_school", None, EMP_NOTE),
]

conn = sqlite3.connect(DB, timeout=120)
cur = conn.cursor()

print(("APPLY" if APPLY else "DRY RUN") + "\n")

print("── RECAT existing civic_affiliations rows ──")
recat_n = 0
for pat, cat in RECAT:
    # Parent-org (PSO/PTA) volunteer roles stay 'civic': a parent volunteering
    # at their kid's school is civic context, not a sector stake.
    rows = cur.execute(
        "SELECT id, canonical_name, organization, category FROM civic_affiliations "
        "WHERE organization LIKE ? AND COALESCE(category,'') != ? "
        "AND organization NOT LIKE '%Parent Service%' AND organization NOT LIKE '%PTA%'",
        (f"%{pat}%", cat)).fetchall()
    for rid, name, org, old in rows:
        print(f"  [{old} -> {cat}] {name}: {org}")
        if APPLY:
            cur.execute("UPDATE civic_affiliations SET category=? WHERE id=?", (cat, rid))
        recat_n += 1

print(f"\n── SEED employment-based rows ──")
seed_n = dup_n = miss_n = 0
for name, org, role, cat, url, notes in SEED:
    known = cur.execute("SELECT 1 FROM donor_identities WHERE canonical_name=?",
                        (name,)).fetchone()
    if not known:
        print(f"  MISSING identity, skipped: {name}")
        miss_n += 1
        continue
    dup = cur.execute("SELECT 1 FROM civic_affiliations WHERE canonical_name=? AND organization=?",
                      (name, org)).fetchone()
    if dup:
        dup_n += 1
        continue
    print(f"  [{cat}] {name}: {org} — {role}")
    if APPLY:
        cur.execute("""INSERT INTO civic_affiliations
                       (canonical_name, organization, role, category, source_url, notes, added_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (name, org, role, cat, url, notes,
                     datetime.now(timezone.utc).isoformat()))
    seed_n += 1

if APPLY:
    conn.commit()
print(f"\nrecategorized: {recat_n}, seeded: {seed_n}, already present: {dup_n}, missing identity: {miss_n}")
