"""
twin_oracle.py
══════════════════════════════════════════════════════════════════════════════
Digital Twin Verification Oracle — IEEE Research Project
Role: The "Formal Verification" engine for the self-healing loop.
══════════════════════════════════════════════════════════════════════════════
"""

import logging
from pybatfish.client.session import Session

# Configure a silent logger for the module
_log = logging.getLogger(__name__)

# --- ARCHITECTURE CONSTANTS ---
_BATFISH_HOST   = "localhost"            
_NETWORK_NAME   = "auto_healer_network"  
_SNAPSHOT_NAME  = "post_remediation"     

def verify_remediation(snapshot_dir: str = "./snapshot/") -> bool:
    """
    Analyzes the 'Proposed Fix' in a virtual environment before deployment.
    """
    try:
        # 1. Connect to the Batfish Engine
        bf = Session(host=_BATFISH_HOST)
        bf.set_network(_NETWORK_NAME)

        # 2. Ingest the snapshot (The Digital Twin)
        bf.init_snapshot(snapshot_dir, name=_SNAPSHOT_NAME, overwrite=True)

        # 3. Formulate the Verification Question
        # Instead of checking the routing table, we ask Batfish directly:
        # "Did the 'no shutdown' command make the interface Active?"
        # NOTE: We do NOT filter by node name — Batfish derives the node
        #       name from the config's 'hostname' directive (e.g. 'iox-r1'),
        #       which may differ from the device's DNS name.
        question = bf.q.interfaceProperties(interfaces="Loopback100")

        # 4. Extract the result into a DataFrame
        result_df = question.answer().frame()

        # --- DEBUG: Show exactly what Batfish returned ---
        print(f"[ORACLE DEBUG] interfaceProperties result ({len(result_df)} rows):")
        if not result_df.empty:
            print(result_df[['Interface', 'Active']].to_string(index=False))
        else:
            print("  (empty DataFrame — Batfish found no matching interfaces)")

        # 5. POLICY EVALUATION
        if not result_df.empty:
            # Pybatfish returns a boolean True/False in the 'Active' column
            is_active = result_df['Active'].iloc[0]
            
            if is_active:
                _log.info("Digital Twin Policy PASS: Loopback100 is Active in the simulation.")
                return True

        _log.warning("Digital Twin Policy FAIL: Loopback100 is still DOWN in simulation.")
        return False

    except Exception as exc:
        # FAIL-SAFE: Abort on any simulation errors
        _log.error(f"Oracle Error: {type(exc).__name__} - {exc}")
        return False