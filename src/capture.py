"""Módulo de aquisição de imagens estéreo do projeto PackMeasure.

Fornece classes e utilitários para captura sincronizada de pares de imagens
utilizando OpenCV, suportando dispositivos locais V4L2 (físicos e virtuais)
e transmissões de rede (HTTP/RTSP).
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Union

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Tipos de entrada suportados para fontes de câmera
CameraSource = Union[int, str, Path]


# ============================================================================
# Exceções Customizadas
# ============================================================================


class PackMeasureError(Exception):
    """Exceção base do projeto PackMeasure."""

    pass


class CameraError(PackMeasureError):
    """Exceção base para falhas relacionadas a câmeras."""

    pass


class CameraOpenError(CameraError):
    """Falha ao inicializar ou conectar ao dispositivo de captura."""

    pass


class StereoCaptureError(CameraError):
    """Falha durante a aquisição ou sincronização do par de frames."""

    pass


class FrameValidationError(CameraError):
    """Incompatibilidade ou invalidade nos frames capturados."""

    pass


# ============================================================================
# Modelos de Dados
# ============================================================================


@dataclass
class CameraConfig:
    """Configuração individual de um dispositivo de câmera.

    Attributes:
        source: Identificador do dispositivo (índice int, caminho /dev/video* ou URL HTTP).
        width: Largura desejada em pixels.
        height: Altura desejada em pixels.
        fps: Taxa de quadros por segundo desejada.
        fourcc: Codec FourCC opcional (ex: 'MJPG', 'YUYV'). Se None, não altera o codec padrão do driver.
        buffer_size: Tamanho do buffer interno do driver (padrão 1 para minimizar latência).
    """

    source: CameraSource
    width: int = 1280
    height: int = 720
    fps: int = 30
    fourcc: Optional[str] = None
    buffer_size: int = 1


@dataclass
class StereoPair:
    """Representação de um par de imagens estéreo capturadas.

    Attributes:
        left: Imagem BGR da câmera esquerda (np.ndarray uint8).
        right: Imagem BGR da câmera direita (np.ndarray uint8).
        timestamp: Marcação temporal POSIX da captura.
    """

    left: np.ndarray
    right: np.ndarray
    timestamp: float = field(default_factory=time.time)

    @property
    def left_resolution(self) -> Tuple[int, int]:
        """Retorna (largura, altura) da imagem esquerda."""
        return self.left.shape[1], self.left.shape[0]

    @property
    def right_resolution(self) -> Tuple[int, int]:
        """Retorna (largura, altura) da imagem direita."""
        return self.right.shape[1], self.right.shape[0]

    @property
    def is_compatible(self) -> bool:
        """Verifica se ambas as imagens possuem dimensões idênticas."""
        return self.left.shape == self.right.shape


# ============================================================================
# Gerenciamento de Câmera Individual
# ============================================================================


class CameraDevice:
    """Gerencia o ciclo de vida e a aquisição de um único dispositivo de captura."""

    def __init__(self, config: CameraConfig, name: str = "camera"):
        self.config = config
        self.name = name
        self._cap: Optional[cv2.VideoCapture] = None
        self._effective_resolution: Optional[Tuple[int, int]] = None
        self._effective_fps: Optional[float] = None
        self._effective_fourcc: Optional[str] = None

    @property
    def is_opened(self) -> bool:
        """Indica se a captura está aberta e pronta."""
        return self._cap is not None and self._cap.isOpened()

    @property
    def effective_resolution(self) -> Optional[Tuple[int, int]]:
        """Resolução (largura, altura) efetivamente configurada no dispositivo."""
        return self._effective_resolution

    @property
    def effective_fps(self) -> Optional[float]:
        """FPS efetivamente configurado no dispositivo."""
        return self._effective_fps

    @property
    def effective_fourcc(self) -> Optional[str]:
        """FourCC retornado pelo driver."""
        return self._effective_fourcc

    def open(self) -> None:
        """Abre o dispositivo de vídeo e aplica as configurações solicitadas."""
        if self.is_opened:
            logger.debug("Câmera %s já se encontra aberta.", self.name)
            return

        normalized_source, api_preference = self._normalize_source(self.config.source)
        logger.info(
            "Abrindo %s (fonte=%r, api=%s)...",
            self.name,
            normalized_source,
            api_preference,
        )

        cap = cv2.VideoCapture(normalized_source, api_preference)

        if not cap.isOpened():
            # Fallback para backend automático caso a API preferencial falhe
            if api_preference != cv2.CAP_ANY:
                logger.warning(
                    "Falha ao abrir %s com backend preferencial %s. Tentando backend padrão (CAP_ANY)...",
                    self.name,
                    api_preference,
                )
                cap = cv2.VideoCapture(normalized_source, cv2.CAP_ANY)

        if not cap.isOpened():
            raise CameraOpenError(
                f"Não foi possível abrir a câmera '{self.name}' na fonte: {self.config.source!r}."
            )

        self._cap = cap

        # 1. Configurar FourCC (se especificado)
        if self.config.fourcc:
            fourcc_val = cv2.VideoWriter_fourcc(*self.config.fourcc)
            success = self._cap.set(cv2.CAP_PROP_FOURCC, fourcc_val)
            if not success:
                logger.warning(
                    "[%s] Driver recusou a configuração FourCC=%r.",
                    self.name,
                    self.config.fourcc,
                )
            else:
                logger.debug("[%s] FourCC configurado para %r.", self.name, self.config.fourcc)

        # 2. Configurar Resolução e FPS
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.config.width))
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.config.height))
        self._cap.set(cv2.CAP_PROP_FPS, float(self.config.fps))

        # 3. Configurar Buffer (para reduzir acúmulo de frames no V4L2)
        try:
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, self.config.buffer_size)
        except Exception as exc:
            logger.debug("[%s] Não foi possível definir CAP_PROP_BUFFERSIZE: %s", self.name, exc)

        # 4. Validar resolução e propriedades efetivas
        eff_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        eff_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._effective_fps = float(self._cap.get(cv2.CAP_PROP_FPS))
        self._effective_resolution = (eff_w, eff_h)

        fourcc_int = int(self._cap.get(cv2.CAP_PROP_FOURCC))
        self._effective_fourcc = (
            "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)])
            if fourcc_int != 0
            else "UNKNOWN"
        )

        logger.info(
            "[%s] Aberta com sucesso. Resolução: %dx%d (solicitada: %dx%d), FPS: %.1f, FourCC: %s",
            self.name,
            eff_w,
            eff_h,
            self.config.width,
            self.config.height,
            self._effective_fps,
            self._effective_fourcc,
        )

        if (eff_w, eff_h) != (self.config.width, self.config.height):
            logger.warning(
                "[%s] A resolução efetiva (%dx%d) diverge da solicitada (%dx%d).",
                self.name,
                eff_w,
                eff_h,
                self.config.width,
                self.config.height,
            )

    def grab(self) -> bool:
        """Instrui o hardware/driver a capturar o próximo frame sem decodificação imediata.

        Returns:
            True se o frame foi requisitado com sucesso, False em caso de falha.
        """
        if not self.is_opened:
            return False
        return bool(self._cap.grab())

    def retrieve(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Decodifica e retorna o frame capturado pelo comando `grab()` anterior.

        Returns:
            Tupla (sucesso, imagem_bgr).
        """
        if not self.is_opened:
            return False, None
        ret, frame = self._cap.retrieve()
        return bool(ret), frame

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Combina grab() e retrieve() em uma única chamada.

        Returns:
            Tupla (sucesso, imagem_bgr).
        """
        if not self.is_opened:
            return False, None
        ret, frame = self._cap.read()
        return bool(ret), frame

    def release(self) -> None:
        """Libera o recurso de captura e encerra a conexão com o dispositivo."""
        if self._cap is not None:
            logger.info("Liberando recurso de vídeo: %s", self.name)
            try:
                self._cap.release()
            except Exception as exc:
                logger.warning("Exceção ao liberar %s: %s", self.name, exc)
            finally:
                self._cap = None
                self._effective_resolution = None
                self._effective_fps = None

    @staticmethod
    def _normalize_source(source: CameraSource) -> Tuple[Union[int, str], int]:
        """Normaliza a fonte de câmera para uso no OpenCV e escolhe o backend adequado.

        Returns:
            Tupla contendo (fonte_normalizada, backend_opencv).
        """
        if isinstance(source, Path):
            source_str = str(source)
        else:
            source_str = str(source).strip()

        # String puramente numérica (ex: "0", "2") -> converte para inteiro
        if source_str.isdigit():
            return int(source_str), cv2.CAP_V4L2 if os.name == "posix" else cv2.CAP_ANY

        # Se já é int
        if isinstance(source, int):
            return source, cv2.CAP_V4L2 if os.name == "posix" else cv2.CAP_ANY

        # Fluxos de rede (HTTP, HTTPS, RTSP)
        if re.match(r"^(http|https|rtsp)://", source_str, re.IGNORECASE):
            return source_str, cv2.CAP_ANY

        # Caminho de dispositivo V4L2 no Linux (ex: "/dev/video0")
        if source_str.startswith("/dev/video"):
            # Extrai índice se possível para compatibilidade com V4L2
            digits = source_str.replace("/dev/video", "")
            if digits.isdigit():
                return int(digits), cv2.CAP_V4L2
            return source_str, cv2.CAP_V4L2

        return source_str, cv2.CAP_ANY

    def __enter__(self) -> CameraDevice:
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    def __del__(self) -> None:
        self.release()


# ============================================================================
# Sistema de Captura Estéreo
# ============================================================================


class StereoCameraCapture:
    """Gerencia a captura sincronizada do par de câmeras estéreo.

    Coordena a inicialização independente das câmeras esquerda e direita,
    a requisição de quadros em rápida sucessão para minimizar a defasagem temporal,
    a validação de compatibilidade dimensional e o salvamento em disco.
    """

    def __init__(
        self,
        left_source: CameraSource = 0,
        right_source: CameraSource = 2,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        left_fourcc: Optional[str] = "MJPG",
        right_fourcc: Optional[str] = None,
        buffer_size: int = 1,
        left_config: Optional[CameraConfig] = None,
        right_config: Optional[CameraConfig] = None,
    ):
        """Inicializa o gerenciador de captura estéreo.

        Args:
            left_source: Fonte da câmera esquerda (índice, caminho ou URL).
            right_source: Fonte da câmera direita (índice, caminho ou URL).
            width: Largura padrão em pixels.
            height: Altura padrão em pixels.
            fps: FPS padrão.
            left_fourcc: FourCC para câmera esquerda (padrão 'MJPG' para webcam física USB).
            right_fourcc: FourCC para câmera direita (padrão None, para v4l2loopback/Iriun ou automático).
            buffer_size: Tamanho do buffer (padrão 1).
            left_config: Instância de CameraConfig para câmera esquerda (se informada, sobrescreve argumentos).
            right_config: Instância de CameraConfig para câmera direita (se informada, sobrescreve argumentos).
        """
        if left_config is None:
            left_config = CameraConfig(
                source=left_source,
                width=width,
                height=height,
                fps=fps,
                fourcc=left_fourcc,
                buffer_size=buffer_size,
            )

        if right_config is None:
            right_config = CameraConfig(
                source=right_source,
                width=width,
                height=height,
                fps=fps,
                fourcc=right_fourcc,
                buffer_size=buffer_size,
            )

        self.left_config = left_config
        self.right_config = right_config

        self.left_camera = CameraDevice(self.left_config, name="Câmera Esquerda")
        self.right_camera = CameraDevice(self.right_config, name="Câmera Direita")

    @property
    def is_opened(self) -> bool:
        """Verifica se ambas as câmeras estão abertas e operacionais."""
        return self.left_camera.is_opened and self.right_camera.is_opened

    def open(self) -> None:
        """Abre ambas as câmeras e valida a compatibilidade de resolução."""
        try:
            self.left_camera.open()
            self.right_camera.open()
        except Exception:
            self.release()
            raise

        # Validação inicial de resoluções efetivas
        eff_left = self.left_camera.effective_resolution
        eff_right = self.right_camera.effective_resolution

        if eff_left and eff_right and eff_left != eff_right:
            logger.warning(
                "Resoluções efetivas diferem entre as câmeras: Esquerda=%s, Direita=%s. "
                "Visão estéreo requer preferencialmente dimensões idênticas.",
                eff_left,
                eff_right,
            )

    def grab_synced(self) -> Tuple[bool, bool]:
        """Dispara a captura de quadros no menor intervalo temporal possível.

        Ao invocar `grab()` consecutivamente nas duas câmeras antes de decodificar
        os dados (`retrieve()`), reduzimos o atraso temporal entre as imagens
        para poucos microssegundos a milissegundos.

        Returns:
            Tupla (sucesso_grab_esquerda, sucesso_grab_direita).
        """
        ret_left = self.left_camera.grab()
        ret_right = self.right_camera.grab()
        return ret_left, ret_right

    def read(self, flush_buffer: bool = False) -> StereoPair:
        """Captura um par sincronizado de imagens BGR.

        Args:
            flush_buffer: Se True, efetua um descarte de frame prévio para garantir
                que nenhum frame retido anteriormente no buffer seja entregue.

        Returns:
            Instância de StereoPair contendo as imagens esquerda e direita.

        Raises:
            StereoCaptureError: Se a leitura falhar em qualquer uma das câmeras.
            FrameValidationError: Se os frames forem inválidos ou incompatíveis.
        """
        if not self.is_opened:
            raise StereoCaptureError("Câmeras estéreo não estão abertas. Execute open() primeiro.")

        if flush_buffer:
            # Descarte rápido de frame residual
            self.left_camera.grab()
            self.right_camera.grab()

        # Disparo sincronizado
        timestamp = time.time()
        grab_left, grab_right = self.grab_synced()

        if not grab_left or not grab_right:
            raise StereoCaptureError(
                f"Falha no sinal de captura (grab): esquerda={grab_left}, direita={grab_right}."
            )

        # Decodificação dos frames BGR
        ret_left, frame_left = self.left_camera.retrieve()
        ret_right, frame_right = self.right_camera.retrieve()

        if not ret_left or frame_left is None:
            raise StereoCaptureError("Falha ao recuperar o frame da câmera esquerda.")

        if not ret_right or frame_right is None:
            raise StereoCaptureError("Falha ao recuperar o frame da câmera direita.")

        # Validação estrutural do par
        self.validate_pair(frame_left, frame_right)

        return StereoPair(left=frame_left, right=frame_right, timestamp=timestamp)

    @staticmethod
    def validate_pair(left_frame: np.ndarray, right_frame: np.ndarray) -> None:
        """Valida integridade e compatibilidade geométrica entre os frames do par.

        Args:
            left_frame: Matriz da imagem esquerda.
            right_frame: Matriz da imagem direita.

        Raises:
            FrameValidationError: Se qualquer validação falhar.
        """
        if left_frame is None or right_frame is None:
            raise FrameValidationError("Frame nulo recebido durante a validação estéreo.")

        if left_frame.size == 0 or right_frame.size == 0:
            raise FrameValidationError("Frame com buffer vazio (size=0) detectado.")

        if len(left_frame.shape) != 3 or left_frame.shape[2] != 3:
            raise FrameValidationError(
                f"Frame esquerdo não possui 3 canais BGR válidos: shape={left_frame.shape}"
            )

        if len(right_frame.shape) != 3 or right_frame.shape[2] != 3:
            raise FrameValidationError(
                f"Frame direito não possui 3 canais BGR válidos: shape={right_frame.shape}"
            )

        h_left, w_left = left_frame.shape[:2]
        h_right, w_right = right_frame.shape[:2]

        if (h_left, w_left) != (h_right, w_right):
            raise FrameValidationError(
                f"Dimensões incompatíveis entre os frames do par estéreo: "
                f"Esquerda=({w_left}x{h_left}), Direita=({w_right}x{h_right}). "
                "Para reconstrução estéreo, as imagens devem possuir dimensões compatíveis."
            )

    def save_pair(
        self,
        pair: Optional[StereoPair] = None,
        directory: Union[str, Path] = "data/captures",
        prefix: str = "capture",
    ) -> Tuple[Path, Path]:
        """Salva o par de imagens estéreo no disco em data/captures/.

        Args:
            pair: Instância de StereoPair a ser salva. Se None, realiza uma nova captura.
            directory: Diretório de destino (padrão 'data/captures').
            prefix: Prefixo para o nome dos arquivos salvos.

        Returns:
            Tupla (caminho_esquerdo, caminho_direito) com os Paths absolutos dos arquivos salvos.

        Raises:
            StereoCaptureError: Se a captura ou escrita em disco falhar.
        """
        if pair is None:
            pair = self.read(flush_buffer=True)

        target_dir = Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.fromtimestamp(pair.timestamp).strftime("%Y%m%d_%H%M%S_%f")[:-3]

        left_filename = f"{prefix}_{timestamp_str}_left.png"
        right_filename = f"{prefix}_{timestamp_str}_right.png"

        left_path = target_dir / left_filename
        right_path = target_dir / right_filename

        # Gravação em disco no formato BGR nativo
        ok_left = cv2.imwrite(str(left_path), pair.left)
        ok_right = cv2.imwrite(str(right_path), pair.right)

        if not ok_left or not ok_right:
            raise StereoCaptureError(
                f"Falha ao gravar imagens em disco: esquerda={ok_left} ({left_path}), "
                f"direita={ok_right} ({right_path})."
            )

        logger.info("Par estéreo salvo com sucesso: %s e %s", left_path.name, right_path.name)
        return left_path, right_path

    def release(self) -> None:
        """Libera com segurança os recursos de ambas as câmeras."""
        logger.info("Liberando sistema de captura estéreo...")
        try:
            self.left_camera.release()
        except Exception as exc:
            logger.warning("Erro ao liberar câmera esquerda: %s", exc)

        try:
            self.right_camera.release()
        except Exception as exc:
            logger.warning("Erro ao liberar câmera direita: %s", exc)

    def close(self) -> None:
        """Alias para release()."""
        self.release()

    def __enter__(self) -> StereoCameraCapture:
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    def __del__(self) -> None:
        self.release()
