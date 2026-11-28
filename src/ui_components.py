"""Design System e componentes visuais de engenharia para o PackMeasure.

Fornece estilos CSS centralizados, ilustrações técnicas em SVG, formatação pt-BR,
componentes de hardware e tabelas para a interface Streamlit.
"""

from __future__ import annotations

import html
import textwrap
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from src.capture import CameraConfig, StereoCameraCapture, StereoPair
from src.packaging import (
    DEFAULT_MARGIN_PER_FACE,
    DEFAULT_MIN_OCCUPANCY_THRESHOLD,
    DEFAULT_WALL_THICKNESS,
    PackageEvaluation,
    PackageFit,
    PackageStatus,
    RecommendationResult,
)

# ============================================================================
# Paleta de Cores e Constantes do Design System
# ============================================================================

COLOR_BG_MAIN = "#0F172A"       # Slate 900
COLOR_BG_CARD = "#1E293B"       # Slate 800
COLOR_BG_SURFACE = "#162032"    # Slate 850
COLOR_PRIMARY = "#14B8A6"       # Teal 500
COLOR_PRIMARY_HOVER = "#0D9488" # Teal 600
COLOR_BORDER = "#334155"        # Slate 700
COLOR_TEXT_MAIN = "#F1F5F9"     # Slate 100
COLOR_TEXT_MUTED = "#94A3B8"    # Slate 400

# Cores semânticas de status
STATUS_STYLES: Dict[PackageStatus, Dict[str, str]] = {
    PackageStatus.RECOMMENDED: {
        "label": "Recomendada",
        "bg": "rgba(16, 185, 129, 0.15)",
        "border": "#10B981",
        "text": "#34D399",
        "dot": "#10B981",
    },
    PackageStatus.ALTERNATIVE: {
        "label": "Alternativa",
        "bg": "rgba(245, 158, 11, 0.15)",
        "border": "#F59E0B",
        "text": "#FBBF24",
        "dot": "#F59E0B",
    },
    PackageStatus.NOT_RECOMMENDED: {
        "label": "Não indicada",
        "bg": "rgba(148, 163, 184, 0.12)",
        "border": "#64748B",
        "text": "#CBD5E1",
        "dot": "#94A3B8",
    },
    PackageStatus.INCOMPATIBLE: {
        "label": "Incompatível",
        "bg": "rgba(239, 68, 68, 0.15)",
        "border": "#EF4444",
        "text": "#F87171",
        "dot": "#EF4444",
    },
}


# ============================================================================
# Helper de Renderização HTML Segura e Sem Parsing Markdown
# ============================================================================


def render_html(raw_html: str) -> None:
    """Renderiza HTML diretamente no DOM do Streamlit.

    Aplica dedent() e strip() para eliminar recuos acidentais e utiliza st.html(),
    evitando que strings com quatro espaços de indentação sejam interpretadas
    como blocos de código pelo parser CommonMark.
    """
    clean_html = textwrap.dedent(raw_html).strip()
    st.html(clean_html)


# ============================================================================
# Formatadores pt-BR
# ============================================================================


def format_ptbr_num(val: Optional[float], decimals: int = 1) -> str:
    """Formata valor float no padrão pt-BR com separador decimal por vírgula."""
    if val is None:
        return "—"
    fmt = f"{{:,.{decimals}f}}".format(val)
    return fmt.replace(",", "X").replace(".", ",").replace("X", ".")


def format_currency(val: Optional[float]) -> str:
    """Formata moeda em Real (ex: R$ 8,30)."""
    if val is None:
        return "—"
    return f"R$ {format_ptbr_num(val, 2)}"


def format_percent(val: Optional[float], decimals: int = 1) -> str:
    """Formata porcentagem (ex: 31,8%)."""
    if val is None:
        return "—"
    return f"{format_ptbr_num(val, decimals)}%"


def format_dim(val: Optional[float]) -> str:
    """Formata dimensão em cm (ex: 20,0 cm)."""
    if val is None:
        return "—"
    return f"{format_ptbr_num(val, 1)} cm"


def format_liters(val_liters: Optional[float]) -> str:
    """Formata volume em litros (ex: 2,54 L)."""
    if val_liters is None:
        return "—"
    return f"{format_ptbr_num(val_liters, 2)} L"


