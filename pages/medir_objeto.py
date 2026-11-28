"""Página principal do PackMeasure — Medição tridimensional e recomendação de embalagens."""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import cv2
import streamlit as st

from src.capture import CameraConfig, StereoCameraCapture, StereoPair
from src.packaging import (
    DEFAULT_MARGIN_PER_FACE,
    DEFAULT_MIN_OCCUPANCY_THRESHOLD,
    DEFAULT_WALL_THICKNESS,
    PackageRecommender,
    RecommendationResult,
)
from src.ui_components import (
    format_dim,
    format_liters,
    format_ptbr_num,
    inject_global_styles,
    render_camera_viewport_placeholder,
    render_comparison_table_custom,
    render_header,
    render_html,
    render_metric_card,
    render_recommended_card_refactored,
    render_sidebar_hardware_and_params,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers de Gerenciamento de Hardware
# ============================================================================


def get_resolution_dimensions(res_label: str) -> Tuple[int, int]:
    """Mapeia o rótulo de resolução para largura e altura em pixels."""
    mapping = {
        "1280 × 720 (HD)": (1280, 720),
        "640 × 480 (VGA)": (640, 480),
        "1920 × 1080 (FHD)": (1920, 1080),
    }
    return mapping.get(res_label, (1280, 720))


def stop_cameras() -> None:
    """Libera os recursos das câmeras e zera os estados ativos."""
    cam: Optional[StereoCameraCapture] = st.session_state.get("stereo_camera")
    if cam is not None:
        try:
            cam.release()
        except Exception as exc:
            logger.warning("Erro ao liberar câmeras: %s", exc)
        st.session_state["stereo_camera"] = None

    st.session_state["camera_streaming"] = False
    st.session_state["last_live_pair"] = None


def start_cameras(left_src: str, right_src: str, width: int, height: int) -> Tuple[bool, str]:
    """Inicializa as câmeras estéreo."""
    stop_cameras()

    try:
        left_cfg = CameraConfig(
            source=left_src,
            width=width,
            height=height,
            fps=30,
            fourcc="MJPG",
            buffer_size=1,
        )
        right_cfg = CameraConfig(
            source=right_src,
            width=width,
            height=height,
            fps=30,
            fourcc=None,
            buffer_size=1,
        )

        stereo = StereoCameraCapture(
            left_config=left_cfg,
            right_config=right_cfg,
        )
        stereo.open()

        st.session_state["stereo_camera"] = stereo
        st.session_state["camera_streaming"] = True
        st.session_state["camera_error"] = None
        return True, "Câmeras conectadas com sucesso."
    except Exception as exc:
        st.session_state["stereo_camera"] = None
        st.session_state["camera_streaming"] = False
        st.session_state["camera_error"] = str(exc)
        return False, str(exc)


# ============================================================================
# Feed de Câmeras Não Bloqueante (Fragment)
# ============================================================================


@st.fragment(run_every="0.25s")
def render_live_camera_pair() -> None:
    """Renderiza os painéis de visualização em proporção 16:9 contínua."""
    cam: Optional[StereoCameraCapture] = st.session_state.get("stereo_camera")
    is_streaming = st.session_state.get("camera_streaming", False)

    col_l, col_r = st.columns(2)

    if cam is not None and is_streaming:
        try:
            pair = cam.read(flush_buffer=False)
            st.session_state["last_live_pair"] = pair

            rgb_l = cv2.cvtColor(pair.left, cv2.COLOR_BGR2RGB)
            rgb_r = cv2.cvtColor(pair.right, cv2.COLOR_BGR2RGB)

            res_l = f"{pair.left_resolution[0]} × {pair.left_resolution[1]}"
            res_r = f"{pair.right_resolution[0]} × {pair.right_resolution[1]}"

            with col_l:
                render_html(f"""
                <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:4px;">
                    <span style="font-weight:600;">Câmera Esquerda (Referência)</span>
                    <span style="color:#10B981; font-weight:600;">● Ao vivo ({res_l})</span>
                </div>
                """)
                st.image(rgb_l, use_container_width=True)

            with col_r:
                render_html(f"""
                <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:4px;">
                    <span style="font-weight:600;">Câmera Direita (Auxiliar)</span>
                    <span style="color:#10B981; font-weight:600;">● Ao vivo ({res_r})</span>
                </div>
                """)
                st.image(rgb_r, use_container_width=True)

        except Exception as exc:
            with col_l:
                render_html(render_camera_viewport_placeholder("Câmera Esquerda", f"Erro: {exc}"))
            with col_r:
                render_html(render_camera_viewport_placeholder("Câmera Direita", f"Erro: {exc}"))
    else:
        with col_l:
            render_html("""
            <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:4px;">
                <span style="font-weight:600;">Câmera Esquerda (Referência)</span>
                <span style="color:#64748B;">Desconectada</span>
            </div>
            """)
            render_html(render_camera_viewport_placeholder("Câmera Esquerda", "Aguardando conexão"))

        with col_r:
            render_html("""
            <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:4px;">
                <span style="font-weight:600;">Câmera Direita (Auxiliar)</span>
                <span style="color:#64748B;">Desconectada</span>
            </div>
            """)
            render_html(render_camera_viewport_placeholder("Câmera Direita", "Aguardando conexão"))


# ============================================================================
# Página Principal
# ============================================================================


def render_measure_page() -> None:
    """Renderiza a interface da página principal de medição."""
    inject_global_styles()
    render_sidebar_hardware_and_params(show_advanced=True)

    render_header(
        title="Medição tridimensional",
        subtitle="Aquisição de pares estéreo e recomendação dimensional de embalagens",
    )

    tab_cam, tab_demo = st.tabs([
        "Aquisição Estéreo",
        "Demonstração Manual",
    ])

    # ------------------------------------------------------------------------
    # ABA 1: Aquisição Estéreo
    # ------------------------------------------------------------------------
    with tab_cam:
        cam_active = (
            st.session_state.get("stereo_camera") is not None
            and st.session_state.get("camera_streaming", False)
        )
        captured_pair: Optional[StereoPair] = st.session_state.get("captured_pair")

        # Exibição dos painéis das câmeras
        if captured_pair is not None:
            col_l, col_r = st.columns(2)
            rgb_l = cv2.cvtColor(captured_pair.left, cv2.COLOR_BGR2RGB)
            rgb_r = cv2.cvtColor(captured_pair.right, cv2.COLOR_BGR2RGB)

            res_l = f"{captured_pair.left_resolution[0]} × {captured_pair.left_resolution[1]}"
            res_r = f"{captured_pair.right_resolution[0]} × {captured_pair.right_resolution[1]}"

            with col_l:
                render_html(f"""
                <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:4px;">
                    <span style="font-weight:600;">Câmera Esquerda (Referência)</span>
                    <span style="color:#38BDF8; font-weight:600;">● Par capturado ({res_l})</span>
                </div>
                """)
                st.image(rgb_l, use_container_width=True)

            with col_r:
                render_html(f"""
                <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:4px;">
                    <span style="font-weight:600;">Câmera Direita (Auxiliar)</span>
                    <span style="color:#38BDF8; font-weight:600;">● Par capturado ({res_r})</span>
                </div>
                """)
                st.image(rgb_r, use_container_width=True)
        else:
            render_live_camera_pair()

        # Espaçamento vertical entre os painéis de câmera e os botões
        render_html("<div style='margin-top: 16px;'></div>")

        # Barra de Ações Operacionais
        col_act1, col_act2, col_info = st.columns([1.3, 1.3, 3])
        with col_act1:
            capture_disabled = not cam_active or (captured_pair is not None)
            if st.button("Capturar par estéreo", use_container_width=True, type="primary", disabled=capture_disabled):
                cam = st.session_state.get("stereo_camera")
                if cam is not None and cam_active:
                    try:
                        pair = cam.read(flush_buffer=True)
                        cam.save_pair(pair=pair, directory="data/captures", prefix="meas")
                        st.session_state["captured_pair"] = pair
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Falha na captura: {exc}")

        with col_act2:
            new_meas_disabled = captured_pair is None
            if st.button("Nova captura", use_container_width=True, disabled=new_meas_disabled):
                st.session_state["captured_pair"] = None
                st.rerun()

        with col_info:
            if captured_pair is not None:
                render_html("""
                <div style="font-size:0.85rem; color:#38BDF8; padding:8px 0;">
                    Par estéreo registrado e congelado para inspeção. Arquivos salvos em <code>data/captures/</code>.
                </div>
                """)
            elif cam_active:
                render_html("""
                <div style="font-size:0.85rem; color:#10B981; padding:8px 0;">
                    Sensores operando em tempo real. Posicione o objeto no campo de visão comum.
                </div>
                """)
            else:
                render_html("""
                <div style="font-size:0.85rem; color:#94A3B8; padding:8px 0;">
                    Dispositivos desconectados. Ative a conexão na barra lateral.
                </div>
                """)

        if captured_pair is not None:
            render_html("""
            <div class="pm-card-subtle" style="margin-top: 12px; margin-bottom: 16px;">
                <div style="font-weight: 600; color: #F1F5F9; font-size: 0.85rem; margin-bottom: 2px;">
                    Medição automática por imagem indisponível
                </div>
                <div style="color: #94A3B8; font-size: 0.8rem; line-height: 1.4;">
                    A reconstrução tridimensional e a projeção de Bounding Box sobre o feed dependem
                    da calibração geométrica estéreo e do cálculo de disparidade.
                    Para avaliar a lógica de recomendação de embalagens, utilize a aba <strong>Demonstração Manual</strong>.
                </div>
            </div>
            """)

        # Espaçamento vertical antes dos indicadores dimensionais
        render_html("<div style='margin-top: 20px;'></div>")
        st.markdown("### Indicadores Dimensionais")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_html(render_metric_card("Comprimento", "—", "aguardando reconstrução"))
        with c2:
            render_html(render_metric_card("Largura", "—", "aguardando reconstrução"))
        with c3:
            render_html(render_metric_card("Altura", "—", "aguardando reconstrução"))
        with c4:
            render_html(render_metric_card("Volume Delimitador", "—", "caixa delimitadora 3D"))

        # Espaçamento vertical antes da seção técnica
        render_html("<div style='margin-top: 24px;'></div>")

        # Seção expansível de detalhes de visão computacional com ícones específicos
        with st.expander("Processamento de visão computacional", expanded=False):
            render_html("""
            <div style="font-size:0.82rem; color:#94A3B8; margin-bottom:0.85rem;">
                Visualizações técnicas intermediárias do pipeline estéreo tridimensional.
            </div>
            """)
            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                render_html(render_camera_viewport_placeholder("Imagens Retificadas", "Aguardando calibração epipolar", kind="rectified"))
            with col_t2:
                render_html(render_camera_viewport_placeholder("Mapa de Disparidade", "Aguardando correspondência estéreo", kind="disparity"))
            with col_t3:
                render_html(render_camera_viewport_placeholder("Nuvem de Pontos 3D", "Aguardando triangulação", kind="pointcloud"))

    # ------------------------------------------------------------------------
    # ABA 2: Demonstração Manual
    # ------------------------------------------------------------------------
    with tab_demo:
        render_html("""
        <div class="pm-card-subtle" style="margin-bottom: 1.25rem;">
            <div style="font-weight: 600; font-size: 0.88rem; color: #F1F5F9;">Simulação dimensional manual</div>
            <div style="font-size: 0.8rem; color: #94A3B8; margin-top: 2px;">
                Os valores informados abaixo são inseridos manualmente para teste do algoritmo de recomendação,
                espaço interno útil e ocupação volumétrica, não representando medições automáticas das câmeras.
            </div>
        </div>
        """)

        col_in1, col_in2, col_in3 = st.columns(3)
        with col_in1:
            in_l = st.number_input("Comprimento (cm):", min_value=0.1, max_value=200.0, value=20.0, step=0.5, key="demo_l")
        with col_in2:
            in_w = st.number_input("Largura (cm):", min_value=0.1, max_value=200.0, value=15.0, step=0.5, key="demo_w")
        with col_in3:
            in_h = st.number_input("Altura (cm):", min_value=0.1, max_value=200.0, value=8.0, step=0.5, key="demo_h")

        try:
            recommender = PackageRecommender()
            res: RecommendationResult = recommender.recommend(
                length=in_l,
                width=in_w,
                height=in_h,
                margin_per_face=st.session_state.get("margin_per_face", DEFAULT_MARGIN_PER_FACE),
                wall_thickness=st.session_state.get("wall_thickness", DEFAULT_WALL_THICKNESS),
                min_occupancy_threshold=st.session_state.get("min_occupancy_threshold", DEFAULT_MIN_OCCUPANCY_THRESHOLD),
            )

            render_html("<div style='margin-top: 16px;'></div>")
            st.markdown("### Indicadores do Objeto Analisado")
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                render_html(render_metric_card("Comprimento", format_dim(in_l), "dimensão manual"))
            with m2:
                render_html(render_metric_card("Largura", format_dim(in_w), "dimensão manual"))
            with m3:
                render_html(render_metric_card("Altura", format_dim(in_h), "dimensão manual"))
            with m4:
                vol_l = res.bounding_box_volume / 1000.0
                render_html(render_metric_card("Volume Delimitador", format_liters(vol_l), "caixa delimitadora"))

            render_html("<div style='margin-top: 20px;'></div>")
            st.markdown("### Recomendação de Embalagem")
            render_recommended_card_refactored(res.recommended, res.has_compatible)

            render_html("<div style='margin-top: 20px;'></div>")
            st.markdown("### Comparação de Todas as Embalagens")
            render_comparison_table_custom(res.evaluations)

            render_html(f"""
            <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 0.85rem; line-height: 1.4;">
                * <strong>Hipótese de projeto:</strong> Espaço interno útil estimado deduzindo {format_ptbr_num(res.wall_thickness)} cm por parede (chapa típica de papelão).
                Margem de segurança configurada: {format_ptbr_num(res.margin_per_face)} cm por face.
                Preços de referência avulsos oficiais não incluem tarifas de postagem.
            </div>
            """)

        except Exception as exc:
            st.error(f"Falha no processamento da recomendação: {exc}")


if __name__ == "__main__":
    render_measure_page()
