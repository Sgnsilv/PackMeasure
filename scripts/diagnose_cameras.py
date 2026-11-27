#!/usr/bin/env python3
"""Script de diagnóstico e validação do sistema de captura estéreo (PackMeasure).

Permite inspecionar em tempo real os feeds das duas câmeras lado a lado,
verificar as resoluções efetivas, avaliar alinhamento óptico com linhas guia,
e realizar a captura de pares sincronizados salvando-os em data/captures/.

Uso:
    python scripts/diagnose_cameras.py --left 0 --right 2
    python scripts/diagnose_cameras.py --help
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

# Adiciona o diretório raiz ao path para importar src
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.capture import (
    CameraConfig,
    CameraOpenError,
    FrameValidationError,
    StereoCameraCapture,
    StereoCaptureError,
)

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("diagnose_cameras")


def parse_arguments() -> argparse.Namespace:
    """Configura e analisa os argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="Diagnóstico e validação manual das câmeras estéreo do PackMeasure.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    group_dev = parser.add_argument_group("Dispositivos de Entrada")
    group_dev.add_argument(
        "--left",
        "-l",
        default="0",
        help="Índice numérico (/dev/videoX), caminho ou URL HTTP da câmera esquerda.",
    )
    group_dev.add_argument(
        "--right",
        "-r",
        default="2",
        help="Índice numérico (/dev/videoX), caminho ou URL HTTP da câmera direita.",
    )

    group_cfg = parser.add_argument_group("Configuração de Imagem")
    group_cfg.add_argument(
        "--width",
        "-W",
        type=int,
        default=1280,
        help="Largura desejada da captura em pixels.",
    )
    group_cfg.add_argument(
        "--height",
        "-H",
        type=int,
        default=720,
        help="Altura desejada da captura em pixels.",
    )
    group_cfg.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Taxa de quadros por segundo desejada.",
    )
    group_cfg.add_argument(
        "--fourcc-left",
        default="MJPG",
        help="FourCC da câmera esquerda (ex: 'MJPG'). Deixe vazio para usar padrão do driver.",
    )
    group_cfg.add_argument(
        "--fourcc-right",
        default=None,
        help="FourCC da câmera direita (padrão: None para manter formato nativo ex: YU12 do Iriun).",
    )

    group_ui = parser.add_argument_group("Interface e Saída")
    group_ui.add_argument(
        "--output-dir",
        "-o",
        default="data/captures",
        help="Diretório onde os pares capturados serão salvos.",
    )
    group_ui.add_argument(
        "--scale",
        type=float,
        default=0.75,
        help="Fator de redimensionamento da janela de visualização.",
    )
    group_ui.add_argument(
        "--guides",
        action="store_true",
        help="Inicia com as linhas guia horizontais ativadas para auxílio de alinhamento.",
    )
    group_ui.add_argument(
        "--headless",
        action="store_true",
        help="Executa em modo não-gráfico (captura um par de teste e encerra).",
    )

    return parser.parse_args()


