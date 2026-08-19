"""
Israel/Palestine Political Money Spectrum Tracker (San Antonio)
===============================================================
Port of the Austin repo's ip_spectrum_flag.py. Flags San Antonio campaign
finance donors by their contributions to Israel/Palestine-related FEC
committees across three spectrum categories:
  1. Hawkish Pro-Israel (AIPAC-aligned network)
  2. Liberal Zionist (J Street, Bend the Arc, etc.)
  3. Pro-Palestine / Anti-Occupation

Writes ip_spectrum / ip_tier / ip_total / ip_committees to donor_identities
and ip_category to fec_committee_cache — the columns generate_profile_data.py
already reads to build each profile's ip_spectrum block (rendered by
profile_template.html's renderIPSpectrum).

Run AFTER fec_enrich.py (scores are derived from fec_contributions_raw).
Re-running is idempotent: every pass resets then rewrites all flags.

Usage:
    python sa_ip_spectrum_flag.py
"""

import io
import os
import sqlite3
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except (ValueError, AttributeError):
    pass

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "san_antonio_finance.db")

# ── Committee Definitions ────────────────────────────────────────────────
# Same list as the Austin repo's ip_spectrum_flag.py — keep the two in sync
# so the cities' spectrum cards stay comparable.

IP_COMMITTEES = {
    # === HAWKISH PRO-ISRAEL (AIPAC-aligned) ===
    # Direct AIPAC
    "C00797670": ("aipac_direct",      "hawkish_proisrael", "AIPAC PAC"),
    "C00799031": ("aipac_direct",      "hawkish_proisrael", "United Democracy Project (AIPAC Super PAC)"),
    # Pro-Israel network
    "C00699470": ("proisrael_hawkish", "hawkish_proisrael", "Pro-Israel America PAC"),
    "C00710848": ("proisrael_hawkish", "hawkish_proisrael", "DMFI PAC (Democratic Majority for Israel)"),
    "C00247403": ("proisrael_hawkish", "hawkish_proisrael", "NORPAC"),
    "C00345132": ("proisrael_hawkish", "hawkish_proisrael", "Republican Jewish Coalition PAC"),
    "C00528554": ("proisrael_hawkish", "hawkish_proisrael", "RJC Victory Fund"),
    "C00687657": ("proisrael_hawkish", "hawkish_proisrael", "American Pro-Israel PAC"),
    "C00753459": ("proisrael_hawkish", "hawkish_proisrael", "Jewish Unity PAC"),
    "C00520320": ("proisrael_hawkish", "hawkish_proisrael", "Allies of Israel PAC"),
    "C00720128": ("proisrael_hawkish", "hawkish_proisrael", "Christians for Israel PAC"),
    "C00141747": ("proisrael_hawkish", "hawkish_proisrael", "Friends of Israel PAC (FIPAC)"),

    # === LIBERAL ZIONIST ===
    "C00441949": ("liberal_zionist",   "liberal_zionist",   "JStreetPAC"),
    "C00815753": ("liberal_zionist",   "liberal_zionist",   "J Street Action Fund"),
    "C00573253": ("liberal_zionist",   "liberal_zionist",   "Bend the Arc Jewish Action PAC"),
    "C00306670": ("liberal_zionist",   "liberal_zionist",   "National Jewish Democratic Council PAC"),

    # === PRO-PALESTINE / ANTI-OCCUPATION ===
    "C00747691": ("pro_palestine",     "pro_palestine",     "JVP Action PAC (Jewish Voice for Peace)"),
    "C00937888": ("pro_palestine",     "pro_palestine",     "PAL PAC (Peace, Accountability & Leadership)"),
    "C00379891": ("pro_palestine",     "pro_palestine",     "Americans for a Palestinian State"),
}
# Mapping: committee_id -> (ip_category, ip_spectrum, display_name)