# ============================================================================
# Estilos CSS Globais
# ============================================================================


def inject_global_styles() -> None:
    """Injeta regras CSS centralizadas para tipografia, espaçamentos e cards."""
    css = f"""
    <style>
    /* Tipografia e espaçamentos globais */
    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    .block-container {{
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
        max-width: 1380px !important;
    }}
    /* Cabeçalhos com hierarquia controlada */
    h1 {{
        font-size: 1.75rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        margin-bottom: 0.25rem !important;
        color: {COLOR_TEXT_MAIN} !important;
    }}
    h2 {{
        font-size: 1.25rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em !important;
        margin-top: 1.25rem !important;
        margin-bottom: 0.5rem !important;
        color: {COLOR_TEXT_MAIN} !important;
    }}
    h3 {{
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        margin-top: 1rem !important;
        margin-bottom: 0.35rem !important;
        color: {COLOR_TEXT_MAIN} !important;
    }}
    /* Cards com estética de instrumentação */
    .pm-card {{
        background: {COLOR_BG_CARD};
        border: 1px solid {COLOR_BORDER};
        border-radius: 8px;
        padding: 1.15rem;
        margin-bottom: 1rem;
        box-sizing: border-box;
    }}
    .pm-card-subtle {{
        background: {COLOR_BG_SURFACE};
        border: 1px solid {COLOR_BORDER};
        border-radius: 6px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.85rem;
        box-sizing: border-box;
    }}
    /* Métrica técnica destacada */
    .pm-metric-box {{
        background: {COLOR_BG_CARD};
        border: 1px solid {COLOR_BORDER};
        border-radius: 8px;
        padding: 0.9rem 1rem;
        text-align: left;
        box-sizing: border-box;
    }}
    .pm-metric-label {{
        font-size: 0.78rem;
        font-weight: 600;
        color: {COLOR_TEXT_MUTED};
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.3rem;
    }}
    .pm-metric-val {{
        font-size: 1.55rem;
        font-weight: 700;
        color: {COLOR_TEXT_MAIN};
        line-height: 1.1;
    }}
    .pm-metric-sub {{
        font-size: 0.75rem;
        color: {COLOR_TEXT_MUTED};
        margin-top: 0.25rem;
    }}
    /* Barra horizontal de ocupação volumétrica */
    .pm-progress-bg {{
        background: {COLOR_BORDER};
        border-radius: 4px;
        height: 8px;
        width: 100%;
        overflow: hidden;
        margin: 0.4rem 0;
    }}
    .pm-progress-fill {{
        background: {COLOR_PRIMARY};
        height: 100%;
        border-radius: 4px;
    }}
    /* Badge de status semântico */
    .pm-badge {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 3px 10px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        white-space: nowrap;
    }}
    /* Tabela HTML profissional */
    .pm-table {{
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        border: 1px solid {COLOR_BORDER};
        border-radius: 8px;
        overflow: hidden;
        margin: 0.75rem 0 1rem 0;
        font-size: 0.85rem;
        box-sizing: border-box;
    }}
    .pm-table th {{
        background: {COLOR_BG_SURFACE};
        color: {COLOR_TEXT_MUTED};
        font-weight: 600;
        text-align: left;
        padding: 10px 14px;
        border-bottom: 1px solid {COLOR_BORDER};
        text-transform: uppercase;
        font-size: 0.72rem;
        letter-spacing: 0.05em;
    }}
    .pm-table td {{
        padding: 11px 14px;
        border-bottom: 1px solid {COLOR_BORDER};
        color: {COLOR_TEXT_MAIN};
        background: {COLOR_BG_CARD};
        vertical-align: middle;
        line-height: 1.4;
    }}
    .pm-table tr:last-child td {{
        border-bottom: none;
    }}
    /* Viewport de Câmera 16:9 */
    .pm-camera-viewport {{
        position: relative;
        width: 100%;
        padding-top: 56.25%; /* 16:9 Aspect Ratio */
        background: #090E17;
        border: 1px solid {COLOR_BORDER};
        border-radius: 8px;
        overflow: hidden;
        box-sizing: border-box;
    }}
    .pm-camera-placeholder {{
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: {COLOR_TEXT_MUTED};
        text-align: center;
        padding: 1rem;
        box-sizing: border-box;
    }}
    /* Ajustes em abas e botões do Streamlit */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 6px 6px 0 0;
        padding: 8px 18px;
        font-weight: 600;
        font-size: 0.88rem;
    }}
    div[data-testid="stSidebarNav"] {{
        padding-top: 0.5rem;
    }}
    </style>
    """
    render_html(css)


