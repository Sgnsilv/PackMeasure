
import streamlit as st

st.set_page_config(
    page_title="PackMeasure",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("PackMeasure")

st.subheader(
    "Medição tridimensional e recomendação de embalagens"
)

st.markdown("""
Sistema de medição de objetos utilizando visão estéreo
e técnicas clássicas de visão computacional.

**Funcionalidades previstas:**

- Aquisição de imagens estéreo.
- Calibração de câmeras.
- Reconstrução tridimensional.
- Estimativa de dimensões de objetos.
- Recomendação de embalagens dos Correios.
""")

st.info("Projeto em desenvolvimento.")