def add_columns(conn):
    """Add IP columns to donor_identities and fec_committee_cache if missing."""
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(donor_identities)")
    existing = {row[1] for row in cur.fetchall()}
    new_cols = [
        ("ip_spectrum",    "TEXT"),
        ("ip_tier",        "INTEGER"),
        ("ip_total",       "REAL DEFAULT 0"),
        ("ip_committees",  "TEXT"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing:
            cur.execute(f"ALTER TABLE donor_identities ADD COLUMN {col_name} {col_type}")
            print(f"  Added donor_identities.{col_name}")
        else:
            print(f"  Column donor_identities.{col_name} already exists")

    cur.execute("PRAGMA table_info(fec_committee_cache)")
    existing_cc = {row[1] for row in cur.fetchall()}
    if "ip_category" not in existing_cc:
        cur.execute("ALTER TABLE fec_committee_cache ADD COLUMN ip_category TEXT")
        print("  Added fec_committee_cache.ip_category")
    else:
        print("  Column fec_committee_cache.ip_category already exists")

    conn.commit()


def flag_committees(conn):
    """Set ip_category on fec_committee_cache for known IP committees."""
    cur = conn.cursor()
    cur.execute("UPDATE fec_committee_cache SET ip_category = NULL")
    flagged = 0
    for cid, (category, _, name) in IP_COMMITTEES.items():
        cur.execute(
            "UPDATE fec_committee_cache SET ip_category = ? WHERE committee_id = ?",
            (category, cid),
        )
        if cur.rowcount > 0:
            print(f"  Flagged {cid} ({name}) -> {category}")
            flagged += 1
        else:
            print(f"  Committee {cid} ({name}) not in cache (no SA donors gave to it)")
    conn.commit()
    print(f"  Total committees flagged in cache: {flagged}")


def score_donors(conn):
    """Score every donor based on their FEC contributions to IP committees."""
    cur = conn.cursor()

    cur.execute("""
        UPDATE donor_identities
        SET ip_spectrum = NULL, ip_tier = NULL, ip_total = 0, ip_committees = NULL
    """)

    cid_list = list(IP_COMMITTEES.keys())
    placeholders = ",".join(["?"] * len(cid_list))

    cur.execute(f"""
        SELECT
            r.donor_id,
            r.committee_id,
            SUM(r.contribution_amount) AS total_to_committee
        FROM fec_contributions_raw r
        WHERE r.committee_id IN ({placeholders})
        GROUP BY r.donor_id, r.committee_id
    """, cid_list)

    donor_data = {}  # donor_id -> {spectrum -> total, committees: set}
    for donor_id, committee_id, total in cur.fetchall():
        if donor_id not in donor_data:
            donor_data[donor_id] = {
                "hawkish_proisrael": 0.0,
                "liberal_zionist": 0.0,
                "pro_palestine": 0.0,
                "committees": set(),
                "total": 0.0,
            }
        _, spectrum, _ = IP_COMMITTEES[committee_id]
        donor_data[donor_id][spectrum] += total
        donor_data[donor_id]["committees"].add(committee_id)
        donor_data[donor_id]["total"] += total

    print(f"\n  Found {len(donor_data)} donors with IP-committee contributions")

    updated = 0
    for donor_id, data in donor_data.items():
        # Spectrum = whichever category received the most $
        spectrum_totals = {
            "hawkish_proisrael": data["hawkish_proisrael"],
            "liberal_zionist": data["liberal_zionist"],
            "pro_palestine": data["pro_palestine"],
        }
        spectrum = max(spectrum_totals, key=spectrum_totals.get)

        # Tier assignment:
        # 1 = gave to AIPAC direct (C00797670 or C00799031) or gave to 3+ IP committees
        # 2 = gave to 2+ IP committees (multi-PAC network donor)
        # 3 = gave to exactly 1 IP committee
        committees = data["committees"]
        aipac_direct = {"C00797670", "C00799031"}
        if committees & aipac_direct or len(committees) >= 3:
            tier = 1
        elif len(committees) >= 2:
            tier = 2
        else:
            tier = 3

        committee_str = ",".join(sorted(committees))

        cur.execute("""
            UPDATE donor_identities
            SET ip_spectrum = ?, ip_tier = ?, ip_total = ?, ip_committees = ?
            WHERE donor_id = ?
        """, (spectrum, tier, data["total"], committee_str, donor_id))
        updated += cur.rowcount

    conn.commit()
    print(f"  Updated {updated} donor records with IP spectrum scores")
    return donor_data


def report_summary(conn):
    """Print summary statistics."""
    cur = conn.cursor()

    print("\n" + "=" * 70)
    print("ISRAEL/PALESTINE SPECTRUM — SUMMARY REPORT")
    print("=" * 70)

    cur.execute("""
        SELECT ip_spectrum, COUNT(*), SUM(ip_total), AVG(ip_total)
        FROM donor_identities
        WHERE ip_spectrum IS NOT NULL
        GROUP BY ip_spectrum
        ORDER BY SUM(ip_total) DESC
    """)
    print(f"\n{'Category':<25} {'Donors':>8} {'Total $':>14} {'Avg $':>12}")
    print("-" * 62)
    for row in cur.fetchall():
        print(f"{row[0]:<25} {row[1]:>8,} {row[2]:>14,.2f} {row[3]:>12,.2f}")

    cur.execute("""
        SELECT ip_tier, COUNT(*), SUM(ip_total)
        FROM donor_identities
        WHERE ip_spectrum IS NOT NULL
        GROUP BY ip_tier
        ORDER BY ip_tier
    """)
    print(f"\n{'Tier':<35} {'Donors':>8} {'Total $':>14}")
    print("-" * 60)
    tier_labels = {
        1: "Tier 1 (AIPAC direct / 3+ cmtes)",
        2: "Tier 2 (multi-PAC network)",
        3: "Tier 3 (single PAC)",
    }
    for row in cur.fetchall():
        label = tier_labels.get(row[0], f"Tier {row[0]}")
        print(f"{label:<35} {row[1]:>8,} {row[2]:>14,.2f}")

    for spectrum in ["hawkish_proisrael", "liberal_zionist", "pro_palestine"]:
        cur.execute("""
            SELECT canonical_name, ip_total, ip_tier, ip_committees
            FROM donor_identities
            WHERE ip_spectrum = ?
            ORDER BY ip_total DESC
            LIMIT 10
        """, (spectrum,))
        rows = cur.fetchall()
        if rows:
            print(f"\n--- Top 10 donors: {spectrum.upper()} ---")
            print(f"{'Name':<40} {'IP Total $':>12} {'Tier':>5}  Committees")
            print("-" * 90)
            for r in rows:
                cids = r[3].split(",") if r[3] else []
                cnames = []
                for cid in cids:
                    if cid in IP_COMMITTEES:
                        cnames.append(IP_COMMITTEES[cid][2][:30])
                print(f"{r[0][:39]:<40} {r[1]:>12,.2f} {r[2]:>5}  {', '.join(cnames)}")


def report_candidates(conn):
    """Per-council-member rollup: flagged donors and their local giving.

    Uses the same base filter as generate_profile_data.py (superseded rows
    dropped, refunds netted via balanced_amount) minus the per-slug recipient
    aliases / year floors — console-report precision, not publication data.
    """
    cur = conn.cursor()

    print("\n" + "=" * 70)
    print("PER-CANDIDATE IP SPECTRUM ROLLUP")
    print("=" * 70)

    cur.execute("""
        SELECT
            cf.filer_slug,
            di.ip_spectrum,
            COUNT(DISTINCT di.donor_id) AS n_donors,
            SUM(COALESCE(cf.balanced_amount, cf.amount_real)) AS local_total
        FROM campaign_finance cf
        JOIN donor_identities di ON cf.donor_id = di.donor_id
        JOIN council_members cm ON cm.slug = cf.filer_slug
        WHERE di.ip_spectrum IS NOT NULL
          AND cf.txn_type = 'contribution'
          AND cf.superseded_by IS NULL
          AND COALESCE(cf.balanced_amount, cf.amount_real) > 0
        GROUP BY cf.filer_slug, di.ip_spectrum
        ORDER BY cf.filer_slug, di.ip_spectrum
    """)
    rows = cur.fetchall()
    if not rows:
        print("  No flagged donors linked to tracked candidates.")
        return

    print(f"\n{'Candidate':<20} {'Spectrum':<22} {'Donors':>8} {'Local $':>12}")
    print("-" * 66)
    for slug, spectrum, n, local in rows:
        print(f"{slug:<20} {spectrum:<22} {n:>8,} {local or 0:>12,.2f}")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    print("=" * 70)
    print("STEP 1: Adding columns to donor_identities and fec_committee_cache")
    print("=" * 70)
    add_columns(conn)

    print("\n" + "=" * 70)
    print("STEP 2: Flagging IP committees in fec_committee_cache")
    print("=" * 70)
    flag_committees(conn)

    print("\n" + "=" * 70)
    print("STEP 3: Scoring all donors by IP spectrum")
    print("=" * 70)
    score_donors(conn)

    report_candidates(conn)
    report_summary(conn)

    conn.close()
    print("\n\nDone. All IP spectrum data written to san_antonio_finance.db.")


if __name__ == "__main__":
    main()