# ============================================================================
# Ilustrações Técnicas em SVG
# ============================================================================


def get_logo_svg(size: int = 34) -> str:
    """Retorna o símbolo de caixa isométrica com eixos cartesianos em SVG."""
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M20 4L36 12.5V28L20 36.5L4 28V12.5L20 4Z" stroke="{COLOR_PRIMARY}" stroke-width="2.2" stroke-linejoin="round" fill="{COLOR_BG_CARD}"/>
<path d="M20 20.5V36.5" stroke="{COLOR_PRIMARY}" stroke-width="2.2" stroke-linejoin="round"/>
<path d="M20 20.5L36 12.5" stroke="{COLOR_PRIMARY}" stroke-width="2.2" stroke-linejoin="round"/>
<path d="M20 20.5L4 12.5" stroke="{COLOR_PRIMARY}" stroke-width="2.2" stroke-linejoin="round"/>
<circle cx="20" cy="20.5" r="2.5" fill="#38BDF8"/>
<circle cx="20" cy="4" r="2" fill="{COLOR_PRIMARY}"/>
<circle cx="4" cy="28" r="2" fill="{COLOR_PRIMARY}"/>
<circle cx="36" cy="28" r="2" fill="{COLOR_PRIMARY}"/>
</svg>"""


def get_package_schematic_svg(size_id: str, width: int = 140, height: int = 100) -> str:
    """Gera ilustração isométrica proporcional da embalagem (P, M, G, GG)."""
    props = {
        "caixa_p": {"w": 65, "d": 45, "h": 24, "label": "P"},
        "caixa_m": {"w": 75, "d": 55, "h": 36, "label": "M"},
        "caixa_g": {"w": 85, "d": 65, "h": 65, "label": "G"},
        "caixa_gg": {"w": 105, "d": 80, "h": 72, "label": "GG"},
    }
    cfg = props.get(size_id, props["caixa_m"])
    pw, pd, ph = cfg["w"], cfg["d"], cfg["h"]

    cx, cy = width / 2, height / 2 + (ph * 0.25)
    dx = pw * 0.45
    dy = pw * 0.22
    dz = pd * 0.40
    dw = pd * 0.20
    h_px = ph * 0.55

    p_top = f"{cx},{cy - h_px - dy - dw} {cx + dx},{cy - h_px - dw} {cx + dx - dz},{cy - h_px} {cx - dz},{cy - h_px - dy}"
    p_left = f"{cx - dz},{cy - h_px - dy} {cx + dx - dz},{cy - h_px} {cx + dx - dz},{cy} {cx - dz},{cy - dy}"
    p_right = f"{cx + dx - dz},{cy - h_px} {cx + dx},{cy - h_px - dw} {cx + dx},{cy - dw} {cx + dx - dz},{cy}"

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg">
<polygon points="{p_top}" fill="#334155" stroke="{COLOR_PRIMARY}" stroke-width="1.4" stroke-linejoin="round"/>
<polygon points="{p_left}" fill="#1E293B" stroke="{COLOR_PRIMARY}" stroke-width="1.4" stroke-linejoin="round"/>
<polygon points="{p_right}" fill="#0F172A" stroke="{COLOR_PRIMARY}" stroke-width="1.4" stroke-linejoin="round"/>
<text x="{cx}" y="{height - 6}" font-family="Inter, sans-serif" font-size="11" font-weight="700" fill="{COLOR_PRIMARY}" text-anchor="middle">{cfg['label']}</text>
</svg>"""


