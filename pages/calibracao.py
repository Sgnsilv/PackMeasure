"""Painel de calibração geométrica estéreo do PackMeasure."""

from __future__ import annotations

import streamlit as st

from pages.medir_objeto import render_live_camera_pair
from src.ui_components import (
    format_ptbr_num,
    get_chessboard_svg,
    inject_global_styles,
    render_header,
    render_html,
    render_metric_card,
    render_sidebar_hardware_and_params,
)


def render_calibration_page() -> None:
    """Renderiza a página de calibração geométrica estéreo."""
    inject_global_styles()
    render_sidebar_hardware_and_params(show_advanced=False)

    render_header(
        title="Calibração estéreo",
        subtitle="Painel de instrumentação geométrica e retificação epipolar",
    )

    # ------------------------------------------------------------------------
    # 1. Indicador de Etapas do Pipeline
    # ------------------------------------------------------------------------
    render_html("""
    <div style="display: flex; gap: 8px; margin-bottom: 1.25rem; overflow-x: auto;">
        <div style="flex: 1; min-width: 130px; background: #1E293B; border-top: 3px solid #14B8A6; padding: 8px 12px; border-radius: 4px;">
            <div style="font-size: 0.7rem; color: #14B8A6; font-weight: 700; text-transform: uppercase;">Etapa 1</div>
            <div style="font-size: 0.82rem; font-weight: 600; color: #F1F5F9;">Configuração</div>
            <div style="font-size: 0.7rem; color: #94A3B8;">Padrão definido</div>
        </div>
        <div style="flex: 1; min-width: 130px; background: #1E293B; border-top: 3px solid #64748B; padding: 8px 12px; border-radius: 4px;">
            <div style="font-size: 0.7rem; color: #94A3B8; font-weight: 700; text-transform: uppercase;">Etapa 2</div>
            <div style="font-size: 0.82rem; font-weight: 600; color: #CBD5E1;">Captura</div>
            <div style="font-size: 0.7rem; color: #94A3B8;">0 pares coletados</div>
        </div>
        <div style="flex: 1; min-width: 130px; background: #1E293B; border-top: 3px solid #334155; padding: 8px 12px; border-radius: 4px;">
            <div style="font-size: 0.7rem; color: #64748B; font-weight: 700; text-transform: uppercase;">Etapa 3</div>
            <div style="font-size: 0.82rem; font-weight: 600; color: #64748B;">Otimização</div>
            <div style="font-size: 0.7rem; color: #64748B;">Pendente</div>
        </div>
        <div style="flex: 1; min-width: 130px; background: #1E293B; border-top: 3px solid #334155; padding: 8px 12px; border-radius: 4px;">
            <div style="font-size: 0.7rem; color: #64748B; font-weight: 700; text-transform: uppercase;">Etapa 4</div>
            <div style="font-size: 0.82rem; font-weight: 600; color: #64748B;">Validação</div>
            <div style="font-size: 0.7rem; color: #64748B;">Pendente</div>
        </div>
    </div>
    """)

    # ------------------------------------------------------------------------
    # 2. Configuração do Tabuleiro de Xadrez
    # ------------------------------------------------------------------------
    col_cfg, col_svg = st.columns([2.5, 1.2])

    with col_cfg:
        st.markdown("### Padrão Geométrico de Calibração")
        render_html("""
        <div style="font-size:0.8rem; color:#94A3B8; margin-bottom:0.75rem;">
            O algoritmo necessita de um padrão planar de xadrez rígido para estimar as distorções ópticas
            e a pose relativa entre as câmeras.
        </div>
        """)

        c_p1, c_p2, c_p3 = st.columns(3)
        with c_p1:
            st.number_input("Cantos horizontais:", value=9, disabled=True, help="Número de interseções internas de cantos ao longo da largura.")
        with c_p2:
            st.number_input("Cantos verticais:", value=6, disabled=True, help="Número de interseções internas de cantos ao longo da altura.")
        with c_p3:
            sq_size = st.number_input(
                "Tamanho do quadrado (mm):",
                min_value=1.0,
                max_value=100.0,
                value=25.0,
                step=0.5,
                help="Dimensão física exata do lado de cada quadrado do tabuleiro impresso.",
            )

    with col_svg:
        render_html(f"""
        <div style="text-align: center; padding: 0.5rem 0;">
            {get_chessboard_svg(width=160, height=112)}
            <div style="font-size: 0.7rem; color: #94A3B8; margin-top: 4px;">Padrão 10 × 7 quadrados (9 × 6 cantos)</div>
        </div>
        """)

    render_html("<div style='margin-top: 20px;'></div>")

    # ------------------------------------------------------------------------
    # 3. Painel de Câmeras e Ações de Coleta
    # ------------------------------------------------------------------------
    st.markdown("### Visualização das Câmeras e Coleta")
    render_live_camera_pair()

    # Espaçamento vertical entre os painéis e a seção de coleta
    render_html("<div style='margin-top: 20px;'></div>")

    # Container técnico coeso para meta, contador e barra de progresso
    with st.container(border=True):
        st.markdown(
            '<div style="font-weight: 600; font-size: 0.88rem; color: #F1F5F9; margin-bottom: 6px;">'
            'Amostragem de Pares Estéreo'
            '</div>',
            unsafe_allow_html=True,
        )

        col_prog1, col_prog2 = st.columns([1, 2])
        pairs_collected = 0

        with col_prog1:
            render_html(render_metric_card("Pares Coletados", f"{pairs_collected}", "meta de calibração"))

        with col_prog2:
            target_pairs = st.slider("Meta de amostragem:", min_value=10, max_value=60, value=30, step=5)
            prog_percent = min(1.0, pairs_collected / target_pairs)
            st.progress(prog_percent, text=f"Progresso: {pairs_collected} de {target_pairs} pares ({format_ptbr_num(prog_percent * 100, 0)}%)")

        render_html("""
        <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 4px;">
            A quantidade de pares é uma referência. A qualidade da calibração depende também da diversidade das poses do tabuleiro.
        </div>
        """)

    # Espaçamento antes dos botões de ação
    render_html("<div style='margin-top: 14px;'></div>")

    # Botões de controle operacional
    b1, b2, b3 = st.columns(3)
    with b1:
        st.button("Capturar par de calibração", use_container_width=True, disabled=True, help="Funcionalidade disponível após integração do detector de cantos.")
    with b2:
        st.button("Calibrar sistema estéreo", use_container_width=True, disabled=True, help="Funcionalidade disponível após integração do otimizador de calibração.")
    with b3:
        st.button("Exportar parâmetros", use_container_width=True, disabled=True, help="Permite gravar matrizes de retificação em disco.")

    # Espaçamento vertical antes dos cards de métricas
    render_html("<div style='margin-top: 24px;'></div>")

    # ------------------------------------------------------------------------
    # 4. Métricas e Parâmetros da Calibração
    # ------------------------------------------------------------------------
    st.markdown("### Métricas de Precisão Geométrica")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        render_html(render_metric_card("RMS Câmera Esq.", "—", "erro residual em pixels"))
    with m2:
        render_html(render_metric_card("RMS Câmera Dir.", "—", "erro residual em pixels"))
    with m3:
        render_html(render_metric_card("RMS Estéreo Total", "—", "reprojeção combinada"))
    with m4:
        render_html(render_metric_card("Distância entre Câmeras", "—", "baseline estéreo (T)"))

    # Espaçamento vertical antes do expansor de matrizes
    render_html("<div style='margin-top: 20px;'></div>")

    with st.expander("Matrizes intrínsecas, coeficientes de distorção e pose relativa", expanded=False):
        render_html("""
        <div style="font-size:0.8rem; color:#94A3B8; margin-bottom:0.75rem;">
            Os parâmetros calculados estarão disponíveis para inspeção técnica após a calibração com o padrão físico.
        </div>
        """)
        col_mat1, col_mat2 = st.columns(2)
        with col_mat1:
            st.markdown("""
            **Câmera Esquerda:**
            - Matriz Intrínseca ($K_1$): `—`
            - Coeficientes de Distorção ($D_1$): `—`
            """)
        with col_mat2:
            st.markdown("""
            **Câmera Direita & Relação Estéreo:**
            - Matriz Intrínseca ($K_2$): `—`
            - Coeficientes de Distorção ($D_2$): `—`
            - Matriz de Rotação ($R$): `—`
            - Vetor de Translação ($T$): `—`
            """)


if __name__ == "__main__":
    render_calibration_page()
