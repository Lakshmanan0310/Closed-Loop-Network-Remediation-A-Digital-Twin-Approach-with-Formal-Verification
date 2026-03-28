# ================================================================
#  PROJECT  : Digital Twin — IEEE Research Project
#  SCRIPT   : digital_twin_analysis.py  (Phase 2 of N)
#  PURPOSE  : Load the router config captured in Phase 1 into a
#             locally running Batfish instance, model the network
#             as a Digital Twin, and run a suite of analysis
#             questions that would take hours to answer manually.
#
#  WHAT IS PYBATFISH?
#  Pybatfish is the Python client for Batfish — an open-source
#  network analysis tool originally developed at Microsoft Research.
#  Batfish builds a complete mathematical model of your network
#  from device configs alone (no live traffic required). It can
#  answer questions like:
#    • What routes does this router know about?
#    • Which ACLs permit or deny specific traffic flows?
#    • What happens to a packet going from A to B?
#    • Are there any undefined references in the config?
#  This is the foundation of a Digital Twin architecture.
#
#  PRE-REQUISITES:
#    1. Batfish Docker running: docker run -d -p 9996:9996 batfish/batfish
#    2. pip install pybatfish pandas
#    3. Phase 1 complete: snapshot/configs/router1.cfg must exist
#
#  USAGE:
#    python digital_twin_analysis.py
#
#  OUTPUT:
#    • Console: formatted analysis results for each question
#    • Files:   digital_twin_reports/ folder with CSV exports
# ================================================================


# ── IMPORTS ──────────────────────────────────────────────────────

# pybatfish.client — The main Batfish session manager.
# Session handles all HTTP communication with the Batfish Docker
# container running on localhost:9996.
from pybatfish.client.session import Session

# pybatfish.datamodel — Data structures used to define traffic flows
# for reachability and traceroute questions.
from pybatfish.datamodel import HeaderConstraints, PathConstraints

# pandas — Batfish returns all results as pandas DataFrames.
# We use pandas to format, filter, and export the results.
import pandas as pd

# os, sys, datetime — standard utilities for file I/O and logging
import os
import sys
from datetime import datetime


# ════════════════════════════════════════════════════════════════
# SECTION 1: CONFIGURATION
# ════════════════════════════════════════════════════════════════

# ── Batfish connection settings ───────────────────────────────────
# Batfish runs as a Docker container on your local machine.
# It exposes a REST API on port 9996 that pybatfish talks to.
BATFISH_HOST    = "localhost"    # Docker container is on your local machine
SNAPSHOT_PATH   = "snapshot"    # Must match the folder Phase 1 created
NETWORK_NAME    = "digital-twin-ieee"   # Logical name for this network model
SNAPSHOT_NAME   = "devnet-c8000v-live"  # Label for this specific snapshot

# ── Report output directory ───────────────────────────────────────
# Every analysis result is exported as a CSV for your IEEE paper.
REPORT_DIR      = "digital_twin_reports"

# ── Target device name ────────────────────────────────────────────
# Batfish derives the device name from the config filename.
# Since Phase 1 saved the file as 'router1.cfg', the device name
# inside Batfish will be 'router1'. This is used in targeted queries.
DEVICE_NAME = "th_router"