def get_chessboard_svg(width: int = 180, height: int = 126) -> str:
    """Gera visualização esquemática de tabuleiro de xadrez 10x7 quadrados (9x6 cantos internos)."""
    cols = 10
    rows = 7
    sq_w = width / cols
    sq_h = height / rows

    rects = []
    for r in range(rows):
        for c in range(cols):
            fill_c = "#E2E8F0" if (r + c) % 2 == 0 else "#1E293B"
            x = c * sq_w
            y = r * sq_h
            rects.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{sq_w:.1f}" height="{sq_h:.1f}" fill="{fill_c}"/>')

    corners = []
    for r in range(1, rows):
        for c in range(1, cols):
            cx = c * sq_w
            cy = r * sq_h
            corners.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="1.6" fill="{COLOR_PRIMARY}"/>')

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" style="border: 1px solid {COLOR_BORDER}; border-radius: 4px;">
{''.join(rects)}
{''.join(corners)}
</svg>"""


def get_tech_placeholder_svg(kind: str = "camera") -> str:
    """Retorna ícones SVG específicos para cada etapa do pipeline técnico."""
    if kind == "rectified":
        return f"""<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="{COLOR_TEXT_MUTED}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
<rect x="2" y="3" width="9" height="18" rx="1.5"></rect>
<rect x="13" y="3" width="9" height="18" rx="1.5"></rect>
<line x1="2" y1="9" x2="22" y2="9" stroke-dasharray="2 2"></line>
<line x1="2" y1="15" x2="22" y2="15" stroke-dasharray="2 2"></line>
</svg>"""
    elif kind == "disparity":
        return f"""<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="{COLOR_TEXT_MUTED}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
<rect x="3" y="3" width="18" height="18" rx="2"></rect>
<path d="M7 17l4-4 3 3 4-4"></path>
<circle cx="8" cy="8" r="1.5"></circle>
</svg>"""
    elif kind == "pointcloud":
        return f"""<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="{COLOR_TEXT_MUTED}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
<circle cx="12" cy="12" r="1.5" fill="{COLOR_PRIMARY}"></circle>
<circle cx="7" cy="8" r="1.2" fill="{COLOR_TEXT_MUTED}"></circle>
<circle cx="17" cy="8" r="1.2" fill="{COLOR_TEXT_MUTED}"></circle>
<circle cx="6" cy="16" r="1.2" fill="{COLOR_TEXT_MUTED}"></circle>
<circle cx="18" cy="16" r="1.2" fill="{COLOR_TEXT_MUTED}"></circle>
<circle cx="12" cy="5" r="1.2" fill="{COLOR_TEXT_MUTED}"></circle>
<circle cx="12" cy="19" r="1.2" fill="{COLOR_TEXT_MUTED}"></circle>
</svg>"""
    # Padrão: Câmera
    return f"""<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="{COLOR_TEXT_MUTED}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
<circle cx="12" cy="13" r="4"></circle>
</svg>"""


# ============================================================================
# Componentes Visuais Reutilizáveis
# ============================================================================


def render_header(title: str, subtitle: str) -> None:
    """Renderiza o cabeçalho compacto padronizado da página."""
    render_html(f"""
    <div style="margin-bottom: 1.25rem;">
        <h1 style="display: flex; align-items: center; gap: 10px;">
            {html.escape(title)}
        </h1>
        <div style="color: {COLOR_TEXT_MUTED}; font-size: 0.92rem; font-weight: 500;">
            {html.escape(subtitle)}
        </div>
    </div>
    """)


def render_metric_card(label: str, value: str, subtext: str = "") -> str:
    """Retorna HTML estilizado de card métrico."""
    sub_html = f'<div class="pm-metric-sub">{html.escape(subtext)}</div>' if subtext else ""
    return f"""<div class="pm-metric-box">
<div class="pm-metric-label">{html.escape(label)}</div>
<div class="pm-metric-val">{html.escape(value)}</div>
{sub_html}
</div>"""


def render_status_badge(status: PackageStatus) -> str:
    """Retorna badge HTML semântico com contraste adequado."""
    cfg = STATUS_STYLES.get(status, STATUS_STYLES[PackageStatus.NOT_RECOMMENDED])
    return (
        f'<span class="pm-badge" style="background:{cfg["bg"]}; border:1px solid {cfg["border"]}; color:{cfg["text"]};">'
        f'<span style="width:7px; height:7px; border-radius:50%; background:{cfg["dot"]};"></span>'
        f'{cfg["label"]}</span>'
    )


def render_camera_viewport_placeholder(label: str, subtext: str = "Dispositivo inativo", kind: str = "camera") -> str:
    """Gera placeholder de câmera 16:9 discreto quando desconectada."""
    svg_icon = get_tech_placeholder_svg(kind)
    return f"""<div class="pm-camera-viewport">
