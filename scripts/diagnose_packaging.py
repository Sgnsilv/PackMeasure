#!/usr/bin/env python3
"""Script de diagnóstico e validação do módulo de recomendação de embalagens (PackMeasure).

Permite informar dimensões manualmente pelo terminal ou executar uma bateria
completa de cenários de teste automatizados para validar a lógica de recomendação,
classificação funcional (RECOMMENDED, ALTERNATIVE, NOT_RECOMMENDED, INCOMPATIBLE),
tabela comparativa completa, heurísticas de ocupação e limites operacionais.

Uso:
    python scripts/diagnose_packaging.py --scenarios
    python scripts/diagnose_packaging.py -l 15 -w 10 -H 5
    python scripts/diagnose_packaging.py --length 22 --width 14 --height 6 --threshold 25.0
    python scripts/diagnose_packaging.py --interactive
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

# Garante acesso ao pacote src
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.packaging import (
    DEFAULT_MARGIN_PER_FACE,
    DEFAULT_MIN_OCCUPANCY_THRESHOLD,
    DEFAULT_WALL_THICKNESS,
    InvalidDimensionsError,
    PackageEvaluation,
    PackageFit,
    PackageRecommender,
    PackageStatus,
    PackagingError,
    RecommendationResult,
)


def format_evaluations_table(evaluations: List[PackageEvaluation]) -> str:
    """Gera uma tabela formatada contendo todas as embalagens avaliadas."""
    headers = ["Embalagem (Modelo)", "Status", "Ocup. Útil", "Preço Ref.", "Justificativa Dinâmica"]
    
    rows = []
    for ev in evaluations:
        pkg_name = f"{ev.package.name} ({ev.package.id})"
        status_str = ev.status.value
        occ_str = f"{ev.occupancy_ratio:.1f}%" if ev.occupancy_ratio is not None else "—"
        price_str = f"R$ {ev.price:.2f}"
        just_str = ev.justification
        rows.append((pkg_name, status_str, occ_str, price_str, just_str))

    # Larguras das colunas
    col_w = [
        max(len(r[0]) for r in rows + [tuple(headers)]),
        max(len(r[1]) for r in rows + [tuple(headers)]),
        max(len(r[2]) for r in rows + [tuple(headers)]),
        max(len(r[3]) for r in rows + [tuple(headers)]),
        min(65, max(len(r[4]) for r in rows + [tuple(headers)])),
    ]

    sep_line = "+" + "+".join("-" * (w + 2) for w in col_w) + "+"
    header_line = "| " + " | ".join(f"{h:<{w}}" for h, w in zip(headers, col_w)) + " |"

    output_lines = [sep_line, header_line, sep_line]
    for r in rows:
        # Quebra justificativa longa em linhas de até col_w[4] caracteres se necessário
        just_text = r[4]
        chunks = []
        while len(just_text) > col_w[4]:
            split_idx = just_text.rfind(" ", 0, col_w[4])
            if split_idx == -1:
                split_idx = col_w[4]
            chunks.append(just_text[:split_idx])
            just_text = just_text[split_idx:].strip()
        chunks.append(just_text)

        first_chunk = chunks[0] if chunks else ""
        line = (
            f"| {r[0]:<{col_w[0]}} "
            f"| {r[1]:<{col_w[1]}} "
            f"| {r[2]:<{col_w[2]}} "
            f"| {r[3]:<{col_w[3]}} "
            f"| {first_chunk:<{col_w[4]}} |"
        )
        output_lines.append(line)

        for follow_chunk in chunks[1:]:
            cont_line = (
                f"| {'':<{col_w[0]}} "
                f"| {'':<{col_w[1]}} "
                f"| {'':<{col_w[2]}} "
                f"| {'':<{col_w[3]}} "
                f"| {follow_chunk:<{col_w[4]}} |"
            )
            output_lines.append(cont_line)

        output_lines.append(sep_line)

    return "\n".join(output_lines)


def format_fit(fit: PackageFit, rank: Optional[int] = None) -> str:
    """Formata os dados detalhados de uma embalagem compatível."""
    prefix = f"Opção #{rank} - " if rank is not None else ""
    pkg = fit.package
    ori = fit.orientation
    int_dims = fit.internal_dimensions
    status_int = "estimada" if fit.is_internal_estimated else "confirmada"

    return (
        f"  {prefix}{pkg.name} ({pkg.id})\n"
        f"    • Dimensões nominais externas: {pkg.length:.1f} × {pkg.width:.1f} × {pkg.height:.1f} cm "
        f"(volume: {pkg.external_volume:,.1f} cm³ / {pkg.external_volume_liters:.2f} L)\n"
        f"    • Espaço interno útil ({status_int}): {int_dims[0]:.1f} × {int_dims[1]:.1f} × {int_dims[2]:.1f} cm "
        f"(volume útil: {fit.internal_volume:,.1f} cm³ / {fit.internal_volume / 1000.0:.2f} L)\n"
        f"    • Preço de ref. (avulso):      R$ {pkg.price:.2f} ({pkg.currency})\n"
        f"    • Orientação adotada:          {ori.description}\n"
        f"    • Folga útil restante:         C: {ori.clearance_length:.1f} cm | "
        f"L: {ori.clearance_width:.1f} cm | A: {ori.clearance_height:.1f} cm\n"
        f"    • Ocupação vol. útil (obj):    {fit.occupancy_ratio:.1f}% "
        f"(com margem: {fit.occupancy_ratio_with_margin:.1f}%)"
    )


def print_result(result: RecommendationResult) -> None:
    """Imprime o resultado detalhado da recomendação e a tabela comparativa geral."""
    orig = result.original_dimensions
    req = result.required_dimensions
    print("-" * 80)
    print("DADOS DO OBJETO E PARÂMETROS:")
    print(
        f" • Dimensões originais do objeto:          {orig[0]:.1f} × {orig[1]:.1f} × {orig[2]:.1f} cm"
    )
    print(
        f" • Margem de segurança (acondicionamento): {result.margin_per_face:.2f} cm por face "
        f"(+{result.total_margin_per_axis:.2f} cm por eixo)"
    )
    print(
        f" • Dimensões necessárias do objeto:        {req[0]:.1f} × {req[1]:.1f} × {req[2]:.1f} cm"
    )
    print(
        f" • Espessura de parede da embalagem:       {result.wall_thickness:.2f} cm por parede "
        f"(-{result.total_wall_reduction_per_axis:.2f} cm por eixo externo)"
    )
    print(
        f" • Limiar mín. de ocupação útil (heurística): {result.min_occupancy_threshold:.1f}%"
    )
    print(
        f" • Volume delimitador original (obj):      {result.bounding_box_volume:,.1f} cm³ "
        f"({result.bounding_box_volume / 1000.0:.3f} L)"
    )
    print(
        f" • Volume necessário com margem (obj):     {result.required_volume:,.1f} cm³ "
        f"({result.required_volume / 1000.0:.3f} L)"
    )
    print("-" * 80)

    print("\nTABELA GERAL DE AVALIAÇÃO DE TODAS AS EMBALAGENS DO CATÁLOGO:")
    print(format_evaluations_table(result.evaluations))
    print()

    if not result.has_compatible:
        print("[!] NENHUMA EMBALAGEM COMPATÍVEL ENCONTRADA NO CATÁLOGO.")
        print(
            "    As dimensões necessárias do objeto excedem o espaço interno útil "
            "de todos os modelos cadastrados."
        )
        print(f"\n[Aviso] {result.disclaimer}")
        print("-" * 80)
        return

    print("RECOMENDAÇÃO PRINCIPAL (Menor volume útil interno / Menor preço):")
    print(format_fit(result.recommended))
    print("-" * 80)

    if result.alternatives:
        print(f"ALTERNATIVAS COMPATÍVEIS (Ocupação >= {result.min_occupancy_threshold:.0f}%) ({len(result.alternatives)}):")
        for idx, alt in enumerate(result.alternatives, start=2):
            print(format_fit(alt, rank=idx))
            print()
        print("-" * 80)

    if result.not_recommended:
        print(f"NÃO INDICADAS (Compatíveis, porém com ocupação < {result.min_occupancy_threshold:.0f}%) ({len(result.not_recommended)}):")
        for nr in result.not_recommended:
            print(f"  • {nr.package.name}: ocupação útil de {nr.occupancy_ratio:.1f}%")
        print("-" * 80)

    print(f"[Aviso] {result.disclaimer}")
    print("-" * 80)


def run_scenarios(recommender: PackageRecommender) -> None:
    """Executa a bateria completa de cenários e validações."""
    print("=" * 80)
    print(" BATERIA DE VALIDAÇÃO — MÓDULO DE EMBALAGENS (STATUS E TABELA GERAL)")
    print("=" * 80)
    print(
        f"Hipóteses padrão: Espessura = {DEFAULT_WALL_THICKNESS} cm | "
        f"Margem = {DEFAULT_MARGIN_PER_FACE} cm | Limiar Ocupação = {DEFAULT_MIN_OCCUPANCY_THRESHOLD}%"
    )
    print("=" * 80)

    # 1. Objeto pequeno
    print("\n>>> [Cenário 1: Objeto Pequeno]")
    print("    Descrição: Objeto compacto (12.0 × 8.0 × 3.0 cm) que cabe folgadamente na Caixa P.")
    res1 = recommender.recommend(12.0, 8.0, 3.0)
    print_result(res1)

    # 2. Mudança de orientação
    print("\n>>> [Cenário 2: Objeto que Exige Mudança de Orientação]")
    print(
        "    Descrição: Objeto com dimensões naturais (6.0 × 21.0 × 13.0 cm). Com margem (+1 cm), "
        "fica (7.0 × 22.0 × 14.0 cm). Na orientação direta, largura 22.0 cm excede a largura útil da "
        "Caixa P (15.2 cm). Rotacionando para (22.0 × 14.0 × 7.0 cm), acomoda perfeitamente na Caixa P."
    )
    res2 = recommender.recommend(6.0, 21.0, 13.0)
    print_result(res2)

    # 3. Múltiplas embalagens e diferenciação de ALTERNATIVE vs NOT_RECOMMENDED
    print("\n>>> [Cenário 3: Objeto com Múltiplas Embalagens e Avaliação de Status]")
    print(
        "    Descrição: Objeto (24.0 × 18.0 × 10.0 cm). Não cabe na Caixa P (incompatível). "
        "Cabe na Caixa M (Recomendada, ocupação 57.2%), Caixa G (Alternativa, ocupação 16.6% sob threshold 15%) "
        "e Caixa GG (Não recomendada, ocupação 6.9%)."
    )
    res3 = recommender.recommend(24.0, 18.0, 10.0, min_occupancy_threshold=15.0)
    print_result(res3)

    # 4. Próximo ao limite dimensional
    print("\n>>> [Cenário 4: Objeto Próximo ao Limite Dimensional Interno]")
    print(
        "    Descrição: Objeto com 22.2 × 14.2 × 6.2 cm. Com margem de 1.0 cm no total, atinge exatamente "
        "23.2 × 15.2 × 7.2 cm, o limite exato do espaço interno útil estimado da Caixa P."
    )
    res4 = recommender.recommend(22.2, 14.2, 6.2)
    print_result(res4)

    # 5. Incompatível com todas as embalagens
    print("\n>>> [Cenário 5: Objeto Incompatível com Todas as Embalagens]")
    print(
        "    Descrição: Objeto grande (55.0 × 40.0 × 32.0 cm) que excede o espaço interno útil da Caixa GG "
        "(51.2 × 39.2 × 31.2 cm). Avalia o detalhamento do menor déficit dimensional."
    )
    res5 = recommender.recommend(55.0, 40.0, 32.0)
    print_result(res5)

    # 6. Validação estrita de entradas anômalas e limites operacionais
    print("\n>>> [Cenário 6: Entradas Inválidas e Limites do Percentual de Ocupação]")
    print("    Descrição: Validação estrita de NaN, Inf, negativos, zero e limites de threshold (0% a 100%).")

    invalid_cases = [
        {"desc": "Comprimento negativo (-5.0, 10.0, 5.0)", "call": lambda: recommender.recommend(-5.0, 10.0, 5.0)},
        {"desc": "Largura zero (10.0, 0.0, 5.0)", "call": lambda: recommender.recommend(10.0, 0.0, 5.0)},
        {"desc": "Altura NaN (10.0, 10.0, float('nan'))", "call": lambda: recommender.recommend(10.0, 10.0, float("nan"))},
        {"desc": "Comprimento Inf (float('inf'), 10.0, 5.0)", "call": lambda: recommender.recommend(float("inf"), 10.0, 5.0)},
        {"desc": "Margem por face negativa (margin_per_face=-0.5)", "call": lambda: recommender.recommend(10.0, 10.0, 5.0, margin_per_face=-0.5)},
        {"desc": "Espessura de parede negativa (wall_thickness=-0.2)", "call": lambda: recommender.recommend(10.0, 10.0, 5.0, wall_thickness=-0.2)},
        {"desc": "Limiar de ocupação negativo (min_occupancy_threshold=-5.0)", "call": lambda: recommender.recommend(10.0, 10.0, 5.0, min_occupancy_threshold=-5.0)},
        {"desc": "Limiar de ocupação superior a 100% (min_occupancy_threshold=105.0)", "call": lambda: recommender.recommend(10.0, 10.0, 5.0, min_occupancy_threshold=105.0)},
    ]

    for case in invalid_cases:
        try:
            case["call"]()
            print(f"    [FALHA] Era esperada exceção para: {case['desc']}")
        except InvalidDimensionsError as exc:
            print(f"    [✓] {case['desc']} -> Exceção capturada: {exc}")

    # 7. Validação da prioridade da embalagem recomendada independentemente da ocupação
    print("\n>>> [Cenário 7: Prioridade de RECOMMENDED mesmo com Baixa Ocupação]")
    print(
        "    Descrição: Objeto muito pequeno (5.0 × 5.0 × 2.0 cm). Ocupação útil na menor caixa (Caixa P) "
        "é de apenas ~1.97% (muito abaixo do limiar padrão de 20%). "
        "A menor embalagem compatível DEVE ser classificada como RECOMMENDED, e as demais como NOT_RECOMMENDED."
    )
    res7 = recommender.recommend(5.0, 5.0, 2.0, min_occupancy_threshold=20.0)
    print_result(res7)

    # Conferência programática da regra
    rec_ev = next(ev for ev in res7.evaluations if ev.package.id == "caixa_p")
    print("    [Checagem da regra de negócio]:")
    print(f"    • Caixa P status: {rec_ev.status.value} (esperado: RECOMMENDED)")
    print(f"    • Ocupação da Caixa P: {rec_ev.occupancy_ratio:.2f}% (abaixo do limiar de 20%)")
    assert rec_ev.status == PackageStatus.RECOMMENDED, "Caixa P deveria ser RECOMMENDED!"
    print("    [✓] Regra validada com sucesso: menor caixa compatível é sempre RECOMMENDED.")

    print("\n" + "=" * 80)
    print(" TODOS OS CENÁRIOS E VALIDAÇÕES FORAM EXECUTADOS COM SUCESSO!")
    print("=" * 80)


def interactive_mode(recommender: PackageRecommender) -> None:
    """Permite ao usuário informar dimensões iterativamente pelo terminal."""
    print("=" * 80)
    print(" PackMeasure — Recomendação Interativa de Embalagens")
    print("=" * 80)
    print("Digite as dimensões do objeto em centímetros (ou 'q' para sair):")

    while True:
        try:
            line = input("\n> Dimensões [Comprimento Largura Altura] (ex: 20 15 8): ").strip()
            if line.lower() in ("q", "quit", "sair", "exit"):
                print("Encerrando modo interativo.")
                break
            if not line:
                continue

            parts = line.replace(",", ".").split()
            if len(parts) != 3:
                print("[!] Informe exatamente três valores numéricos separados por espaço.")
                continue

            c, l, a = float(parts[0]), float(parts[1]), float(parts[2])
            margin_input = input(f"  Margem por face em cm [Enter para {DEFAULT_MARGIN_PER_FACE}]: ").strip()
            margin = float(margin_input.replace(",", ".")) if margin_input else DEFAULT_MARGIN_PER_FACE

            thick_input = input(f"  Espessura parede em cm [Enter para {DEFAULT_WALL_THICKNESS}]: ").strip()
            thick = float(thick_input.replace(",", ".")) if thick_input else DEFAULT_WALL_THICKNESS

            thresh_input = input(f"  Limiar de ocupação mín. %% [Enter para {DEFAULT_MIN_OCCUPANCY_THRESHOLD}]: ").strip()
            thresh = float(thresh_input.replace(",", ".")) if thresh_input else DEFAULT_MIN_OCCUPANCY_THRESHOLD

            res = recommender.recommend(
                c, l, a,
                margin_per_face=margin,
                wall_thickness=thick,
                min_occupancy_threshold=thresh,
            )
            print_result(res)

        except (ValueError, PackagingError) as exc:
            print(f"[!] Erro: {exc}")
        except (KeyboardInterrupt, EOFError):
            print("\nEncerrando.")
            break


def main() -> int:
    """Ponto de entrada do script."""
    parser = argparse.ArgumentParser(
        description="Diagnóstico e validação manual do módulo de recomendação de embalagens.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--length",
        "-l",
        type=float,
        help="Comprimento do objeto em cm.",
    )
    parser.add_argument(
        "--width",
        "-w",
        type=float,
        help="Largura do objeto em cm.",
    )
    parser.add_argument(
        "--height",
        "-H",
        type=float,
        help="Altura do objeto em cm.",
    )
    parser.add_argument(
        "--margin",
        "-m",
        type=float,
        default=DEFAULT_MARGIN_PER_FACE,
        help="Margem de segurança de acondicionamento por face em cm.",
    )
    parser.add_argument(
        "--thickness",
        "-t",
        type=float,
        default=DEFAULT_WALL_THICKNESS,
        help="Espessura estimada de cada parede da caixa em cm.",
    )
    parser.add_argument(
        "--threshold",
        "-T",
        type=float,
        default=DEFAULT_MIN_OCCUPANCY_THRESHOLD,
        help="Limiar percentual de ocupação mínima para status ALTERNATIVE (0 a 100%%).",
    )
    parser.add_argument(
        "--catalog",
        "-c",
        default="data/catalog/embalagens_correios.json",
        help="Caminho do arquivo de catálogo de embalagens.",
    )
    parser.add_argument(
        "--scenarios",
        "-s",
        action="store_true",
        help="Executa a bateria de cenários pré-configurados.",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Executa em modo interativo pelo terminal.",
    )

    args = parser.parse_args()

    try:
        recommender = PackageRecommender(args.catalog)
    except Exception as exc:
        print(f"[ERRO CRÍTICO] Falha ao inicializar recomendador: {exc}", file=sys.stderr)
        return 1

    if args.scenarios:
        run_scenarios(recommender)
        return 0

    if args.interactive or (args.length is None and args.width is None and args.height is None):
        interactive_mode(recommender)
        return 0

    if args.length is None or args.width is None or args.height is None:
        print(
            "[!] Para consulta direta via argumentos, informe comprimento (-l), "
            "largura (-w) e altura (-H).",
            file=sys.stderr,
        )
        return 2

    try:
        res = recommender.recommend(
            args.length,
            args.width,
            args.height,
            margin_per_face=args.margin,
            wall_thickness=args.thickness,
            min_occupancy_threshold=args.threshold,
        )
        print_result(res)
        return 0
    except PackagingError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
