import streamlit as st
import pandas as pd
import plotly.express as px
import os
import json
import base64
import requests
from datetime import datetime

# Configuracion de pagina
st.set_page_config(
    page_title="LinkedIn Scraper - Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo personalizado oscuro
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #16213e; padding: 15px; border-radius: 10px; border: 1px solid #2a2a4a; }
    .st-emotion-cache-1wivap2 { color: #e0e0e0 !important; }
    .css-1d391kg { background-color: #1a1a2e; }
    .post-card { background-color: #16213e; padding: 20px; border-radius: 10px; border: 1px solid #2a2a4a; margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

ALL_OFFERS_FILE = "Todas_Ofertas.csv"
STRUCTURAL_FILE = "Ofertas_Estructurales.csv"
TRAINING_FILE = "training_data.json"
LEADS_FILE = "Contactos_Emails.csv"
LEADS_COLUMNS = [
    "Correo", "Autor", "Empresa", "Cargo", "Es Estructural", "Es Contacto",
    "Region", "Comuna", "Fecha Post", "URL Perfil", "Contactado", "Fecha Agregado"
]

def _github_config():
    """Lee las credenciales de GitHub desde st.secrets. Devuelve (token, repo, branch) o (None, None, None)."""
    try:
        gh = st.secrets["github"]
        return gh["token"], gh.get("repo", "bRUNS123/Linkedin-AG"), gh.get("branch", "master")
    except (KeyError, FileNotFoundError):
        return None, None, None

def github_sync_enabled():
    token, _, _ = _github_config()
    return token is not None

def push_file_to_github(path, content_bytes, message):
    """Crea o actualiza un archivo en el repo de GitHub para que los datos persistan
    entre reinicios de Streamlit Cloud. Si no hay credenciales configuradas, no hace nada."""
    token, repo, branch = _github_config()
    if not token:
        return False

    api_url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    try:
        get_resp = requests.get(api_url, headers=headers, params={"ref": branch}, timeout=10)
        sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

        payload = {
            "message": message,
            "content": base64.b64encode(content_bytes).decode("utf-8"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        put_resp = requests.put(api_url, headers=headers, json=payload, timeout=10)
        return put_resp.status_code in (200, 201)
    except requests.RequestException:
        return False

@st.cache_data(ttl=60)
def load_csv_data():
    if not os.path.exists(ALL_OFFERS_FILE):
        return pd.DataFrame(), pd.DataFrame()
    df_all = pd.read_csv(ALL_OFFERS_FILE)
    df_struct = pd.DataFrame()
    if os.path.exists(STRUCTURAL_FILE):
        df_struct = pd.read_csv(STRUCTURAL_FILE)
        
    # Añadir columna 'Es Estructural' al df general si existe df_struct
    if not df_struct.empty and not df_all.empty:
        # Usamos 'Texto' o 'URL Perfil' como clave única para saber cuáles son estructurales
        estructurales_urls = df_struct['URL Perfil'].tolist()
        df_all['Es Estructural'] = df_all['URL Perfil'].apply(lambda x: 'Sí' if x in estructurales_urls else 'No')
    else:
        df_all['Es Estructural'] = 'No'

    return df_all, df_struct

def load_training_data():
    if os.path.exists(TRAINING_FILE):
        try:
            with open(TRAINING_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []

def save_training_data(data):
    content = json.dumps(data, ensure_ascii=False, indent=2)
    with open(TRAINING_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    push_file_to_github(TRAINING_FILE, content.encode("utf-8"), "Actualizar training_data.json desde la app")

def _disp(val, default=""):
    """Convierte NaN/None/vacío a un valor por defecto para mostrar en la UI."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    val = str(val).strip()
    return val if val else default

def compute_priority(row):
    """Combina score de IA, oferta estructural, contacto directo y disponibilidad de correo."""
    try:
        score = float(row.get('Score', 0) or 0)
    except (ValueError, TypeError):
        score = 0.0

    priority = score * 0.4
    if row.get('Es Estructural') == 'Sí':
        priority += 0.25
    if row.get('Es Contacto') == 'Sí':
        priority += 0.20
    correos = row.get('Correos')
    if isinstance(correos, str) and correos.strip():
        priority += 0.15
    return priority

def load_leads():
    if os.path.exists(LEADS_FILE):
        try:
            return pd.read_csv(LEADS_FILE)
        except (pd.errors.EmptyDataError, OSError):
            return pd.DataFrame(columns=LEADS_COLUMNS)
    return pd.DataFrame(columns=LEADS_COLUMNS)

def save_leads(df_leads):
    df_leads.to_csv(LEADS_FILE, index=False)
    content = df_leads.to_csv(index=False)
    push_file_to_github(LEADS_FILE, content.encode("utf-8"), "Actualizar Contactos_Emails.csv desde la app")

def update_leads_from_df(df_all):
    """Agrega a la base de contactos los correos nuevos encontrados en df_all. Devuelve (n_nuevos, leads_df)."""
    leads_df = load_leads()
    existing_emails = set(leads_df["Correo"].astype(str).str.lower()) if not leads_df.empty else set()

    new_rows = []
    today = datetime.now().strftime("%Y-%m-%d")
    for _, row in df_all.iterrows():
        correos = row.get("Correos")
        if not isinstance(correos, str) or not correos.strip():
            continue
        es_contacto = row.get("Es Contacto") == "Sí"
        empresa_contacto = _disp(row.get("Empresa Contacto"))
        empresa = empresa_contacto if (es_contacto and empresa_contacto) else _disp(row.get("Empresa"))
        cargo = _disp(row.get("Cargo Contacto")) if es_contacto else ""
        for email in correos.split(","):
            email = email.strip()
            if not email or email.lower() in existing_emails:
                continue
            new_rows.append({
                "Correo": email,
                "Autor": _disp(row.get("Autor")),
                "Empresa": empresa,
                "Cargo": cargo,
                "Es Estructural": row.get("Es Estructural", "No"),
                "Es Contacto": row.get("Es Contacto", "No"),
                "Region": _disp(row.get("Region")),
                "Comuna": _disp(row.get("Comuna")),
                "Fecha Post": _disp(row.get("Fecha")),
                "URL Perfil": _disp(row.get("URL Perfil")),
                "Contactado": False,
                "Fecha Agregado": today,
            })
            existing_emails.add(email.lower())

    if new_rows:
        leads_df = pd.concat([leads_df, pd.DataFrame(new_rows)], ignore_index=True)
        save_leads(leads_df)

    return len(new_rows), leads_df

st.title("📊 Panel de Inteligencia - LinkedIn Scraper")

if github_sync_enabled():
    st.sidebar.success("🔄 Sincronización con GitHub activa")
else:
    st.sidebar.warning("⚪ Sin sincronización con GitHub (los cambios solo viven en esta sesión)")

df, df_struct = load_csv_data()
if df.empty:
    st.warning("No hay datos disponibles. Espera a que el bot exporte los primeros resultados.")
    st.stop()

# Inicializar variables de sesión para el entrenamiento
if 'training_idx' not in st.session_state:
    st.session_state.training_idx = 0
if 'training_data' not in st.session_state:
    st.session_state.training_data = load_training_data()
    
# Layout de Pestañas
tab1, tab_top, tab2, tab3 = st.tabs(["📈 Dashboard General", "🏆 Top Ofertas", "🔎 Explorador de Datos", "🧠 Entrenamiento Bot"])

# ==========================================
# PESTAÑA 1: DASHBOARD
# ==========================================
with tab1:
    st.markdown("### Resumen de Extracción")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Ofertas", f"{len(df):,}")
    with col2:
        st.metric("Estructurales", f"{len(df_struct):,}")
    with col3:
        total_correos = len(df[df["Correos"].notna() & (df["Correos"] != "")])
        st.metric("Posts con Correos", f"{total_correos:,}")
    with col4:
        st.metric("Muestras Entrenadas", f"{len(st.session_state.training_data):,}")

    st.markdown("---")
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("Distribución de Roles de IA")
        if 'Rol' in df.columns:
            role_counts = df['Rol'].value_counts().reset_index()
            role_counts.columns = ['Rol', 'Cantidad']
            role_counts = role_counts[role_counts['Rol'] != '']
            fig1 = px.bar(role_counts.head(10), x='Rol', y='Cantidad', color_discrete_sequence=['#e94560'])
            st.plotly_chart(fig1, use_container_width=True)

    with col_chart2:
        st.subheader("Match con Contactos Directos")
        if 'Es Contacto' in df.columns:
            contact_counts = df['Es Contacto'].value_counts().reset_index()
            contact_counts.columns = ['Es Contacto', 'Cantidad']
            fig2 = px.pie(contact_counts, values='Cantidad', names='Es Contacto', color_discrete_sequence=['#448aff', '#0f3460'])
            st.plotly_chart(fig2, use_container_width=True)


# ==========================================
# PESTAÑA TOP: TOP OFERTAS
# ==========================================
with tab_top:
    st.markdown("### 🏆 Top Ofertas")
    st.write("Ranking combinado: score de IA + oferta estructural + contacto directo + correo disponible.")

    df_rank = df.copy()
    df_rank['Prioridad'] = df_rank.apply(compute_priority, axis=1)
    df_rank['_FechaDT'] = pd.to_datetime(df_rank['Fecha'], errors='coerce')
    df_rank = df_rank.sort_values(by=['Prioridad', '_FechaDT'], ascending=[False, False])

    solo_accionables = st.checkbox("Solo mostrar accionables (correo o contacto directo)", key="f_top_accionable")
    if solo_accionables:
        df_rank = df_rank[
            (df_rank["Correos"].notna() & (df_rank["Correos"] != "")) |
            (df_rank["Es Contacto"] == "Sí")
        ]

    top_n = st.slider("Cuántas ofertas mostrar:", min_value=5, max_value=50, value=10, step=5)
    df_rank = df_rank.head(top_n)

    if df_rank.empty:
        st.info("No hay ofertas que cumplan los filtros seleccionados.")
    else:
        now = datetime.now()
        for _, row in df_rank.iterrows():
            badges = []
            if row.get('Es Estructural') == 'Sí':
                badges.append("🏗️ Estructural")
            if row.get('Es Contacto') == 'Sí':
                badges.append(f"🤝 Contacto directo ({row.get('Empresa Contacto', '')} - {row.get('Cargo Contacto', '')})")
            correos = row.get('Correos')
            if isinstance(correos, str) and correos.strip():
                badges.append("📧 Tiene correo")
            fecha_dt = row.get('_FechaDT')
            if pd.notna(fecha_dt) and (now - fecha_dt).days <= 7:
                badges.append("🕐 Reciente")

            badges_html = " &nbsp; ".join(badges) if badges else "—"
            texto_completo = _disp(row.get('Texto'))
            texto = texto_completo[:300] + ("..." if len(texto_completo) > 300 else "")
            empresa = _disp(row.get('Empresa')) or _disp(row.get('Empresa Contacto'))

            st.markdown(f'''
            <div class="post-card">
                <h4>👤 {_disp(row.get("Autor"))} <span style="float:right; color:#00e676;">Prioridad: {row.get("Prioridad", 0):.2f}</span></h4>
                <p>{badges_html}</p>
                <p><b>🛠️ Rol:</b> {_disp(row.get("Rol"))} | <b>🏢 Empresa:</b> {empresa} | <b>📍 Región:</b> {_disp(row.get("Region"))}</p>
                <p><b>📧 Correos:</b> <span style="color:#00e676">{_disp(row.get("Correos"), "Ninguno")}</span></p>
                <p>{texto}</p>
                <a href="{row.get("URL Perfil", "#")}" target="_blank">🔗 Ver Perfil en LinkedIn</a>
            </div>
            ''', unsafe_allow_html=True)


# ==========================================
# PESTAÑA 2: EXPLORADOR
# ==========================================
with tab2:
    st.sidebar.header("🔎 Filtros del Explorador")
    
    # Filtros
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        ia_filter = st.sidebar.radio("IA Validado", ["Todos", "Sí", "No"], key="f_ia")
        contact_filter = st.sidebar.radio("Proviene de Contacto", ["Todos", "Sí", "No"], key="f_contact")
    with col_f2:
        has_email = st.sidebar.checkbox("Solo posts con correos", key="f_email")
        only_structural = st.sidebar.checkbox("Solo ofertas estructurales", key="f_struct")
        search_query = st.sidebar.text_input("Buscador global (texto, empresa, rol):")
        
    df_filtered = df.copy()
    if ia_filter != "Todos": df_filtered = df_filtered[df_filtered["IA Validado"] == ia_filter]
    if contact_filter != "Todos": df_filtered = df_filtered[df_filtered["Es Contacto"] == contact_filter]
    if has_email: df_filtered = df_filtered[df_filtered["Correos"].notna() & (df_filtered["Correos"] != "")]
    if only_structural: df_filtered = df_filtered[df_filtered["Es Estructural"] == 'Sí']
    if search_query:
        mask = df_filtered.apply(lambda row: row.astype(str).str.lower().str.contains(search_query.lower()).any(), axis=1)
        df_filtered = df_filtered[mask]

    st.subheader(f"Resultados ({len(df_filtered)})")
    
    selected_cols = st.multiselect("Columnas visibles:", df_filtered.columns, 
                                   default=['Autor', 'Es Estructural', 'Es Contacto', 'Correos', 'Rol', 'Empresa', 'Region'])
    
    st.dataframe(df_filtered[selected_cols], use_container_width=True, height=300)

    st.markdown("### 📧 Base de Contactos")

    if 'leads_df' not in st.session_state:
        st.session_state.leads_df = load_leads()

    if st.button("🔄 Actualizar base desde datos actuales"):
        n_new, st.session_state.leads_df = update_leads_from_df(df)
        st.success(f"Se agregaron {n_new} correos nuevos a la base.")

    leads_df = st.session_state.leads_df

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        solo_no_contactados = st.checkbox("Solo no contactados", key="f_leads_no_contact")
    with col_l2:
        solo_estructural_leads = st.checkbox("Solo estructurales", key="f_leads_struct")
    leads_search = st.text_input("Buscar en base de contactos:", key="f_leads_search")

    leads_filtered = leads_df.copy()
    if not leads_filtered.empty:
        if solo_no_contactados:
            leads_filtered = leads_filtered[leads_filtered["Contactado"] == False]
        if solo_estructural_leads:
            leads_filtered = leads_filtered[leads_filtered["Es Estructural"] == "Sí"]
        if leads_search:
            mask = leads_filtered.apply(lambda row: row.astype(str).str.lower().str.contains(leads_search.lower()).any(), axis=1)
            leads_filtered = leads_filtered[mask]

    st.write(f"**{len(leads_filtered)}** contactos mostrados (de **{len(leads_df)}** totales en la base).")

    edited_leads = st.data_editor(
        leads_filtered,
        column_config={"Contactado": st.column_config.CheckboxColumn("Contactado")},
        disabled=[c for c in LEADS_COLUMNS if c != "Contactado"],
        use_container_width=True,
        height=300,
        key="leads_editor",
    )

    if st.button("💾 Guardar cambios"):
        leads_df.update(edited_leads)
        st.session_state.leads_df = leads_df
        save_leads(leads_df)
        st.success("Cambios guardados.")

    if not leads_df.empty:
        csv_bytes = leads_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Descargar Contactos_Emails.csv", data=csv_bytes, file_name="Contactos_Emails.csv", mime="text/csv")

    st.markdown("### 👁️ Detalle del Post")
    if not df_filtered.empty:
        post_options = [f"[{idx}] {_disp(row.get('Autor'), 'Desconocido')} - {_disp(row.get('Rol'))}" for idx, row in df_filtered.iterrows()]
        selected_post_str = st.selectbox("Selecciona un post para leer:", post_options)
        if selected_post_str:
            idx = int(selected_post_str.split(']')[0].replace('[', ''))
            post_row = df_filtered.loc[idx]
            
            st.markdown(f'''
            <div class="post-card">
                <h4>👤 {_disp(post_row.get("Autor"))}</h4>
                <p><b>🏢 Empresa Contacto:</b> {_disp(post_row.get("Empresa Contacto"))} | <b>📍 Región:</b> {_disp(post_row.get("Region"))}</p>
                <p><b>📧 Correos Detectados:</b> <span style="color:#00e676">{_disp(post_row.get("Correos"), "Ninguno")}</span></p>
                <p><b>🤖 IA Score:</b> {post_row.get("Score", 0)} | <b>🛠️ Rol:</b> {_disp(post_row.get("Rol"))}</p>
                <hr>
                <p>{_disp(post_row.get("Texto"), "Sin texto")}</p>
                <a href="{post_row.get("URL Perfil", "#")}" target="_blank">🔗 Ver Perfil en LinkedIn</a>
            </div>
            ''', unsafe_allow_html=True)


# ==========================================
# PESTAÑA 3: ENTRENAMIENTO
# ==========================================
with tab3:
    st.markdown("### 🧠 Centro de Entrenamiento del Bot")
    st.write("Enséñale a la IA clasificando posts manualmente. Estos datos se guardarán en `training_data.json` para mejorar la precisión futura del bot.")
    
    # Preparar datos sin entrenar
    trained_texts = [item.get("text", "") for item in st.session_state.training_data]
    df_untrained = df[~df["Texto"].isin(trained_texts)]
    
    if df_untrained.empty:
        st.success("¡Felicidades! Has revisado todos los posts exportados actualmente.")
    else:
        # Asegurar que el index no se pase de largo
        if st.session_state.training_idx >= len(df_untrained):
            st.session_state.training_idx = 0
            
        current_post = df_untrained.iloc[st.session_state.training_idx]
        
        st.progress((st.session_state.training_idx) / len(df_untrained))
        st.write(f"Viendo post **{st.session_state.training_idx + 1}** de **{len(df_untrained)}** sin clasificar.")
        
        st.markdown(f'''
        <div class="post-card">
            <p><b>Texto del Post:</b></p>
            <p><i>"{current_post.get("Texto", "")}"</i></p>
        </div>
        ''', unsafe_allow_html=True)
        
        st.markdown("**¿Cómo clasificarías este post?**")
        c1, c2, c3, c4, c5 = st.columns(5)

        def save_classification(label, is_structural, is_seeker=False):
            new_item = {
                "text": current_post.get("Texto", ""),
                "is_job_offer": label,
                "is_structural": is_structural,
                "is_seeker": is_seeker,
                "labeled_at": str(datetime.now())
            }
            st.session_state.training_data.append(new_item)
            save_training_data(st.session_state.training_data)
            # Avanzar al siguiente
            st.session_state.training_idx += 1

        with c1:
            if st.button("🏗️ Oferta Estructural", use_container_width=True, type="primary"):
                save_classification(True, True)
                st.rerun()
        with c2:
            if st.button("✅ Oferta General (No Estructural)", use_container_width=True):
                save_classification(True, False)
                st.rerun()
        with c3:
            if st.button("🙋 Postulante (busca pega)", use_container_width=True):
                save_classification(False, False, is_seeker=True)
                st.rerun()
        with c4:
            if st.button("🗑️ Basura / No es oferta", use_container_width=True):
                save_classification(False, False)
                st.rerun()
        with c5:
            if st.button("⏭️ Saltar", use_container_width=True):
                st.session_state.training_idx += 1
                st.rerun()

    st.markdown("---")
    st.markdown("#### Datos de Entrenamiento")
    st.write(f"Has clasificado un total de **{len(st.session_state.training_data)}** posts.")

    if github_sync_enabled():
        st.caption("✅ Cada clasificación se guarda automáticamente en GitHub, así que tú y tu colega comparten el mismo progreso sin pasos manuales.")
    else:
        st.caption("⚠️ La sincronización con GitHub no está configurada: este progreso solo vive en esta sesión y se perderá al reiniciar la app.")

    # Boton de descarga para respaldar/compartir el progreso
    if len(st.session_state.training_data) > 0:
        json_string = json.dumps(st.session_state.training_data, ensure_ascii=False, indent=2)
        st.download_button(
            label="⬇️ Descargar `training_data.json`",
            file_name="training_data.json",
            mime="application/json",
            data=json_string
        )

    st.markdown("##### 🔄 Fusionar entrenamiento de un colega")
    st.caption(
        "Sube un `training_data.json` (descargado por tu colega u otra sesión) para fusionarlo "
        "con el progreso actual."
    )
    uploaded_training = st.file_uploader("Subir training_data.json", type="json", key="training_uploader")
    if uploaded_training is not None:
        try:
            incoming = json.load(uploaded_training)
            existing_texts = {item.get("text", "") for item in st.session_state.training_data}
            new_items = [item for item in incoming if item.get("text", "") not in existing_texts]
            if new_items:
                st.session_state.training_data.extend(new_items)
                save_training_data(st.session_state.training_data)
                st.success(f"Se fusionaron {len(new_items)} clasificaciones nuevas. Total: {len(st.session_state.training_data)}.")
            else:
                st.info("El archivo subido no contiene clasificaciones nuevas.")
        except (json.JSONDecodeError, AttributeError):
            st.error("El archivo subido no es un training_data.json válido.")