<div class="pm-camera-placeholder">
{svg_icon}
<div style="font-weight: 600; font-size: 0.9rem; margin-top: 0.5rem; color:{COLOR_TEXT_MAIN};">{html.escape(label)}</div>
<div style="font-size: 0.78rem; color:{COLOR_TEXT_MUTED}; margin-top: 0.2rem;">{html.escape(subtext)}</div>
</div>
</div>"""


# ============================================================================
# Barra Lateral de Controle de Hardware e Parâmetros
# ============================================================================


def render_sidebar_hardware_and_params(show_advanced: bool = True) -> None:
    """Renderiza a barra lateral unificada para controle das câmeras e parâmetros."""
    with st.sidebar:
        # Identidade PackMeasure no topo
        render_html(f"""
        <div style="display: flex; align-items: center; gap: 10px; padding: 0.25rem 0 0.85rem 0; border-bottom: 1px solid {COLOR_BORDER}; margin-bottom: 0.85rem;">
            {get_logo_svg(36)}
            <div>
                <div style="font-weight: 700; font-size: 1.15rem; color: {COLOR_TEXT_MAIN}; letter-spacing: -0.02em;">PackMeasure</div>
                <div style="font-size: 0.72rem; color: {COLOR_TEXT_MUTED}; text-transform: uppercase; letter-spacing: 0.05em;">Sistema de Visão Estéreo</div>
            </div>
        </div>
        """)

        st.markdown("### Dispositivos de Vídeo")

        col_dev1, col_dev2 = st.columns(2)
        with col_dev1:
            left_val = st.text_input(
                "Esq. (Ref):",
                value=st.session_state.get("left_camera_index", "0"),
                help="Índice V4L2 (/dev/videoX) ou caminho da câmera esquerda.",
                key="sb_left_idx",
            )
            st.session_state["left_camera_index"] = left_val

        with col_dev2:
            right_val = st.text_input(
                "Dir. (Aux):",
                value=st.session_state.get("right_camera_index", "2"),
                help="Índice V4L2 (/dev/videoX) ou caminho da câmera direita.",
                key="sb_right_idx",
            )
            st.session_state["right_camera_index"] = right_val

        resolutions = [
            "1280 × 720 (HD)",
            "640 × 480 (VGA)",
            "1920 × 1080 (FHD)",
        ]
        chosen_res = st.selectbox(
            "Resolução de captura:",
            options=resolutions,
            index=0,
            key="sb_res_select",
        )
        st.session_state["resolution_label"] = chosen_res

        cam_active = (
            st.session_state.get("stereo_camera") is not None
            and st.session_state.get("camera_streaming", False)
        )

        col_btn_start, col_btn_stop = st.columns(2)
        with col_btn_start:
            if st.button("Conectar", use_container_width=True, type="primary", disabled=cam_active):
                from pages.medir_objeto import get_resolution_dimensions, start_cameras
                w, h = get_resolution_dimensions(chosen_res)
                ok, msg = start_cameras(left_val, right_val, w, h)
                if ok:
                    st.rerun()
                else:
                    st.session_state["camera_error"] = msg
                    st.rerun()

        with col_btn_stop:
            if st.button("Desconectar", use_container_width=True, disabled=not cam_active):
                from pages.medir_objeto import stop_cameras
                stop_cameras()
                st.rerun()

        dot_left = "#10B981" if cam_active else "#64748B"
        dot_right = "#10B981" if cam_active else "#64748B"
        txt_left = "Conectada" if cam_active else "Desconectada"
        txt_right = "Conectada" if cam_active else "Desconectada"

        render_html(f"""
        <div style="background:{COLOR_BG_CARD}; border:1px solid {COLOR_BORDER}; border-radius:6px; padding:0.65rem 0.85rem; margin: 0.75rem 0 1rem 0; font-size:0.8rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                <span style="color:{COLOR_TEXT_MUTED};">Câmera Esquerda:</span>
                <span style="display:flex; align-items:center; gap:5px; font-weight:600; color:{COLOR_TEXT_MAIN};">
                    <span style="width:7px; height:7px; border-radius:50%; background:{dot_left};"></span>{txt_left}
                </span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                <span style="color:{COLOR_TEXT_MUTED};">Câmera Direita:</span>
                <span style="display:flex; align-items:center; gap:5px; font-weight:600; color:{COLOR_TEXT_MAIN};">
                    <span style="width:7px; height:7px; border-radius:50%; background:{dot_right};"></span>{txt_right}
                </span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:{COLOR_TEXT_MUTED};">Calibração Estéreo:</span>
                <span style="display:flex; align-items:center; gap:5px; font-weight:600; color:{COLOR_TEXT_MUTED};">
                    <span style="width:7px; height:7px; border-radius:50%; background:#EF4444;"></span>Indisponível
                </span>
            </div>
        </div>
        """)

        if st.session_state.get("camera_error"):
            with st.expander("Falha na inicialização das câmeras", expanded=False):
                st.caption(f"Detalhes: {st.session_state['camera_error']}")

        if show_advanced:
            with st.expander("Parâmetros do Recomendador", expanded=False):
                margin_val = st.number_input(
                    "Margem por face (cm):",
                    min_value=0.0,
                    max_value=10.0,
                    value=float(st.session_state.get("margin_per_face", DEFAULT_MARGIN_PER_FACE)),
                    step=0.1,
                    key="sb_margin",
                )
                st.session_state["margin_per_face"] = margin_val

                thick_val = st.number_input(
                    "Espessura parede (cm):",
                    min_value=0.0,
                    max_value=3.0,
                    value=float(st.session_state.get("wall_thickness", DEFAULT_WALL_THICKNESS)),
                    step=0.05,
                    key="sb_thick",
                )
                st.session_state["wall_thickness"] = thick_val

                thresh_val = st.slider(
                    "Limiar ocupação (%):",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(st.session_state.get("min_occupancy_threshold", DEFAULT_MIN_OCCUPANCY_THRESHOLD)),
                    step=1.0,
                    key="sb_thresh",
                )
                st.session_state["min_occupancy_threshold"] = thresh_val


# ============================================================================
# Tabela Comparativa e Card de Recomendação
# ============================================================================


def render_comparison_table_custom(evaluations: List[PackageEvaluation]) -> None:
    """Renderiza a tabela técnica de todas as embalagens com quebra de linha suave."""
    order_weights = {"caixa_p": 1, "caixa_m": 2, "caixa_g": 3, "caixa_gg": 4}
    sorted_evals = sorted(evaluations, key=lambda ev: order_weights.get(ev.package.id, 99))

    rows_html = []
    for ev in sorted_evals:
        pkg_name = html.escape(ev.package.name.replace("Caixa de Encomenda ", "Caixa "))
        int_d = ev.internal_dimensions
        int_str = f"{format_ptbr_num(int_d[0])} × {format_ptbr_num(int_d[1])} × {format_ptbr_num(int_d[2])} cm"
        vol_str = format_liters(ev.internal_volume / 1000.0)
        occ_str = format_percent(ev.occupancy_ratio) if ev.occupancy_ratio is not None else "—"
        price_str = format_currency(ev.price)
        badge_html = render_status_badge(ev.status)
        just_escaped = html.escape(ev.justification)

        row = f"""<tr>
