# -*- coding: utf-8 -*-
# app_edt_presence.py
# Lecture SEULE depuis data/ (EDT + Students en .xlsx ou .csv)
# QR -> pointage direct, "Pointage par salle", "Administration"
# Mode kiosque par salle via ?room=A118 (et option ?day=LUNDI)

import io
import os
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import qrcode

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Pointage GC (Lecture seule)", page_icon="🧭", layout="wide")

JOURS = ["DIMANCHE", "LUNDI", "MARDI", "MERCREDI", "JEUDI"]
REQ_EDT = {"session_id","level","speciality","group","day","start","end","course","teacher","room"}
REQ_STU = {"student_id","name","level","speciality","group"}

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# LECTURE DES DONNÉES (data/ uniquement)
# ──────────────────────────────────────────────────────────────────────────────
def read_any(path: Path) -> pd.DataFrame | None:
    if not path.exists(): return None
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return None

def load_from_data_or_fail(basename: str) -> pd.DataFrame:
    # Priorité: .xlsx puis .csv
    xlsx = DATA_DIR / f"{basename}.xlsx"
    csv  = DATA_DIR / f"{basename}.csv"
    df = read_any(xlsx) or read_any(csv)
    if df is None:
        st.error(f"Fichier manquant : data/{basename}.xlsx **ou** data/{basename}.csv")
        st.stop()
    return df