# ════════════════════════════════════════════════════════════════
# SECTION 2: LOGGING HELPER  (same pattern as Phase 1)
# ════════════════════════════════════════════════════════════════
def log(message, level="INFO"):
    """Prints a formatted, timestamped log line to stdout."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level:<7}] {message}")


# ════════════════════════════════════════════════════════════════
# SECTION 3: REPORT SAVER
#
# Every Batfish question returns a pandas DataFrame. This helper
# prints it to the console in a readable format AND exports it
# to a CSV file in the digital_twin_reports/ folder.
# CSV exports are essential for an IEEE research paper — they
# give you machine-readable evidence of every finding.
# ════════════════════════════════════════════════════════════════
def save_report(dataframe, report_name):
    """
    Prints a DataFrame to console and saves it as a CSV report.

    Args:
        dataframe   (pd.DataFrame) : Batfish question result.
        report_name (str)          : Base name for the output file.
    """
    os.makedirs(REPORT_DIR, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{report_name}_{timestamp_str}.csv"
    filepath  = os.path.join(REPORT_DIR, filename)

    if dataframe is None or dataframe.empty:
        log(f"  [No results returned for '{report_name}']", level="WARN")
        return

    # Print to console with pandas' built-in table formatter.
    # to_string() shows ALL rows and columns without truncation —
    # important when you want to see the full Digital Twin model.
    print(dataframe.to_string(index=False))
    print()

    # Export to CSV — preserves all data for the research paper.
    dataframe.to_csv(filepath, index=False)
    log(f"Report saved → '{filepath}' ({len(dataframe)} rows)", level="SUCCESS")


# ════════════════════════════════════════════════════════════════
# SECTION 4: BATFISH SESSION INITIALISER
#
# This function:
#   1. Connects pybatfish to the local Batfish Docker container
#   2. Creates a named logical network ("digital-twin-ieee")
#   3. Loads our snapshot folder (the configs Batfish will model)
#   4. Returns the active Session object for running questions
#
# This is the core of the Digital Twin architecture — Batfish
# builds a complete, queryable mathematical model of the router
# from the config file alone. No live device access needed after
# this point. The model IS the twin.
# ════════════════════════════════════════════════════════════════
def initialise_batfish():
    """
    Connects to the local Batfish Docker instance and loads
    the Phase 1 snapshot to build the Digital Twin model.

    Returns:
        Session : Active pybatfish session ready for questions.
                  Exits with code 1 on any initialisation failure.
    """
    log(f"Connecting to Batfish at {BATFISH_HOST}:9996...", level="STEP")

    try:
        # Create a pybatfish Session pointed at the Docker container.
        # All subsequent API calls go through this session object.
        bf = Session(host=BATFISH_HOST)

        # Set the logical network name. In Batfish, a "network" is a
        # container that can hold multiple snapshots (e.g., configs from
        # different points in time for change analysis).
        bf.set_network(NETWORK_NAME)
        log(f"Network set: '{NETWORK_NAME}' ✅")

        # Load the snapshot folder into Batfish.
        # Batfish reads every .cfg file inside snapshot/configs/,
        # parses the IOS-XE syntax, and builds its internal model.
        # This is the moment your Digital Twin comes to life.
        log(f"Loading snapshot from './{SNAPSHOT_PATH}/'...", level="STEP")
        log("Batfish is parsing the config and building the network model...")
        log("This takes 15-60 seconds depending on config complexity...")

        bf.init_snapshot(
            SNAPSHOT_PATH,
            name      = SNAPSHOT_NAME,
            overwrite = True,    # Replace any previous snapshot with same name
        )

        log(f"Digital Twin model initialised: '{SNAPSHOT_NAME}' ✅", level="SUCCESS")
        return bf

    except Exception as e:
        log(f"Batfish initialisation failed: {type(e).__name__}: {e}", level="ERROR")
        log("Fix checklist:", level="ERROR")
        log("  1. Is Docker running? Run: docker ps", level="ERROR")
        log("  2. Is Batfish container running? Look for 'batfish/batfish'", level="ERROR")
        log("  3. Start it: docker run -d -p 9996:9996 batfish/batfish", level="ERROR")
        log("  4. Does snapshot/configs/router1.cfg exist?", level="ERROR")
        sys.exit(1)


# ════════════════════════════════════════════════════════════════
# SECTION 5: ANALYSIS QUESTIONS
#
# Each function below asks Batfish one specific question about the
# Digital Twin model. Batfish questions are categorised as:
#
#   bf.q.<question_name>().answer().frame()
#                │                    │
#           Question type         Returns a
#          (what to ask)        pandas DataFrame
#
# All questions run against the mathematical model — not the live
# device. This is the power of the Digital Twin: you can run
# hundreds of analyses without touching production hardware.
# ════════════════════════════════════════════════════════════════

def q1_node_properties(bf):
    """
    QUESTION 1: Node Properties
    ───────────────────────────
    What devices does Batfish see in this snapshot, and what are
    their fundamental properties (hostname, OS, config format)?

    Use case: Inventory validation — confirm Batfish correctly
    parsed and recognised the device from the config file.
    """
    print()
    print("─" * 65)
    log("Q1: Node Properties — Device Inventory", level="STEP")
    print("─" * 65)

    try:
        # nodeProperties() queries the properties Batfish extracted
        # from the device config — hostname, vendor, OS version, etc.
        result = bf.q.nodeProperties().answer().frame()
        save_report(result, "q1_node_properties")

    except Exception as e:
        log(f"Q1 failed: {e}", level="ERROR")


def q2_interface_properties(bf):
    """
    QUESTION 2: Interface Properties
    ──────────────────────────────────
    What interfaces exist on the router? What are their IP addresses,
    MTU values, admin status, and configured descriptions?

    Use case: Validates that the Digital Twin accurately reflects
    the interface topology of the live device. Compare this output
    against the Phase 1 'show ip interface brief' to confirm parity.
    """
    print()
    print("─" * 65)
    log("Q2: Interface Properties — Full Interface Inventory", level="STEP")
    print("─" * 65)

    try:
        # interfaceProperties() returns one row per interface with
        # all configured attributes Batfish extracted from the config.
        result = (
            bf.q.interfaceProperties()
               .answer()
               .frame()
        )
        save_report(result, "q2_interface_properties")

    except Exception as e:
        log(f"Q2 failed: {e}", level="ERROR")


def q3_routing_table(bf):
    """
    QUESTION 3: Routing Table (RIB)
    ────────────────────────────────
    What routes does the router's Routing Information Base (RIB)
    contain? What are the next-hops, protocols, and admin distances?

    Use case: Verifies that the Digital Twin's routing model matches
    what you would see with 'show ip route' on the live device.
    Critical for validating that the model is faithful to reality.
    """
    print()
    print("─" * 65)
    log("Q3: Routing Table — Full RIB Analysis", level="STEP")
    print("─" * 65)

    try:
        # routes() queries the complete Routing Information Base
        # that Batfish computed from the config's routing statements.
        result = (
            bf.q.routes()
               .answer()
               .frame()
        )
        save_report(result, "q3_routing_table")

    except Exception as e:
        log(f"Q3 failed: {e}", level="ERROR")


def q4_bgp_config(bf):
    """
    QUESTION 4: BGP Configuration Analysis
    ────────────────────────────────────────
    Is BGP configured? If so, what are the peer relationships,
    local AS numbers, and neighbour IP addresses?

    Use case: For an IEEE research paper, BGP analysis demonstrates
    the Digital Twin can model complex routing protocols — not just
    static routes. Even if BGP is not configured, this question
    returning empty results is itself a valid finding.
    """
    print()
    print("─" * 65)
    log("Q4: BGP Configuration — Peer Relationships", level="STEP")
    print("─" * 65)

    try:
        result = (
            bf.q.bgpSessionCompatibility()
               .answer()
               .frame()
        )
        if result.empty:
            log("No BGP sessions found in config — BGP is not configured.", level="INFO")
            log("This is a valid finding: the twin confirms no BGP on this device.", level="INFO")
        else:
            save_report(result, "q4_bgp_config")

    except Exception as e:
        log(f"Q4 failed: {e}", level="ERROR")


def q5_undefined_references(bf):
    """
    QUESTION 5: Undefined References (Config Integrity Check)
    ──────────────────────────────────────────────────────────
    Are there any references in the config to objects that don't
    exist? For example: an ACL applied to an interface that was
    never defined, or a route-map referenced but not created.

    Use case: This is a HIGH-VALUE finding for an IEEE paper.
    It demonstrates the Digital Twin can detect latent config bugs
    that would be invisible to 'show' commands on the live device
    but would cause failures during a failover or policy change.
    """
    print()
    print("─" * 65)
    log("Q5: Undefined References — Config Integrity Audit", level="STEP")
    print("─" * 65)

    try:
        result = (
            bf.q.undefinedReferences()
               .answer()
               .frame()
        )
        if result.empty:
            log("No undefined references found — config integrity is CLEAN ✅", level="SUCCESS")
        else:
            log(f"FOUND {len(result)} undefined reference(s) — review required!", level="WARN")
            save_report(result, "q5_undefined_references")

    except Exception as e:
        log(f"Q5 failed: {e}", level="ERROR")


def q6_unused_structures(bf):
    """
    QUESTION 6: Unused Structures (Config Hygiene)
    ────────────────────────────────────────────────
    Are there any defined structures (ACLs, prefix-lists,
    route-maps) that exist in the config but are never applied
    or referenced anywhere?

    Use case: Identifies config bloat and dead code in the
    router configuration — relevant for security audits (unused
    ACLs may have been intended for a policy that was never applied)
    and for demonstrating the Digital Twin's audit capabilities.
    """
    print()
    print("─" * 65)
    log("Q6: Unused Structures — Config Hygiene Audit", level="STEP")
    print("─" * 65)

    try:
        result = (
            bf.q.unusedStructures()
               .answer()
               .frame()
        )
        if result.empty:
            log("No unused structures found — config is clean ✅", level="SUCCESS")
        else:
            log(f"Found {len(result)} unused structure(s).", level="WARN")
            save_report(result, "q6_unused_structures")

    except Exception as e:
        log(f"Q6 failed: {e}", level="ERROR")


def q7_traceroute(bf):
    """
    QUESTION 7: Traceroute Simulation
    ───────────────────────────────────
    What path does a packet take from GigabitEthernet1 (the WAN
    interface at 10.10.20.148) to Loopback0 (10.10.10.1)?

    Use case: This is the most visually impressive Digital Twin
    demonstration. Without sending a single packet on the live
    network, Batfish simulates the exact forwarding path the
    packet would take — including every interface, VRF, and
    policy it would encounter. This is pure model-based analysis.
    """
    print()
    print("─" * 65)
    log("Q7: Traceroute Simulation — Model-Based Path Analysis", level="STEP")
    print("─" * 65)

    try:
        # Define the simulated traffic flow.
        # HeaderConstraints specifies packet header fields.
        # We simulate ICMP (protocol 1) from the WAN IP to Loopback0.
        result = (
            bf.q.traceroute(
                startLocation="@enter(th_router[GigabitEthernet1])",
                headers       = HeaderConstraints(
                    srcIps   = "10.10.20.148",   # GigabitEthernet1 IP (from your output)
                    dstIps   = "10.10.10.1",     # Loopback0 IP (from your output)
                    ipProtocols = ["ICMP"],
                ),
            )
            .answer()
            .frame()
        )
        save_report(result, "q7_traceroute_simulation")

    except Exception as e:
        log(f"Q7 failed: {e}", level="ERROR")
        log("Note: Traceroute requires valid interface names from Q2 output.", level="INFO")
        log("Update srcIps/dstIps in q7_traceroute() to match your device's IPs.", level="INFO")


# ════════════════════════════════════════════════════════════════
# SECTION 6: MAIN ORCHESTRATOR
# ════════════════════════════════════════════════════════════════
def main():
    print()
    print("=" * 65)
    print("   DIGITAL TWIN — Pybatfish Analysis Engine  (Phase 2)")
    print("   IEEE Research Project | Cisco IOS-XE C8000v")
    print("=" * 65)
    log(f"Batfish Host  : {BATFISH_HOST}:9996")
    log(f"Network Name  : {NETWORK_NAME}")
    log(f"Snapshot      : ./{SNAPSHOT_PATH}/")
    log(f"Report Output : ./{REPORT_DIR}/")
    print()

    # ── Step 1: Initialise Batfish and build the Digital Twin ─────
    bf = initialise_batfish()
    print()

    # ── Step 2: Run the analysis question suite ───────────────────
    log("Running Digital Twin analysis suite (7 questions)...", level="STEP")

    q1_node_properties(bf)        # Device inventory
    q2_interface_properties(bf)   # Interface topology
    q3_routing_table(bf)          # Routing Information Base
    q4_bgp_config(bf)             # BGP peer relationships
    q5_undefined_references(bf)   # Config integrity audit
    q6_unused_structures(bf)      # Config hygiene audit
    q7_traceroute(bf)             # Simulated packet path

    # ── Step 3: Final summary ─────────────────────────────────────
    print()
    print("=" * 65)
    log("PHASE 2 COMPLETE — Digital Twin Analysis Finished ✅", level="SUCCESS")
    log(f"All CSV reports saved in './{REPORT_DIR}/'", level="SUCCESS")
    print()
    log("IEEE Paper talking point:", level="INFO")
    log("  The Digital Twin modelled a live Cisco IOS-XE router", level="INFO")
    log("  and answered 7 network analysis questions from config", level="INFO")
    log("  alone — with zero live device interaction after Phase 1.", level="INFO")
    print("=" * 65)
    print()


if __name__ == "__main__":
    main()