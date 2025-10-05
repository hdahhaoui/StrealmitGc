# -*- coding: utf-8 -*-
# app_edt_presence.py
# Streamlit + Excel (EDT + Students) + QR + pointage par salle + remarques

import io
import os
import base64
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import qrcode

# ----------------------------
# CONFIG GÉNÉRALE
# ----------------------------
st.set_page_config(page_title="Pointage GC - Salles/EDT", page_icon="🧭", layout="wide")

# Jours en FR pour correspondre aux EDT
JOURS = ["DIMANCHE", "LUNDI", "MARDI", "MERCREDI", "JEUDI"]
# Fuseau local : Africa/Algiers (utilisateur à Tlemcen)
TZ = "Africa/Algiers"

# ----------------------------
# A) TEMPLATES ET DONNÉES SEED
# ----------------------------
def template_students() -> pd.DataFrame:
    """
    Modèle Excel 'students.xlsx' (une seule feuille).
    Colonnes obligatoires:
      - student_id (texte ou entier)
      - name
      - level      (ex: L1, L2, L3, M1, M2)
      - speciality (ex: ING, COMM, GC, STR, VOA, RIB)
      - group      (ex: G11, G12, etc.)
    """
    return pd.DataFrame(
        [
            {"student_id":"2025L1ING001","name":"Ali Benabbas","level":"L1","speciality":"ING","group":"G12"},
            {"student_id":"2025L1ING002","name":"Nadia Boukhalfa","level":"L1","speciality":"ING","group":"G12"},
            {"student_id":"2025L2COMM003","name":"Karim Meziani","level":"L2","speciality":"COMM","group":"G11"},
            {"student_id":"2025L3GC004","name":"Lila Bensalah","level":"L3","speciality":"GC","group":"G12"},
        ]
    )