<td style="font-weight: 600; white-space: nowrap;">{pkg_name}</td>
<td style="white-space: nowrap;">{int_str}<br><span style="color:{COLOR_TEXT_MUTED}; font-size:0.75rem;">{vol_str}</span></td>
<td>{badge_html}</td>
<td style="font-weight: 600; white-space: nowrap;">{occ_str}</td>
<td style="white-space: nowrap;">{price_str}</td>
<td style="color:{COLOR_TEXT_MUTED}; font-size:0.8rem; min-width: 250px; word-break: break-word;">{just_escaped}</td>
</tr>"""
        rows_html.append(row)

    table_html = f"""<div style="overflow-x: auto; margin-top: 0.5rem; margin-bottom: 1rem;">
<table class="pm-table">
<thead>
<tr>
<th>Modelo</th>
<th>Espaço Interno Útil</th>
<th>Status</th>
<th>Ocupação</th>
<th>Preço Ref.</th>
<th>Justificativa Técnica</th>
</tr>
</thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
</div>"""
    render_html(table_html)


def render_recommended_card_refactored(fit: Optional[PackageFit], has_compatible: bool) -> None:
    """Card de destaque da embalagem recomendada com ilustração esquemática."""
    if not has_compatible or fit is None:
        render_html(f"""
        <div class="pm-card" style="border-left: 4px solid #EF4444; margin-bottom: 1.25rem;">
            <div style="font-weight: 700; color: #F87171; font-size: 1.05rem; margin-bottom: 0.3rem;">
                Nenhuma embalagem compatível identificada
            </div>
            <div style="color: {COLOR_TEXT_MUTED}; font-size: 0.88rem; line-height: 1.4;">
                As dimensões do objeto, acrescidas da margem de segurança configurada,
                excedem o espaço interno útil de todas as caixas padronizadas do catálogo.
            </div>
        </div>
        """)
        return

    pkg = fit.package
    int_d = fit.internal_dimensions
    ori = fit.orientation
    occ = fit.occupancy_ratio
    svg_box = get_package_schematic_svg(pkg.id, width=120, height=85)

    card_html = f"""<div class="pm-card" style="border-left: 4px solid {COLOR_PRIMARY}; margin-bottom: 1.25rem;">
