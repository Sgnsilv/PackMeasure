"""Página de catálogo de embalagens padronizadas do PackMeasure."""

from __future__ import annotations

import html

import streamlit as st

from src.packaging import (
    DEFAULT_WALL_THICKNESS,
    PackageRecommender,
)
from src.ui_components import (
    COLOR_BORDER,
    COLOR_PRIMARY,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    format_currency,
    format_liters,
    format_ptbr_num,
    get_package_schematic_svg,
    inject_global_styles,
    render_header,
    render_html,
    render_sidebar_hardware_and_params,
)


def render_catalog_page() -> None:
    """Renderiza a página com a grade de cards das embalagens e metadados."""
    inject_global_styles()
    render_sidebar_hardware_and_params(show_advanced=False)

    render_header(
        title="Catálogo de embalagens",
        subtitle="Modelos padronizados de caixas de papelão ondulado para despacho postal",
    )

    try:
        recommender = PackageRecommender()
        packages = recommender.packages
        metadata = recommender.metadata
        wall_thick = float(st.session_state.get("wall_thickness", DEFAULT_WALL_THICKNESS))
    except Exception as exc:
        st.error(f"Falha ao carregar o catálogo de embalagens: {exc}")
        return

    # ------------------------------------------------------------------------
    # Grade Responsiva de Cards (4 Colunas para P, M, G, GG)
    # ------------------------------------------------------------------------
    st.markdown("### Modelos Disponíveis")
    cols = st.columns(4)

    for idx, p in enumerate(packages):
        int_d = p.get_internal_dimensions(wall_thick)
        int_vol_l = p.get_internal_volume_liters(wall_thick)
        ext_vol_l = p.external_volume_liters
        svg_box = get_package_schematic_svg(p.id, width=130, height=85)
        short_name = p.name.replace("Caixa de Encomenda ", "Caixa ")

        with cols[idx % 4]:
            card_html = f"""<div class="pm-card" style="display: flex; flex-direction: column; justify-content: space-between; height: 100%; min-height: 420px; box-sizing: border-box; overflow: visible;">
<div>
<div style="text-align: center; padding: 0.5rem 0 0.75rem 0; border-bottom: 1px solid {COLOR_BORDER};">
{svg_box}
<div style="font-weight: 700; font-size: 1.05rem; color: {COLOR_TEXT_MAIN}; margin-top: 6px;">
{html.escape(short_name)}
</div>
<div style="font-size: 1.45rem; font-weight: 800; color: {COLOR_PRIMARY}; margin-top: 2px;">
{format_currency(p.price)}
</div>
<div style="font-size: 0.72rem; color: {COLOR_TEXT_MUTED};">preço unitário de referência</div>
</div>

<div style="padding: 0.85rem 0 0.5rem 0; font-size: 0.8rem; line-height: 1.5;">
<div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
<span style="color: {COLOR_TEXT_MUTED};">Dim. Externas:</span>
<span style="font-weight: 600; color: {COLOR_TEXT_MAIN};">{format_ptbr_num(p.length)}×{format_ptbr_num(p.width)}×{format_ptbr_num(p.height)} cm</span>
</div>
<div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
<span style="color: {COLOR_TEXT_MUTED};">Vol. Externo:</span>
<span style="color: {COLOR_TEXT_MAIN};">{format_liters(ext_vol_l)}</span>
</div>
<div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
<span style="color: {COLOR_TEXT_MUTED};">Espaço Útil:</span>
<span style="font-weight: 600; color: #38BDF8;">{format_ptbr_num(int_d[0])}×{format_ptbr_num(int_d[1])}×{format_ptbr_num(int_d[2])} cm</span>
</div>
<div style="display: flex; justify-content: space-between;">
<span style="color: {COLOR_TEXT_MUTED};">Volume Útil:</span>
<span style="font-weight: 700; color: #38BDF8;">{format_liters(int_vol_l)}</span>
</div>
</div>
</div>

<div style="border-top: 1px solid {COLOR_BORDER}; padding-top: 0.65rem; font-size: 0.74rem; color: {COLOR_TEXT_MUTED}; line-height: 1.4; word-break: break-word;">
{html.escape(p.description)}
</div>
</div>"""
            render_html(card_html)

    st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------------
    # Tabela Técnica Comparativa (Expansível)
    # ------------------------------------------------------------------------
    with st.expander("Tabela técnica comparativa", expanded=False):
        table_rows = []
        for p in packages:
            int_d = p.get_internal_dimensions(wall_thick)
            table_rows.append(f"""<tr>
<td style="font-weight:600; white-space:nowrap;">{html.escape(p.name)}</td>
<td style="white-space:nowrap;">{format_ptbr_num(p.length)} × {format_ptbr_num(p.width)} × {format_ptbr_num(p.height)} cm</td>
<td style="white-space:nowrap;">{format_liters(p.external_volume_liters)}</td>
<td style="font-weight:600; color:#38BDF8; white-space:nowrap;">{format_ptbr_num(int_d[0])} × {format_ptbr_num(int_d[1])} × {format_ptbr_num(int_d[2])} cm</td>
<td style="font-weight:700; color:#38BDF8; white-space:nowrap;">{format_liters(p.get_internal_volume_liters(wall_thick))}</td>
<td style="font-weight:600; color:{COLOR_PRIMARY}; white-space:nowrap;">{format_currency(p.price)}</td>
</tr>""")

        table_html = f"""<table class="pm-table">
<thead>
<tr>
<th>Modelo</th>
<th>Dimensões Externas</th>
<th>Vol. Externo</th>
<th>Espaço Interno Útil</th>
<th>Vol. Útil</th>
<th>Preço Ref.</th>
</tr>
</thead>
<tbody>
{''.join(table_rows)}
</tbody>
</table>"""
        render_html(table_html)

    # ------------------------------------------------------------------------
    # Informações Metodológicas e Fontes Oficiais
    # ------------------------------------------------------------------------
    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
    st.markdown("### Referências e Metodologia")
    with st.container(border=True):
        render_html(f"""
        <div style="font-size: 0.82rem; color: {COLOR_TEXT_MUTED}; line-height: 1.5;">
            <p style="margin-bottom: 6px;"><strong>Fontes de Consulta:</strong> Dados nominais de dimensões e preços de referência unitários foram obtidos
            através do simulador oficial de preços e prazos dos Correios (<a href="https://www2.correios.com.br/sistemas/precosPrazos/" target="_blank" style="color:{COLOR_PRIMARY}; text-decoration:none;">correios.com.br</a>)
            em <strong>{metadata.get('data_consulta', '27/11/2026')}</strong>.</p>
            <p style="margin-bottom: 6px;"><strong>Hipótese de Espessura de Parede:</strong> Como as especificações comerciais dos Correios publicam exclusivamente as medidas
            externas nominais da caixa montada, o espaço interno disponível é calculado assumindo chapa padrão de papelão ondulado de
            <strong>{format_ptbr_num(wall_thick)} cm por parede</strong> (dedução de {format_ptbr_num(2 * wall_thick)} cm em cada eixo tridimensional).</p>
            <p style="margin-bottom: 0;"><strong>Tarifas Postais:</strong> Os preços exibidos referem-se estritamente à compra avulsa da embalagem vazia e não guardam relação,
            cálculo ou estimativa de tarifas de postagem de serviços PAC ou SEDEX.</p>
        </div>
        """)


if __name__ == "__main__":
    render_catalog_page()