def normalize_edt(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    # Colonnes requises
    for c in REQ_EDT:
        if c not in df.columns: df[c] = ""
    # MAJUSCULES pour day
    df["day"] = df["day"].astype(str).str.strip().str.upper()
    # Normaliser heures
    def norm_time(x):
        s = str(x).strip().replace("h",":")
        try: return datetime.strptime(s, "%H:%M").strftime("%H:%M")
        except Exception:
            try: return pd.to_datetime(x).strftime("%H:%M")
            except Exception: return s
    df["start"] = df["start"].apply(norm_time)
    df["end"]   = df["end"].apply(norm_time)
    # session_id auto si manquant
    need = df["session_id"].astype(str).str.strip().eq("") if "session_id" in df else True
    if need is True or need.any():
        df["session_id"] = (
            df["level"].astype(str).str.strip() + "-" +
            df["speciality"].astype(str).str.strip() + "-" +
            df["group"].astype(str).str.strip() + "-" +
            df["day"].astype(str).str.strip() + "-" +
            df["start"].astype(str).str.strip()
        )
    return df[list(REQ_EDT)]

def normalize_students(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    for c in REQ_STU:
        if c not in df.columns: df[c] = ""
    for k in ["level","speciality","group"]:
        df[k] = df[k].astype(str).str.strip()
    return df[list(REQ_STU)]

def load_all():
    edt_raw = load_from_data_or_fail("EDT")
    stu_raw = load_from_data_or_fail("students")
    edt_df = normalize_edt(edt_raw)
    students_df = normalize_students(stu_raw)
    return edt_df, students_df

# ──────────────────────────────────────────────────────────────────────────────
# OUTILS
# ──────────────────────────────────────────────────────────────────────────────
def get_default_day() -> str:
    # Monday=0 ... Sunday=6 → map FR
    map_fr = {0:"LUNDI",1:"MARDI",2:"MERCREDI",3:"JEUDI",4:"VENDREDI",5:"SAMEDI",6:"DIMANCHE"}
    return map_fr.get(datetime.now().weekday(), "LUNDI")

def now_local() -> datetime:
    return datetime.now()

def make_qr_png_bytes(data: str) -> bytes:
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def build_qr_url(session_id: str) -> str:
    base = st.secrets.get("BASE_URL", "")
    if isinstance(base, str) and base.strip():
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}session_id={session_id}"
    return f"?session_id={session_id}"

def upcoming_sessions_for_day(edt: pd.DataFrame, day: str, within_minutes: int = 180) -> pd.DataFrame:
    now = now_local()
    day_df = edt[edt["day"]==day]
    rows = []
    for _, r in day_df.iterrows():
        try:
            sd = datetime.combine(now.date(), datetime.strptime(r["start"], "%H:%M").time())
            ed = datetime.combine(now.date(), datetime.strptime(r["end"], "%H:%M").time())
        except Exception:
            continue
        if sd - timedelta(minutes=15) <= now <= sd + timedelta(minutes=within_minutes):
            rows.append(r)
    return pd.DataFrame(rows) if rows else day_df.sort_values(["start","room"])

def save_attendance(records_df: pd.DataFrame) -> Path:
    # ⚠️ Sur Streamlit Cloud, ce fichier est éphémère (prévoir export/Google Sheets plus tard)
    csv_path = DATA_DIR / "attendance_records.csv"
    if csv_path.exists():
        old = pd.read_csv(csv_path)
        new = pd.concat([old, records_df], ignore_index=True)
    else:
        new = records_df
    new.to_csv(csv_path, index=False)
    return csv_path

# ──────────────────────────────────────────────────────────────────────────────
# CHARGEMENT
# ──────────────────────────────────────────────────────────────────────────────
edt_df, students_df = load_all()

# ──────────────────────────────────────────────────────────────────────────────
# ROUTAGE QUERY PARAMS (QR direct, kiosque par salle)
# ──────────────────────────────────────────────────────────────────────────────
q = st.experimental_get_query_params()

def render_session_form(session_id: str):
    sel = edt_df[edt_df["session_id"]==session_id]
    if sel.empty:
        st.error("Séance introuvable. Vérifiez 'session_id'.")
        return
    row = sel.iloc[0]
    st.title("✅ Pointage de la séance")
    st.info(
        f"**{row['course']}** — **{row['teacher']}**  \n"
        f"**Salle :** {row['room']}  \n"
        f"**Niveau :** {row['level']} | **Spécialité :** {row['speciality']} | **Groupe :** {row['group']}  \n"
        f"**Horaire :** {row['day']} {row['start']}–{row['end']}"
    )
    studs = students_df[
        (students_df["level"]==row["level"]) &
        (students_df["speciality"]==row["speciality"]) &
        (students_df["group"]==row["group"])
    ].copy()
    if studs.empty:
        st.warning("Aucun étudiant pour cette combinaison (level/speciality/group).")
        return
    studs["present"] = False
    edited = st.data_editor(studs[["student_id","name","present"]],
                            num_rows="fixed", use_container_width=True, height=420,
                            key=f"ed_s_{session_id}")
    remark = st.text_area("Remarque au département (optionnel)", key=f"rem_s_{session_id}")
    if st.button("✅ Envoyer le pointage", key=f"send_s_{session_id}"):
        out = edited.copy()
        out["session_id"] = session_id
        out["timestamp"] = now_local().strftime("%Y-%m-%d %H:%M:%S")
        out["teacher"] = row["teacher"]
        out["room"] = row["room"]
        out["course"] = row["course"]
        out["remark"] = remark
        pth = save_attendance(out)
        st.success(f"Présences enregistrées ({len(out)} lignes) → {pth.name}")

# 1) Lien direct par QR
if "session_id" in q:
    render_session_form(q["session_id"][0])
    st.stop()

# 2) Page administration (lecture seule + export)
if q.get("admin", ["0"])[0] == "1":
    st.title("🗂️ Administration — enregistrements")
    csv_path = DATA_DIR / "attendance_records.csv"
    if csv_path.exists():
        df_att = pd.read_csv(csv_path)
        st.dataframe(df_att, use_container_width=True, height=520)
        st.download_button("⬇️ Export CSV", data=df_att.to_csv(index=False).encode("utf-8"),
                           file_name="attendance_records_export.csv", mime="text/csv", key="adm_dl")
    else:
        st.info("Aucun enregistrement pour l’instant.")
    st.stop()

# ──────────────────────────────────────────────────────────────────────────────
# ONGLET 1 : EDT & QR | ONGLET 2 : Pointage par salle | ONGLET 3 : Administration
# ──────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📅 Emplois du temps & QR", "🏫 Pointage par salle", "🗂️ Administration"])

with tab1:
    st.subheader("Emplois du temps (lecture depuis data/)")
    c1, c2, c3, c4 = st.columns([1,1,1,1])
    with c1:
        day_sel = st.selectbox("Jour", JOURS,
                               index=JOURS.index(get_default_day()) if get_default_day() in JOURS else 1,
                               key="t1_day")
    with c2:
        level_sel = st.selectbox("Niveau", sorted(edt_df["level"].unique()), key="t1_level")
    with c3:
        spec_sel = st.selectbox("Spécialité", sorted(edt_df["speciality"].unique()), key="t1_spec")
    with c4:
        grp_sel = st.selectbox("Groupe", sorted(edt_df["group"].unique()), key="t1_group")

    filt = (edt_df["day"]==day_sel) & (edt_df["level"]==level_sel) & (edt_df["speciality"]==spec_sel) & (edt_df["group"]==grp_sel)
    day_sessions = edt_df[filt].sort_values(["start","room"])
    st.dataframe(day_sessions[["start","end","course","teacher","room"]], use_container_width=True, height=260)

    st.markdown("### QR pour accès direct au pointage de la séance")
    for _, row in day_sessions.iterrows():
        cc1, cc2, cc3, cc4 = st.columns([2,2,2,2])
        with cc1:
            st.write(f"**{row['start']}–{row['end']}**  \n{row['course']}")
        with cc2:
            st.write(f"{row['teacher']} — **Salle {row['room']}**")
        with cc3:
            url = build_qr_url(row["session_id"])
            st.image(make_qr_png_bytes(url), caption=f"QR {row['session_id']}", width=100)
        with cc4:
            st.code(url, language="text")

with tab2:
    st.subheader("Pointage par **Salle**")
    # Mode kiosque : ?room=A118 (et ?day=LUNDI optionnel)
    fixed_room = q.get("room", [None])[0]
    fixed_day  = q.get("day",  [None])[0]
    d1, d2 = st.columns([1,2])
    with d1:
        day2 = fixed_day if fixed_day in JOURS else st.selectbox("Jour", JOURS,
                    index=JOURS.index(get_default_day()) if get_default_day() in JOURS else 1,
                    key="t2_day")
    up_df = upcoming_sessions_for_day(edt_df, day2, within_minutes=180)
    rooms = sorted(up_df["room"].unique()) if not up_df.empty else sorted(edt_df[edt_df["day"]==day2]["room"].unique())
    with d2:
        room_sel = fixed_room if fixed_room in rooms else st.selectbox("Salle", rooms, key="t2_room")

    if up_df.empty:
        cand = edt_df[(edt_df["day"]==day2) & (edt_df["room"]==room_sel)].sort_values("start")
    else:
        cand = up_df[up_df["room"]==room_sel].sort_values("start")

    options = [f"{r['session_id']} | {r['start']}-{r['end']} | {r['course']} | {r['teacher']}" for _, r in cand.iterrows()]
    sess_sel = options[0] if (fixed_room and options) else st.selectbox("Séance", options, key="t2_session") if options else None

    if sess_sel:
        session_id = sess_sel.split("|")[0].strip()
        # Réutilise le même formulaire que QR
        render_session_form(session_id)

with tab3:
    st.subheader("Administration — enregistrements")
    csv_path = DATA_DIR / "attendance_records.csv"
    if csv_path.exists():
        df_att = pd.read_csv(csv_path)
        st.dataframe(df_att, use_container_width=True, height=420)
        st.download_button("⬇️ Export CSV", data=df_att.to_csv(index=False).encode("utf-8"),
                           file_name="attendance_records_export.csv", mime="text/csv", key="adm_dl2")
    else:
        st.info("Aucun enregistrement disponible pour l’instant.")

st.caption("Lecture seule depuis data/. Pour QR publics, définissez st.secrets['BASE_URL'] sur Streamlit Cloud. Mode kiosque: ajoutez ?room=A118&day=LUNDI à l’URL.")
