"""Aplicação principal do PackMeasure — Sistema de medição 3D e recomendação de embalagens."""

from __future__ import annotations

import streamlit as st

from src.packaging import (
    DEFAULT_MARGIN_PER_FACE,
    DEFAULT_MIN_OCCUPANCY_THRESHOLD,
    DEFAULT_WALL_THICKNESS,
)
from src.ui_components import inject_global_styles

# Configuração global de página
st.set_page_config(
    page_title="PackMeasure",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Injeção dos estilos CSS padronizados do tema
inject_global_styles()

# Inicialização de estado compartilhado (session_state)
if "stereo_camera" not in st.session_state:
    st.session_state["stereo_camera"] = None
if "camera_streaming" not in st.session_state:
    st.session_state["camera_streaming"] = False
if "left_camera_index" not in st.session_state:
    st.session_state["left_camera_index"] = "0"
if "right_camera_index" not in st.session_state:
    st.session_state["right_camera_index"] = "2"
if "resolution_label" not in st.session_state:
    st.session_state["resolution_label"] = "1280 × 720 (HD)"
if "margin_per_face" not in st.session_state:
    st.session_state["margin_per_face"] = DEFAULT_MARGIN_PER_FACE
if "wall_thickness" not in st.session_state:
    st.session_state["wall_thickness"] = DEFAULT_WALL_THICKNESS
if "min_occupancy_threshold" not in st.session_state:
    st.session_state["min_occupancy_threshold"] = DEFAULT_MIN_OCCUPANCY_THRESHOLD
if "captured_pair" not in st.session_state:
    st.session_state["captured_pair"] = None
if "last_live_pair" not in st.session_state:
    st.session_state["last_live_pair"] = None
if "camera_error" not in st.session_state:
    st.session_state["camera_error"] = None

# Configuração de navegação multipage com ícones minimalistas Material Symbols
pages = [
    st.Page(
        "pages/medir_objeto.py",
        title="Medir objeto",
        icon=":material/view_in_ar:",
        default=True,
    ),
    st.Page(
        "pages/calibracao.py",
        title="Calibração",
        icon=":material/tune:",
    ),
    st.Page(
        "pages/catalogo.py",
        title="Catálogo de embalagens",
        icon=":material/inventory_2:",
    ),
]

nav = st.navigation(pages)
nav.run()
