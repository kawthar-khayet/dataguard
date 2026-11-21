"""
DataGuard — interface Streamlit : vue d'ensemble, validation humaine, catalogue, historique.

Lancer (depuis la racine du projet) :
    .venv\\Scripts\\streamlit.exe run app\\app.py
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # pour importer `scanner`
from scanner.db import connect            # noqa: E402
from scanner.policy import decide         # noqa: E402

st.set_page_config(page_title="DataGuard", page_icon="🛡️", layout="wide")


# --- Accès aux données -------------------------------------------------------------
def query(sql: str, params=None) -> pd.DataFrame:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def run_full_scan():
    from scanner import discovery
    from scanner.catalog import update_catalog
    from scanner.detection import detect_all
    from scanner.policy import propose_policies
    run_id, profiles = discovery.run()
    detections = detect_all(profiles)
    with connect() as conn:
        events = update_catalog(conn, run_id, detections)
        changes = propose_policies(conn, run_id)
    return run_id, len(events), len(changes)


# --- Barre latérale ------------------------------------------------------------------
st.sidebar.title("🛡️ DataGuard")
st.sidebar.caption("Détection et protection des données personnelles — loi 09-08")
admin = st.sidebar.text_input("Administrateur", placeholder="ex. dpo.rania",
                              help="Nom enregistré avec chaque décision (traçabilité).")
st.sidebar.divider()
if st.sidebar.button("🔍 Lancer un nouveau scan", use_container_width=True):
    with st.sidebar, st.spinner("Scan en cours (chargement du modèle NLP)…"):
        run_id, n_events, n_changes = run_full_scan()
    st.sidebar.success(f"Scan n°{run_id} : {n_events} événement(s), {n_changes} politique(s) modifiée(s)")

last = query("SELECT run_id, started_at FROM governance.scan_run ORDER BY run_id DESC LIMIT 1")
if not last.empty:
    st.sidebar.caption(f"Dernier scan : n°{last.run_id[0]} — {last.started_at[0]:%d/%m/%Y %H:%M}")

tab_overview, tab_validation, tab_catalog, tab_history = st.tabs(
    ["📊 Vue d'ensemble", "✅ Validation", "📚 Catalogue", "🕓 Historique"])


# --- 1. Vue d'ensemble ---------------------------------------------------------------
with tab_overview:
    catalog = query("SELECT * FROM governance.catalog WHERE is_active")
    policies = query("SELECT status, pii_type FROM governance.policy WHERE status <> 'obsolète'")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Colonnes scannées", len(catalog))
    c2.metric("Données personnelles", int((catalog.decision == "PII").sum()))
    c3.metric("À vérifier", int((catalog.decision == "À vérifier").sum()))
    c4.metric("Politiques en attente", int((policies.status == "proposée").sum()))
    c5.metric("Politiques approuvées", int((policies.status == "approuvée").sum()))

    sensitive = catalog[catalog.decision != "Non sensible"]
    left, right = st.columns(2)
    with left:
        st.subheader("Colonnes sensibles par type")
        st.bar_chart(sensitive.pii_type.value_counts(), horizontal=True)
    with right:
        st.subheader("Par niveau de sensibilité")
        st.bar_chart(sensitive.sensitivity.value_counts(), horizontal=True)

    st.subheader("Couverture par table")
    coverage = (catalog.assign(sensible=catalog.decision != "Non sensible")
                .groupby("table_name", sort=False)
                .agg(colonnes=("column_name", "count"), sensibles=("sensible", "sum"))
                .reset_index())
    st.dataframe(coverage, hide_index=True, use_container_width=True)


# --- 2. Validation humaine -------------------------------------------------------------
with tab_validation:
    st.subheader("Politiques en attente de décision")
    pending = query("""
        SELECT p.policy_id, p.table_name, p.column_name, p.pii_type, p.sensitivity,
               p.masking_method, p.clear_roles, p.rationale,
               c.confidence, c.decision, c.evidence
        FROM governance.policy p
        JOIN governance.catalog c USING (table_name, column_name)
        WHERE p.status = 'proposée'
        ORDER BY (c.decision = 'À vérifier') DESC, c.confidence""")   # les cas incertains en premier

    if pending.empty:
        st.success("Aucune politique en attente. 🎉")
    if not admin:
        st.warning("Renseigne ton nom d'administrateur dans la barre latérale pour pouvoir décider.")

    # Les restrictions d'accès aux couches techniques (crm, raw, staging) sont nombreuses et
    # sans ambiguïté quand la détection est sûre : on peut les approuver en une fois.
    # Les cas incertains (« À vérifier ») restent à examiner un par un.
    bulk = pending[(pending.masking_method == "RESTRICT_ACCESS") & (pending.decision == "PII")]
    if not bulk.empty:
        with st.container(border=True):
            st.markdown(f"**{len(bulk)} restrictions d'accès** aux couches techniques "
                        f"(crm, raw, staging), détection sûre : seuls `data_engineer` et `dpo` y accèdent.")
            if st.button(f"✅ Approuver les {len(bulk)} restrictions", disabled=not admin):
                with connect() as conn:
                    for pid in bulk.policy_id:
                        decide(conn, int(pid), True, admin, "approbation groupée des couches techniques")
                st.rerun()
        pending = pending.drop(bulk.index)

    layers = sorted({t.split(".")[0] for t in pending.table_name})
    if layers:
        chosen = st.multiselect("Couches", layers, default=layers)
        pending = pending[pending.table_name.str.split(".").str[0].isin(chosen)]

    for p in pending.itertuples():
        icon = "⚠️" if p.decision == "À vérifier" else "🔒"
        with st.container(border=True):
            st.markdown(f"#### {icon} `{p.table_name}.{p.column_name}`")
            a, b, c = st.columns(3)
            a.markdown(f"**Type détecté :** {p.pii_type}  \n**Sensibilité :** {p.sensitivity}")
            b.markdown(f"**Confiance :** {p.confidence:.0%} ({p.decision})  \n"
                       f"**Pourquoi :** {p.evidence}")
            c.markdown(f"**Masquage proposé :** `{p.masking_method}`  \n"
                       f"**En clair pour :** {', '.join(p.clear_roles)}")
            st.caption(p.rationale)
            comment = st.text_input("Commentaire (optionnel)", key=f"comment_{p.policy_id}")
            ok, ko, _ = st.columns([1, 1, 2])
            if ok.button("✅ Approuver", key=f"ok_{p.policy_id}", disabled=not admin):
                with connect() as conn:
                    decide(conn, p.policy_id, True, admin, comment)
                st.rerun()
            if ko.button("❌ Rejeter", key=f"ko_{p.policy_id}", disabled=not admin):
                with connect() as conn:
                    decide(conn, p.policy_id, False, admin, comment)
                st.rerun()

    st.subheader("Décisions prises")
    decided = query("""
        SELECT table_name || '.' || column_name AS colonne, masking_method AS masquage,
               status AS statut, decided_by AS par, decided_at AS le, comment AS commentaire
        FROM governance.policy WHERE status IN ('approuvée', 'rejetée')
        ORDER BY decided_at DESC""")
    st.dataframe(decided, hide_index=True, use_container_width=True)


# --- 3. Catalogue ------------------------------------------------------------------------
with tab_catalog:
    st.subheader("Catalogue des colonnes")
    choice = st.multiselect("Décision", ["PII", "À vérifier", "Non sensible"],
                            default=["PII", "À vérifier"])
    view = catalog[catalog.decision.isin(choice)][
        ["table_name", "column_name", "decision", "pii_type", "category",
         "sensitivity", "confidence", "evidence"]]
    st.dataframe(view.sort_values(["table_name", "column_name"]), hide_index=True,
                 use_container_width=True,
                 column_config={"confidence": st.column_config.ProgressColumn(
                     "confiance", min_value=0, max_value=1, format="%.2f")})


# --- 4. Historique -------------------------------------------------------------------------
with tab_history:
    st.subheader("Changements détectés entre les scans")
    history = query("""
        SELECT run_id AS scan, event_type AS événement,
               table_name || '.' || column_name AS colonne,
               old_value AS avant, new_value AS après, created_at AS le
        FROM governance.catalog_history
        WHERE event_type <> 'NOUVELLE_COLONNE' OR run_id > (SELECT min(run_id) FROM governance.catalog_history)
        ORDER BY event_id DESC LIMIT 100""")
    if history.empty:
        st.info("Aucun changement depuis le premier scan.")
    st.dataframe(history, hide_index=True, use_container_width=True)

    st.subheader("Scans réalisés")
    st.dataframe(query("SELECT run_id AS scan, started_at AS le, n_columns AS colonnes "
                       "FROM governance.scan_run ORDER BY run_id DESC"),
                 hide_index=True, use_container_width=True)
