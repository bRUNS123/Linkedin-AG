import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime

# Configuracion de pagina
st.set_page_config(
    page_title="LinkedIn Scraper - Data Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo personalizado oscuro para encajar con el otro dashboard
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #16213e;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #2a2a4a;
    }
    h1, h2, h3 {
        color: #e0e0e0 !important;
    }
    </style>
""", unsafe_allow_html=True)

# Archivos de datos
ALL_OFFERS_FILE = "Todas_Ofertas.csv"
STRUCTURAL_FILE = "Ofertas_Estructurales.csv"

@st.cache_data(ttl=60) # Refrescar cada 60 segs si hay cambios
def load_data():
    if not os.path.exists(ALL_OFFERS_FILE):
        return pd.DataFrame(), pd.DataFrame()
    
    df_all = pd.read_csv(ALL_OFFERS_FILE)
    
    # Procesar fechas para graficos
    if 'Fecha' in df_all.columns:
        # Algunos formatos pueden venir de LinkedIn como '1w', '2d', o fechas reales.
        # Asumiremos que están mezclados, intentamos limpiar para visualizar.
        pass
        
    df_struct = pd.DataFrame()
    if os.path.exists(STRUCTURAL_FILE):
        df_struct = pd.read_csv(STRUCTURAL_FILE)
        
    return df_all, df_struct

st.title("📊 Panel de Análisis - LinkedIn Scraper")

df, df_struct = load_data()

if df.empty:
    st.warning(f"No se encontró el archivo '{ALL_OFFERS_FILE}'. Asegúrate de que el bot haya exportado los datos.")
    st.stop()

# ======= BARRA LATERAL =======
st.sidebar.header("Filtros")

# Filtro por IA validado
ia_filter = st.sidebar.radio("IA Validado", ["Todos", "Sí", "No"])

# Filtro si es Contacto
if 'Es Contacto' in df.columns:
    contact_filter = st.sidebar.radio("Proviene de Contacto", ["Todos", "Sí", "No"])
else:
    contact_filter = "Todos"

# Filtro con correos
has_email = st.sidebar.checkbox("Solo posts con correos")

# Aplicar filtros
df_filtered = df.copy()

if ia_filter != "Todos":
    df_filtered = df_filtered[df_filtered["IA Validado"] == ia_filter]

if contact_filter != "Todos":
    df_filtered = df_filtered[df_filtered["Es Contacto"] == contact_filter]

if has_email:
    # Correos no esta nulo y no esta vacio
    df_filtered = df_filtered[df_filtered["Correos"].notna() & (df_filtered["Correos"] != "")]

# Buscador de texto libre
search_query = st.sidebar.text_input("Buscador libre (texto, empresa, rol):")
if search_query:
    search_query = search_query.lower()
    mask = df_filtered.apply(lambda row: row.astype(str).str.lower().str.contains(search_query).any(), axis=1)
    df_filtered = df_filtered[mask]

# ======= KPIs =======
st.markdown("### Resumen")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Ofertas", f"{len(df):,}")
with col2:
    st.metric("Ofertas Filtradas", f"{len(df_filtered):,}")
with col3:
    st.metric("Estructurales", f"{len(df_struct):,}")
with col4:
    total_correos = len(df[df["Correos"].notna() & (df["Correos"] != "")])
    st.metric("Posts con Correos", f"{total_correos:,}")

st.markdown("---")

# ======= GRAFICOS =======
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Distribución de Roles de IA")
    if 'Rol' in df_filtered.columns and not df_filtered.empty:
        role_counts = df_filtered['Rol'].value_counts().reset_index()
        role_counts.columns = ['Rol', 'Cantidad']
        # Eliminar vacios
        role_counts = role_counts[role_counts['Rol'] != '']
        fig1 = px.bar(role_counts.head(10), x='Rol', y='Cantidad', 
                      title='Top 10 Roles detectados', 
                      color_discrete_sequence=['#e94560'])
        st.plotly_chart(fig1, use_container_width=True)
    else:
        st.info("Sin datos suficientes para roles.")

with col_chart2:
    st.subheader("Match con Contactos")
    if 'Es Contacto' in df_filtered.columns and not df_filtered.empty:
        contact_counts = df_filtered['Es Contacto'].value_counts().reset_index()
        contact_counts.columns = ['Es Contacto', 'Cantidad']
        fig2 = px.pie(contact_counts, values='Cantidad', names='Es Contacto',
                     title='Porcentaje de ofertas por contactos directos',
                     color_discrete_sequence=['#448aff', '#0f3460'])
        st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# ======= TABLA INTERACTIVA =======
st.subheader(f"Explorador de Ofertas ({len(df_filtered)} resultados)")

# Columnas seleccionables para mostrar
all_columns = list(df_filtered.columns)
default_cols = ['Autor', 'Es Contacto', 'Empresa Contacto', 'Correos', 'Region', 'Rol', 'Score']
# Asegurar que las columnas default existen
default_cols = [c for c in default_cols if c in all_columns]

selected_cols = st.multiselect("Columnas a mostrar:", all_columns, default=default_cols)

# Configuramos la vista de dataframe interactiva de Streamlit
st.dataframe(
    df_filtered[selected_cols],
    use_container_width=True,
    height=400
)

# ======= DETALLE DE OFERTA =======
st.subheader("Vista Detallada del Post")
if not df_filtered.empty:
    # Crear un selectbox con los posts filtrados
    post_options = []
    for idx, row in df_filtered.iterrows():
        autor = row.get('Autor', 'Desconocido')
        rol = row.get('Rol', 'Sin rol')
        post_options.append(f"[{idx}] {autor} - {rol}")
        
    selected_post_str = st.selectbox("Selecciona un post para ver el texto original:", post_options)
    if selected_post_str:
        idx_str = selected_post_str.split(']')[0].replace('[', '')
        idx = int(idx_str)
        post_row = df_filtered.loc[idx]
        
        st.info(f"**URL:** {post_row.get('URL Perfil', 'No disponible')}")
        st.write(post_row.get('Texto', 'Sin texto'))
else:
    st.info("No hay resultados para mostrar con los filtros actuales.")
