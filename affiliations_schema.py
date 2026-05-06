"""
affiliations_schema.py
Create / migrate the donor_affiliations and donor_affiliation_evidence tables.

Idempotent — re-runnable. Creates tables if missing, and exposes a
clear_category() helper used by the integrator before re-importing a
category's findings.

Tables:
    donor_affiliations:
        Per-donor, per-category roll-up. Unique on (donor_id, category, label)
        so re-runs UPSERT cleanly.

    donor_affiliation_evidence:
        Per-finding receipts. FK to donor_affiliations.affiliation_id.
        Each row is a single source artefact (an FEC contribution, a TEC
        contribution, a civic-affiliations match, an employer match, etc.)
        with enough provenance for a reader to verify.

Categories (canonical strings):
    aipac, adl, zionist_general,
    oil_gas, real_estate, mic,
    fec_partisan, tec_partisan
"""

from __future__ import annotations
import pathlib
import sqlite3
import sys

DB_PATH = pathlib.Path(__file__).parent / "san_antonio_finance.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS donor_affiliations (
    affiliation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id         TEXT    NOT NULL,
    category         TEXT    NOT NULL,
    label            TEXT    NOT NULL,
    total_amount     REAL,
    confidence       TEXT,                 -- 'high' / 'medium' / 'low'
    first_seen       TEXT,
    last_seen        TEXT,
    notes            TEXT,
    sensitive        INTEGER DEFAULT 0,    -- 1 = flagged for human review before publish
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(donor_id, category, label)
);
CREATE INDEX IF NOT EXISTS idx_aff_donor    ON donor_affiliations(donor_id);
CREATE INDEX IF NOT EXISTS idx_aff_category ON donor_affiliations(category);

CREATE TABLE IF NOT EXISTS donor_affiliation_evidence (
    evidence_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliation_id    INTEGER NOT NULL,
    source            TEXT    NOT NULL,    -- e.g. 'FEC schedule_a', 'TEC bulk', 'employer_match', 'civic_affiliations'
    source_url        TEXT,                -- direct link to the source record where available
    evidence_text     TEXT,                -- human-readable summary
    contribution_id   TEXT,                -- pointer back to fec_contributions_raw.id, texas_contributions_raw.id, etc.
    committee_id      TEXT,                -- FEC committee id, when applicable
    committee_name    TEXT,
    amount            REAL,
    date              TEXT,
    raw_data          TEXT,                -- JSON blob of the underlying row, for full transparency
    rule              TEXT,                -- the matching rule that fired (e.g. 'fec_committee_id_match', 'employer_keyword: lockheed')
    FOREIGN KEY(affiliation_id) REFERENCES donor_affiliations(affiliation_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ev_aff       ON donor_affiliation_evidence(affiliation_id);
CREATE INDEX IF NOT EXISTS idx_ev_committee ON donor_affiliation_evidence(committee_id);
"""


VALID_CATEGORIES = {
    "aipac", "adl", "zionist_general",
    "oil_gas", "real_estate", "mic",
    "fec_partisan", "tec_partisan",
}


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def clear_category(conn: sqlite3.Connection, category: str) -> tuple[int, int]:
    """Delete all affiliations + evidence for a given category. Returns
    (affiliations_deleted, evidence_deleted)."""
    if category not in VALID_CATEGORIES:
        raise ValueError(f"unknown category {category!r}; valid: {sorted(VALID_CATEGORIES)}")
    cur = conn.cursor()
    aff_ids = [r[0] for r in cur.execute(
        "SELECT affiliation_id FROM donor_affiliations WHERE category=?", (category,)
    ).fetchall()]
    if not aff_ids:
        return 0, 0
    placeholders = ",".join("?" * len(aff_ids))
    ev_count = cur.execute(
        f"DELETE FROM donor_affiliation_evidence WHERE affiliation_id IN ({placeholders})",
        aff_ids,
    ).rowcount
    aff_count = cur.execute(
        f"DELETE FROM donor_affiliations WHERE affiliation_id IN ({placeholders})",
        aff_ids,
    ).rowcount
    conn.commit()
    return aff_count, ev_count


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        ensure_schema(conn)
        n_aff = conn.execute("SELECT COUNT(*) FROM donor_affiliations").fetchone()[0]
        n_ev  = conn.execute("SELECT COUNT(*) FROM donor_affiliation_evidence").fetchone()[0]
        print(f"[schema] donor_affiliations={n_aff} rows  donor_affiliation_evidence={n_ev} rows")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