def draw_text_with_shadow(
    img: np.ndarray,
    text: str,
    org: Tuple[int, int],
    font_scale: float = 0.55,
    color: Tuple[int, int, int] = (255, 255, 255),
    thickness: int = 1,
) -> None:
    """Desenha texto com contorno preto para máxima legibilidade sobre o vídeo."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    # Sombra/Borda preta
    cv2.putText(
        img,
        text,
        (org[0] + 1, org[1] + 1),
        font,
        font_scale,
        (0, 0, 0),
        thickness + 2,
        cv2.LINE_AA,
    )
    # Texto frontal
    cv2.putText(
        img,
        text,
        org,
        font,
        font_scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def run_diagnostics(args: argparse.Namespace) -> int:
    """Executa o loop de diagnóstico interativo."""
    fourcc_left = args.fourcc_left.strip() if args.fourcc_left else None
    fourcc_right = args.fourcc_right.strip() if args.fourcc_right else None

    left_config = CameraConfig(
        source=args.left,
        width=args.width,
        height=args.height,
        fps=args.fps,
        fourcc=fourcc_left,
        buffer_size=1,
    )

    right_config = CameraConfig(
        source=args.right,
        width=args.width,
        height=args.height,
        fps=args.fps,
        fourcc=fourcc_right,
        buffer_size=1,
    )

    print("=" * 70)
    print(" PackMeasure — Diagnóstico e Aquisição de Câmeras Estéreo")
    print("=" * 70)
    print(f" • Câmera Esquerda: {args.left} (FourCC={fourcc_left or 'padrão'})")
    print(f" • Câmera Direita:  {args.right} (FourCC={fourcc_right or 'padrão'})")
    print(f" • Resolução pedida: {args.width}x{args.height} @ {args.fps} FPS")
    print(f" • Diretório saída: {args.output_dir}")
    print("=" * 70)

    try:
        stereo = StereoCameraCapture(
            left_config=left_config,
            right_config=right_config,
        )
        stereo.open()
    except CameraOpenError as exc:
        logger.error("Erro crítico ao inicializar câmeras: %s", exc)
        return 1
    except Exception as exc:
        logger.exception("Falha inesperada ao abrir dispositivos: %s", exc)
        return 1

    eff_left_res = stereo.left_camera.effective_resolution
    eff_right_res = stereo.right_camera.effective_resolution
    eff_left_fps = stereo.left_camera.effective_fps
    eff_right_fps = stereo.right_camera.effective_fps
    eff_left_fourcc = stereo.left_camera.effective_fourcc
    eff_right_fourcc = stereo.right_camera.effective_fourcc

    print("\n[+] Câmeras conectadas com sucesso:")
    print(f"    - Esquerda: {eff_left_res[0]}x{eff_left_res[1]} @ {eff_left_fps:.1f} FPS (codec: {eff_left_fourcc})")
    print(f"    - Direita:  {eff_right_res[0]}x{eff_right_res[1]} @ {eff_right_fps:.1f} FPS (codec: {eff_right_fourcc})")

    # Modo headless para testes de linha de comando sem servidor X/Wayland
    if args.headless:
        print("\n[*] Modo headless ativado. Capturando um par de teste...")
        try:
            pair = stereo.read(flush_buffer=True)
            left_p, right_p = stereo.save_pair(pair, directory=args.output_dir, prefix="diag")
            print(f"[✓] Par de teste salvo com sucesso:\n    - {left_p}\n    - {right_p}")
            stereo.release()
            return 0
        except Exception as exc:
            logger.error("Falha na captura headless: %s", exc)
            stereo.release()
            return 1

    window_name = "PackMeasure - Diagnostico Estereo"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    show_guides = args.guides
    saved_count = 0
    feedback_msg = ""
    feedback_until = 0.0

    fps_count = 0
    fps_start_time = time.perf_counter()
    measured_fps = 0.0

    print("\nControles na janela de visualização:")
    print("  [ESPAÇO] ou [C] : Capturar e salvar par estéreo")
    print("  [G]             : Alternar linhas guia horizontais de alinhamento")
    print("  [Q] ou [ESC]    : Sair e liberar recursos\n")

    try:
        while True:
            t0 = time.perf_counter()

            try:
                pair = stereo.read()
            except (StereoCaptureError, FrameValidationError) as exc:
                logger.warning("Falha na leitura do par: %s", exc)
                time.sleep(0.05)
                continue

            frame_l = pair.left.copy()
            frame_r = pair.right.copy()
            h, w = frame_l.shape[:2]

            # Linhas guias horizontais (auxílio na retificação visual)
            if show_guides:
                for y_ratio in [0.25, 0.5, 0.75]:
                    y = int(h * y_ratio)
                    color = (0, 255, 0) if y_ratio == 0.5 else (0, 255, 255)
                    cv2.line(frame_l, (0, y), (w, y), color, 1, cv2.LINE_AA)
                    cv2.line(frame_r, (0, y), (w, y), color, 1, cv2.LINE_AA)

            # Rótulos das câmeras
            draw_text_with_shadow(
                frame_l,
                f"ESQUERDA | {w}x{h} ({eff_left_fourcc})",
                (15, 30),
                color=(0, 255, 255),
            )
            draw_text_with_shadow(
                frame_r,
                f"DIREITA | {w}x{h} ({eff_right_fourcc})",
                (15, 30),
                color=(0, 255, 255),
            )

            # Combina lado a lado
            combined = np.hstack([frame_l, frame_r])

            # Divisória central
            cv2.line(combined, (w, 0), (w, h), (100, 100, 100), 2)

            # Cálculo de taxa de quadros (FPS de visualização)
            fps_count += 1
            elapsed_fps = time.perf_counter() - fps_start_time
            if elapsed_fps >= 1.0:
                measured_fps = fps_count / elapsed_fps
                fps_count = 0
                fps_start_time = time.perf_counter()

            # Barra de status inferior
            total_w = combined.shape[1]
            status_bar_h = 32
            cv2.rectangle(
                combined,
                (0, h - status_bar_h),
                (total_w, h),
                (30, 30, 30),
                -1,
            )

            info_text = (
                f"FPS: {measured_fps:.1f} | Salvos: {saved_count} | "
                "[ESPACO/C] Salvar | [G] Guias | [Q] Sair"
            )
            draw_text_with_shadow(
                combined,
                info_text,
                (15, h - 10),
                font_scale=0.5,
                color=(200, 200, 200),
            )

            # Feedback de gravação recente
            now = time.time()
            if now < feedback_until and feedback_msg:
                # Banner verde no topo
                cv2.rectangle(combined, (0, 0), (total_w, 40), (0, 120, 0), -1)
                draw_text_with_shadow(
                    combined,
                    feedback_msg,
                    (20, 26),
                    font_scale=0.6,
                    color=(255, 255, 255),
                    thickness=2,
                )

            # Redimensionamento de exibição
            if args.scale != 1.0:
                disp_w = int(total_w * args.scale)
                disp_h = int(h * args.scale)
                display_frame = cv2.resize(combined, (disp_w, disp_h), interpolation=cv2.INTER_LINEAR)
            else:
                display_frame = combined

            cv2.imshow(window_name, display_frame)

            # Processamento de teclas (aguarda até 1ms)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), ord("Q"), 27):  # 27 = ESC
                print("[*] Encerrando visualização solicitada pelo usuário.")
                break
            elif key in (ord("c"), ord("C"), 32):  # 32 = Barra de espaço
                try:
                    left_p, right_p = stereo.save_pair(
                        pair=pair,
                        directory=args.output_dir,
                        prefix="capture",
                    )
                    saved_count += 1
                    feedback_msg = f"[SALVO #{saved_count}] {left_p.name} e {right_p.name}"
                    feedback_until = time.time() + 2.5
                    print(f"[✓] Par #{saved_count} salvo:")
                    print(f"    - Esquerda: {left_p}")
                    print(f"    - Direita:  {right_p}")
                except Exception as exc:
                    logger.error("Erro ao salvar par de imagens: %s", exc)
                    feedback_msg = f"ERRO AO SALVAR: {exc}"
                    feedback_until = time.time() + 3.0
            elif key in (ord("g"), ord("G")):
                show_guides = not show_guides
                status_str = "ativadas" if show_guides else "desativadas"
                print(f"[*] Linhas guia {status_str}.")

    except KeyboardInterrupt:
        print("\n[*] Interrupção via teclado detectada (Ctrl+C).")
    finally:
        stereo.release()
        cv2.destroyAllWindows()
        print(f"[+] Diagnóstico concluído. Total de pares salvos: {saved_count}.")

    return 0


if __name__ == "__main__":
    cli_args = parse_arguments()
    sys.exit(run_diagnostics(cli_args))
