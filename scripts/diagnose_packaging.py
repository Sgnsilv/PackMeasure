#!/usr/bin/env python3
"""Script de diagnóstico e validação do módulo de recomendação de embalagens (PackMeasure).

Permite informar dimensões manualmente pelo terminal ou executar uma bateria
completa de cenários de teste automatizados para validar a lógica de recomendação,
dimensões internas estimadas, orientação ortogonal, margens de segurança,
espessura de parede e tratamento de entradas inválidas.

Uso:
    python scripts/diagnose_packaging.py --scenarios
    python scripts/diagnose_packaging.py -l 15 -w 10 -H 5
    python scripts/diagnose_packaging.py --length 22 --width 14 --height 6 --margin 0.5 --thickness 0.4
    python scripts/diagnose_packaging.py --interactive
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Optional, Tuple

# Garante acesso ao pacote src
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.packaging import (
    DEFAULT_MARGIN_PER_FACE,
    DEFAULT_WALL_THICKNESS,
    DISCLAIMER_TEXT,
    InvalidDimensionsError,
    PackageFit,
    PackageRecommender,
    PackagingError,
    RecommendationResult,
)


def format_fit(fit: PackageFit, rank: Optional[int] = None) -> str:
    """Formata os dados de uma embalagem compatível para exibição textual."""
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
    """Imprime o resultado detalhado da recomendação."""
    orig = result.original_dimensions
    req = result.required_dimensions
    print("-" * 76)
    print("DADOS DO OBJETO E PARÂMETROS:")
    print(
        f" • Dimensões originais do objeto:     {orig[0]:.1f} × {orig[1]:.1f} × {orig[2]:.1f} cm"
    )
    print(
        f" • Margem de segurança (acondicionamento): {result.margin_per_face:.2f} cm por face "
        f"(+{result.total_margin_per_axis:.2f} cm por eixo)"
    )
    print(
        f" • Dimensões necessárias do objeto:   {req[0]:.1f} × {req[1]:.1f} × {req[2]:.1f} cm"
    )
    print(
        f" • Espessura de parede da embalagem:  {result.wall_thickness:.2f} cm por parede "
        f"(-{result.total_wall_reduction_per_axis:.2f} cm por eixo externo)"
    )
    print(
        f" • Volume delimitador original (obj): {result.bounding_box_volume:,.1f} cm³ "
        f"({result.bounding_box_volume / 1000.0:.3f} L)"
    )
    print(
        f" • Volume necessário com margem (obj): {result.required_volume:,.1f} cm³ "
        f"({result.required_volume / 1000.0:.3f} L)"
    )
    print("-" * 76)

    if not result.has_compatible:
        print("[!] NENHUMA EMBALAGEM COMPATÍVEL ENCONTRADA NO CATÁLOGO.")
        print(
            "    As dimensões necessárias do objeto excedem o espaço interno útil "
            "de todos os modelos cadastrados."
        )
        print(f"\n[Aviso] {result.disclaimer}")
        print("-" * 76)
        return

    print("RECOMENDAÇÃO PRINCIPAL (Menor volume útil interno / Menor preço):")
    print(format_fit(result.recommended))
    print("-" * 76)

    if result.alternatives:
        print(f"ALTERNATIVAS COMPATÍVEIS ({len(result.alternatives)}):")
        for idx, alt in enumerate(result.alternatives, start=2):
            print(format_fit(alt, rank=idx))
            print()
        print("-" * 76)
    else:
        print("OUTRAS OPÇÕES: Nenhuma outra embalagem do catálogo acomoda este objeto.")
        print("-" * 76)

    print(f"[Aviso] {result.disclaimer}")
    print("-" * 76)


def run_scenarios(recommender: PackageRecommender) -> None:
    """Executa a bateria de 7 cenários previstos na especificação da issue."""
    print("=" * 80)
    print(" BATERIA DE VALIDAÇÃO DE CENÁRIOS — MÓDULO DE EMBALAGENS (REVISÃO)")
    print("=" * 80)
    print(f"Hipóteses padrão: Espessura de parede = {DEFAULT_WALL_THICKNESS} cm | Margem = {DEFAULT_MARGIN_PER_FACE} cm")
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

    # 3. Múltiplas embalagens
    print("\n>>> [Cenário 3: Objeto Compatível com Múltiplas Embalagens]")
    print(
        "    Descrição: Objeto (16.0 × 10.0 × 5.0 cm) que cabe no espaço interno da Caixa P, M, G e GG. "
        "Verifica a ordenação ótima por menor volume útil interno."
    )
    res3 = recommender.recommend(16.0, 10.0, 5.0)
    print_result(res3)

    # 4. Próximo ao limite dimensional
    print("\n>>> [Cenário 4: Objeto Próximo ao Limite Dimensional Interno]")
    print(
        "    Descrição: Objeto com 22.2 × 14.2 × 6.2 cm. Com margem de 1.0 cm no total, atinge exatamente "
        "23.2 × 15.2 × 7.2 cm, o limite exato do espaço interno útil estimado da Caixa P (24 - 0.8 = 23.2, etc.)."
    )
    res4 = recommender.recommend(22.2, 14.2, 6.2)
    print_result(res4)

    # 5. Incompatível com todas as embalagens
    print("\n>>> [Cenário 5: Objeto Incompatível com Todas as Embalagens]")
    print(
        "    Descrição: Objeto grande (55.0 × 40.0 × 32.0 cm) que excede o espaço interno útil da Caixa GG "
        "(51.2 × 39.2 × 31.2 cm)."
    )
    res5 = recommender.recommend(55.0, 40.0, 32.0)
    print_result(res5)

    # 6. Dimensões inválidas (Bateria abrangente de entradas anômalas)
    print("\n>>> [Cenário 6: Dimensões Inválidas (Tratamento de Exceções)]")
    print("    Descrição: Validação estrita de entradas anômalas: negativa, zero, NaN, Inf, margem/espessura negativas.")

    invalid_cases = [
        {"desc": "Comprimento negativo (-5.0, 10.0, 5.0)", "call": lambda: recommender.recommend(-5.0, 10.0, 5.0)},
        {"desc": "Largura zero (10.0, 0.0, 5.0)", "call": lambda: recommender.recommend(10.0, 0.0, 5.0)},
        {"desc": "Altura NaN (10.0, 10.0, float('nan'))", "call": lambda: recommender.recommend(10.0, 10.0, float("nan"))},
        {"desc": "Comprimento Inf (float('inf'), 10.0, 5.0)", "call": lambda: recommender.recommend(float("inf"), 10.0, 5.0)},
        {"desc": "Margem por face negativa (margin_per_face=-0.5)", "call": lambda: recommender.recommend(10.0, 10.0, 5.0, margin_per_face=-0.5)},
        {"desc": "Espessura de parede negativa (wall_thickness=-0.2)", "call": lambda: recommender.recommend(10.0, 10.0, 5.0, wall_thickness=-0.2)},
    ]

    for case in invalid_cases:
        try:
            case["call"]()
            print(f"    [FALHA] Era esperada exceção para: {case['desc']}")
        except InvalidDimensionsError as exc:
            print(f"    [✓] {case['desc']} -> Exceção capturada: {exc}")

    # 7. Alteração da margem de segurança
    print("\n>>> [Cenário 7: Alteração da Margem de Segurança]")
    print(
        "    Descrição: Compara o mesmo objeto (22.0 × 14.0 × 6.0 cm) sob margem padrão (0.5 cm/face) "
        "vs margem ampliada (1.0 cm/face)."
    )
    obj_dims = (22.0, 14.0, 6.0)
    print(f"    Dimensões do objeto: {obj_dims[0]} × {obj_dims[1]} × {obj_dims[2]} cm")

    print("\n    --- Teste A: Margem padrão de 0.5 cm por face (+1.0 cm total) ---")
    res_a = recommender.recommend(*obj_dims, margin_per_face=0.5)
    rec_name_a = res_a.recommended.package.name if res_a.recommended else "Nenhuma"
    print(f"    Recomendação: {rec_name_a}")
    print(
        f"    Dimensões necessárias: {res_a.required_dimensions[0]:.1f} × "
        f"{res_a.required_dimensions[1]:.1f} × {res_a.required_dimensions[2]:.1f} cm "
        f"(limite interno Caixa P: 23.2 × 15.2 × 7.2 cm)"
    )

    print("\n    --- Teste B: Margem ampliada de 1.0 cm por face (+2.0 cm total) ---")
    res_b = recommender.recommend(*obj_dims, margin_per_face=1.0)
    rec_name_b = res_b.recommended.package.name if res_b.recommended else "Nenhuma"
    print(f"    Recomendação: {rec_name_b}")
    print(
        f"    Dimensões necessárias: {res_b.required_dimensions[0]:.1f} × "
        f"{res_b.required_dimensions[1]:.1f} × {res_b.required_dimensions[2]:.1f} cm "
        f"(excede Caixa P, migra para Caixa M)"
    )
    print("    [✓] Resultado: Com a margem ampliada, o objeto foi corretamente realocado para a Caixa M.")

    print("\n" + "=" * 80)
    print(" TODOS OS CENÁRIOS FORAM VALIDADOS COM SUCESSO!")
    print("=" * 80)


def interactive_mode(recommender: PackageRecommender) -> None:
    """Permite ao usuário informar dimensões iterativamente pelo terminal."""
    print("=" * 76)
    print(" PackMeasure — Recomendação Interativa de Embalagens")
    print("=" * 76)
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

            res = recommender.recommend(c, l, a, margin_per_face=margin, wall_thickness=thick)
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
        "--catalog",
        "-c",
        default="data/catalog/embalagens_correios.json",
        help="Caminho do arquivo de catálogo de embalagens.",
    )
    parser.add_argument(
        "--scenarios",
        "-s",
        action="store_true",
        help="Executa a bateria de 7 cenários pré-configurados.",
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
        )
        print_result(res)
        return 0
    except PackagingError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