def template_edt() -> pd.DataFrame:
    """
    Modèle Excel 'EDT.xlsx' (une seule feuille).
    Colonnes obligatoires:
      - session_id  (ID unique séance)
      - level       (L1/L2/L3/M1/M2)
      - speciality  (ING/COMM/GC/STR/VOA/RIB)
      - group       (G11/G12/…)
      - day         (DIMANCHE/LUNDI/MARDI/MERCREDI/JEUDI)
      - start       (HH:MM)
      - end         (HH:MM)
      - course      (intitulé)
      - teacher     (enseignant)
      - room        (salle/lab/amphi)
    Données seed simplifiées extraites des PDFs du 04-10-2025 pour démarrer rapidement.
    """
    rows = []
    add = rows.append

    # --- Exemples L1 ING G12 (source PDF 04-10-2025) ---
    add({"session_id":"L1-ING-G12-DIM-0830","level":"L1","speciality":"ING","group":"G12","day":"DIMANCHE",
         "start":"08:30","end":"10:00","course":"Algèbre 1 (Cours)","teacher":"BELBACHIR.A","room":"A004"})
    add({"session_id":"L1-ING-G12-LUN-0830","level":"L1","speciality":"ING","group":"G12","day":"LUNDI",
         "start":"08:30","end":"10:00","course":"Analyse 1 (Cours)","teacher":"ATTAR.K","room":"A004"})  # :contentReference[oaicite:4]{index=4}
    add({"session_id":"L1-ING-G12-MER-0830","level":"L1","speciality":"ING","group":"G12","day":"MERCREDI",
         "start":"08:30","end":"10:00","course":"Physique 1 (TD)","teacher":"BELAOUI.M","room":"A002"})

    # --- Exemples L2 ING G11 (source PDF 04-10-2025) ---
    add({"session_id":"L2-ING-G11-DIM-0830","level":"L2","speciality":"ING","group":"G11","day":"DIMANCHE",
         "start":"08:30","end":"10:00","course":"Math appliqués (Cours)","teacher":"CHEKROUN.A","room":"AMPHI01"})
    add({"session_id":"L2-ING-G11-LUN-0830","level":"L2","speciality":"ING","group":"G11","day":"LUNDI",
         "start":"08:30","end":"10:00","course":"RDM1 (Cours)","teacher":"MAHI.I","room":"AMPHI1"})  # :contentReference[oaicite:5]{index=5}

    # --- Exemples L2 COMM G12 ---
    add({"session_id":"L2-COMM-G12-DIM-0830","level":"L2","speciality":"COMM","group":"G12","day":"DIMANCHE",
         "start":"08:30","end":"10:00","course":"Analyse 3 (Cours)","teacher":"CHEKROUN.A","room":"AMPHI01"})
    add({"session_id":"L2-COMM-G12-LUN-1000","level":"L2","speciality":"COMM","group":"G12","day":"LUNDI",
         "start":"10:00","end":"11:30","course":"Ondes et vibrations (Cours)","teacher":"BOURABAH.M","room":"AMPHI01"})

    # --- Exemples L3 GC G12 ---
    add({"session_id":"L3-GC-G12-DIM-0830","level":"L3","speciality":"GC","group":"G12","day":"DIMANCHE",
         "start":"08:30","end":"10:00","course":"Méc des sols 2 (Cours)","teacher":"ZADJAOUI.A","room":"A118"})
    add({"session_id":"L3-GC-G12-LUN-1000","level":"L3","speciality":"GC","group":"G12","day":"LUNDI",
         "start":"10:00","end":"11:30","course":"Béton Armé 1 (Cours)","teacher":"GHENNANI.B","room":"A118"})

    # --- Exemples M1 STR G11 ---
    add({"session_id":"M1-STR-G11-DIM-0830","level":"M1","speciality":"STR","group":"G11","day":"DIMANCHE",
         "start":"08:30","end":"10:00","course":"Gestion des risques (Cours)","teacher":"BEKKOUCHE.A","room":"A113"})
    add({"session_id":"M1-STR-G11-LUN-1130","level":"M1","speciality":"STR","group":"G11","day":"LUNDI",
         "start":"11:30","end":"13:00","course":"BA1 (Cours)","teacher":"HOUTI.F","room":"A113"})

    # --- Exemples M2 VOA G11 ---
    add({"session_id":"M2-VOA-G11-LUN-1000","level":"M2","speciality":"VOA","group":"G11","day":"LUNDI",
         "start":"10:00","end":"11:30","course":"Géotechnique avancée (Cours)","teacher":"ZADJAOUI.A","room":"A120"})
    add({"session_id":"M2-VOA-G11-MAR-1500","level":"M2","speciality":"VOA","group":"G11","day":"MARDI",
         "start":"15:00","end":"17:00","course":"Modélisation num. des ponts (TP)","teacher":"MEDJAHED.A","room":"LABINFA08"})

    # NB: Remplacez/complétez ces seeds en important votre EDT.xlsx.
    return pd.DataFrame(rows)

