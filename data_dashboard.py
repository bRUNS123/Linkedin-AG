import streamlit as st
import pandas as pd
import plotly.express as px
import os
import json
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
        except:
            return []
    return []

def save_training_data(data):
    with open(TRAINING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

st.title("📊 Panel de Inteligencia - LinkedIn Scraper")

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
tab1, tab2, tab3 = st.tabs(["📈 Dashboard General", "🔎 Explorador de Datos", "🧠 Entrenamiento Bot"])

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

    st.markdown("### 📧 Exportar Correos")
    with st.expander("Ver lista de todos los correos recopilados"):
        all_emails = []
        for correos_str in df_filtered["Correos"].dropna():
            if correos_str:
                for em in correos_str.split(","):
                    em = em.strip()
                    if em and em not in all_emails:
                        all_emails.append(em)
        
        st.write(f"Se encontraron **{len(all_emails)}** correos únicos con los filtros actuales.")
        if all_emails:
            st.text_area("Copia estos correos (separados por coma):", value=", ".join(all_emails), height=150)

    st.markdown("### 👁️ Detalle del Post")
    if not df_filtered.empty:
        post_options = [f"[{idx}] {row.get('Autor', 'Desconocido')} - {row.get('Rol', '')}" for idx, row in df_filtered.iterrows()]
        selected_post_str = st.selectbox("Selecciona un post para leer:", post_options)
        if selected_post_str:
            idx = int(selected_post_str.split(']')[0].replace('[', ''))
            post_row = df_filtered.loc[idx]
            
            st.markdown(f'''
            <div class="post-card">
                <h4>👤 {post_row.get("Autor", "")}</h4>
                <p><b>🏢 Empresa Contacto:</b> {post_row.get("Empresa Contacto", "")} | <b>📍 Región:</b> {post_row.get("Region", "")}</p>
                <p><b>📧 Correos Detectados:</b> <span style="color:#00e676">{post_row.get("Correos", "Ninguno")}</span></p>
                <p><b>🤖 IA Score:</b> {post_row.get("Score", 0)} | <b>🛠️ Rol:</b> {post_row.get("Rol", "")}</p>
                <hr>
                <p>{post_row.get("Texto", "Sin texto")}</p>
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
        c1, c2, c3, c4 = st.columns(4)
        
        def save_classification(label, is_structural):
            new_item = {
                "text": current_post.get("Texto", ""),
                "is_job_offer": label,
                "is_structural": is_structural,
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
            if st.button("🗑️ Basura / No es oferta", use_container_width=True):
                save_classification(False, False)
                st.rerun()
        with c4:
            if st.button("⏭️ Saltar", use_container_width=True):
                st.session_state.training_idx += 1
                st.rerun()

    st.markdown("---")
    st.markdown("#### Datos de Entrenamiento")
    st.write(f"Has clasificado un total de **{len(st.session_state.training_data)}** posts.")
    
    # Boton de descarga para usuarios en la nube
    if len(st.session_state.training_data) > 0:
        json_string = json.dumps(st.session_state.training_data, ensure_ascii=False, indent=2)
        st.download_button(
            label="⬇️ Descargar `training_data.json` (Para uso en Streamlit Cloud)",
            file_name="training_data.json",
            mime="application/json",
            data=json_string
        )