<div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem;">
<div style="display: flex; align-items: center; gap: 1.25rem;">
<div style="flex-shrink: 0;">
{svg_box}
</div>
<div>
<div style="font-size: 0.75rem; text-transform: uppercase; color: {COLOR_TEXT_MUTED}; font-weight: 600; letter-spacing: 0.05em;">
Embalagem Recomendada
</div>
<div style="font-size: 1.35rem; font-weight: 700; color: {COLOR_TEXT_MAIN}; line-height: 1.2;">
{html.escape(pkg.name)}
</div>
<div style="font-size: 0.82rem; color: {COLOR_TEXT_MUTED}; margin-top: 2px;">
Dimensões externas: {format_ptbr_num(pkg.length)} × {format_ptbr_num(pkg.width)} × {format_ptbr_num(pkg.height)} cm
</div>
</div>
</div>

<div style="text-align: right;">
<div>{render_status_badge(PackageStatus.RECOMMENDED)}</div>
<div style="font-size: 1.6rem; font-weight: 800; color: {COLOR_PRIMARY}; margin-top: 4px;">
{format_currency(pkg.price)}
</div>
<div style="font-size: 0.72rem; color: {COLOR_TEXT_MUTED};">preço unitário de referência</div>
</div>
</div>

<div style="margin-top: 1rem; padding-top: 0.85rem; border-top: 1px solid {COLOR_BORDER};">
<div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: {COLOR_TEXT_MUTED}; margin-bottom: 2px;">
<span>Ocupação volumétrica útil do objeto: <strong style="color:{COLOR_TEXT_MAIN};">{format_percent(occ)}</strong></span>
<span>Espaço interno útil: <strong style="color:{COLOR_TEXT_MAIN};">{format_ptbr_num(int_d[0])} × {format_ptbr_num(int_d[1])} × {format_ptbr_num(int_d[2])} cm ({format_liters(fit.internal_volume / 1000.0)})</strong></span>
</div>
<div class="pm-progress-bg">
<div class="pm-progress-fill" style="width: {min(100.0, max(0.0, occ)):.1f}%;"></div>
</div>
<div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: {COLOR_TEXT_MUTED}; margin-top: 4px;">
<span>Folga restante por eixo: C: {format_ptbr_num(ori.clearance_length)} cm | L: {format_ptbr_num(ori.clearance_width)} cm | A: {format_ptbr_num(ori.clearance_height)} cm</span>
<span>{html.escape(ori.description.split('(')[0].strip())}</span>
</div>
</div>
</div>"""
    render_html(card_html)