def download_excel_button(df: pd.DataFrame, filename: str, label: str):
    buf = io.BytesIO()
    # Un seul sheet par simplicité
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    st.download_button(label=label, data=buf.getvalue(), file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ----------------------------
# B) CHARGEMENT DES FICHIERS
# ----------------------------
st.sidebar.header("Fichiers d'entrée (Excel)")
edt_file = st.sidebar.file_uploader("EDT.xlsx (emplois du temps)", type=["xlsx"])
stud_file = st.sidebar.file_uploader("students.xlsx (étudiants)", type=["xlsx"])

st.sidebar.markdown("Si vous n'importez rien, des **données seed** seront utilisées (vous pourrez les remplacer ensuite).")
st.sidebar.markdown("Téléchargez les **modèles** pour les remplir et réimporter :")
download_excel_button(template_edt(), "EDT_template.xlsx", "⬇️ Télécharger modèle EDT.xlsx")
download_excel_button(template_students(), "students_template.xlsx", "⬇️ Télécharger modèle students.xlsx")

# Lire EDT
if edt_file:
    edt_df = pd.read_excel(edt_file)
else:
    edt_df = template_edt()

# Lire Students
if stud_file:
    students_df = pd.read_excel(stud_file)
else:
    students_df = template_students()

# Validation colonnes minimales
REQ_EDT_COLS = {"session_id","level","speciality","group","day","start","end","course","teacher","room"}
REQ_STU_COLS = {"student_id","name","level","speciality","group"}

def valid_cols(df, required):
    missing = [c for c in required if c not in df.columns]
    return len(missing)==0, missing

ok1, miss1 = valid_cols(edt_df, REQ_EDT_COLS)
ok2, miss2 = valid_cols(students_df, REQ_STU_COLS)
if not ok1:
    st.error(f"Colonnes manquantes dans EDT.xlsx : {miss1}")
if not ok2:
    st.error(f"Colonnes manquantes dans students.xlsx : {miss2}")
if not (ok1 and ok2):
    st.stop()

# Normalisations
edt_df["day"] = edt_df["day"].str.upper().str.strip()
for tcol in ["start","end"]:
    edt_df[tcol] = edt_df[tcol].astype(str).str.strip()

# ----------------------------
# C) UTILITAIRES
# ----------------------------
def now_local():
    # horodatage local simple (sans tz-aware pour Streamlit)
    return datetime.now()

def time_in_range(start_str, end_str, t: datetime):
    t0 = datetime.strptime(start_str, "%H:%M").time()
    t1 = datetime.strptime(end_str, "%H:%M").time()
    return t0 <= t.time() <= t1

def build_qr_url(session_id: str):
    # Si déployé (e.g. Streamlit Cloud), remplacez par l’URL publique.
    # En local, on encode juste ?session_id=...
    return f"?session_id={session_id}"

def make_qr_png_bytes(data: str) -> bytes:
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def get_upcoming_sessions_by_room(edt: pd.DataFrame, day: str, within_minutes: int = 120):
    """
    Séances qui démarrent dans la fenêtre [now - 15 min ; now + within_minutes]
    pour sélection rapide par salle.
    """
    now = now_local()
    res = []
    for _, row in edt[edt["day"]==day].iterrows():
        start_dt = datetime.combine(now.date(), datetime.strptime(row["start"], "%H:%M").time())
        end_dt = datetime.combine(now.date(), datetime.strptime(row["end"], "%H:%M").time())
        if start_dt - timedelta(minutes=15) <= now <= start_dt + timedelta(minutes=within_minutes):
            res.append(row)
    if not res:
        # fallback: toutes les séances du jour (tri par heure)
        res = list(edt[edt["day"]==day].sort_values("start").itertuples(index=False))
        return pd.DataFrame(res).rename(columns={c:getattr(res[0], "_fields")[i] for i,c in enumerate(edt.columns)}) if res else edt.iloc[0:0]
    return pd.DataFrame(res)

# ----------------------------
# D) UI : Onglets
# ----------------------------
tab1, tab2, tab3 = st.tabs(["📅 Emplois du temps & QR", "🏫 Pointage par salle", "🗂️ Administration"])

# ---- TAB 1 : Visualisation EDT & QR ----
with tab1:
    st.subheader("Emplois du temps (EDT)")
    colf1, colf2, colf3 = st.columns([1,1,2])
    with colf1:
        day_sel = st.selectbox("Jour", JOURS, index=JOURS.index(JOURS[now_local().weekday() % len(JOURS)]))
    with colf2:
        level_sel = st.selectbox("Niveau (Level)", sorted(edt_df["level"].unique()))
    with colf3:
        spec_sel = st.selectbox("Spécialité (Speciality)", sorted(edt_df["speciality"].unique()))
    gcol1, gcol2 = st.columns([2,1])
    with gcol1:
        grp_sel = st.selectbox("Groupe (Group)", sorted(edt_df["group"].unique()))
    filt = (edt_df["day"]==day_sel)&(edt_df["level"]==level_sel)&(edt_df["speciality"]==spec_sel)&(edt_df["group"]==grp_sel)
    day_sessions = edt_df[filt].sort_values(["start","room"])
    st.dataframe(day_sessions[["start","end","course","teacher","room"]], use_container_width=True, height=260)

    st.markdown("### Générer QR code (accès direct au pointage de la séance)")
    for _, row in day_sessions.iterrows():
        c1, c2, c3, c4 = st.columns([2,2,2,2])
        with c1:
            st.write(f"**{row['start']}–{row['end']}**  \n{row['course']}")
        with c2:
            st.write(f"{row['teacher']} — **Salle {row['room']}**")
        with c3:
            url = build_qr_url(row["session_id"])
            png = make_qr_png_bytes(url)
            st.image(png, caption=f"QR {row['session_id']}", width=100)
        with c4:
            st.code(url, language="text")

# ---- TAB 2 : Pointage par salle (sans QR) ----
with tab2:
    st.subheader("Pointage enseignant par **Salle** (séance proche)")
    col1, col2, col3 = st.columns([1,1,2])
    with col1:
        day2 = st.selectbox("Jour", JOURS, index=JOURS.index(JOURS[now_local().weekday() % len(JOURS)]))
    up_df = get_upcoming_sessions_by_room(edt_df, day2, within_minutes=180)
    with col2:
        room_sel = st.selectbox("Salle", sorted(up_df["room"].unique()) if not up_df.empty else sorted(edt_df[edt_df["day"]==day2]["room"].unique()))
    if up_df.empty:
        cand = edt_df[(edt_df["day"]==day2) & (edt_df["room"]==room_sel)].sort_values("start")
    else:
        cand = up_df[up_df["room"]==room_sel].sort_values("start")
    with col3:
        sess_sel = st.selectbox("Séance", [f"{r['session_id']} | {r['start']}-{r['end']} | {r['course']} | {r['teacher']}" for _, r in cand.iterrows()] if not cand.empty else [])
    if sess_sel:
        session_id = sess_sel.split("|")[0].strip()
        row = edt_df[edt_df["session_id"]==session_id].iloc[0]
        st.info(f"**Séance :** {row['course']} — **Enseignant :** {row['teacher']} — **Salle :** {row['room']}  \n**Niveau :** {row['level']} **Spécialité :** {row['speciality']} **Groupe :** {row['group']}  \n**Horaire :** {row['start']}–{row['end']}")
        # Filtrer étudiants du même level/speciality/group
        st.markdown("### Liste des étudiants")
        studs = students_df[
            (students_df["level"]==row["level"]) &
            (students_df["speciality"]==row["speciality"]) &
            (students_df["group"]==row["group"])
        ].copy()
        if studs.empty:
            st.warning("Aucun étudiant trouvé pour cette combinaison (vérifiez students.xlsx).")
        else:
            studs["present"] = False
            key = f"present_{session_id}"
            edited = st.data_editor(studs[["student_id","name","present"]], num_rows="fixed", key=key, use_container_width=True, height=300)
            remark = st.text_area("Remarque à l'attention du département (optionnel)")
            if st.button("✅ Envoyer le pointage"):
                out = edited.copy()
                out["session_id"] = session_id
                out["timestamp"] = now_local().strftime("%Y-%m-%d %H:%M:%S")
                out["teacher"] = row["teacher"]
                out["room"] = row["room"]
                out["course"] = row["course"]
                out["remark"] = remark
                # Append CSV
                csv_path = "attendance_records.csv"
                if os.path.exists(csv_path):
                    old = pd.read_csv(csv_path)
                    new = pd.concat([old, out], ignore_index=True)
                else:
                    new = out
                new.to_csv(csv_path, index=False)
                st.success(f"Présences enregistrées ({len(out)} lignes) → {csv_path}")

# ---- TAB 3 : Administration ----
with tab3:
    st.subheader("Consultation des enregistrements")
    csv_path = "attendance_records.csv"
    if os.path.exists(csv_path):
        df_att = pd.read_csv(csv_path)
        st.dataframe(df_att, use_container_width=True, height=360)
        st.download_button("⬇️ Export CSV complet", data=df_att.to_csv(index=False).encode("utf-8"), file_name="attendance_records_export.csv", mime="text/csv")
    else:
        st.info("Aucun enregistrement pour l'instant. Le fichier 'attendance_records.csv' sera créé au premier envoi.")

st.caption("Données seed simplifiées à partir des emplois du temps PDF du 04-10-2025 (L1/L2/L3/M1/M2) afin d'amorcer l’outil. Remplacez-les par votre EDT.xlsx final.")
