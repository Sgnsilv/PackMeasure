"""Módulo de catálogo e recomendação de embalagens dos Correios para o PackMeasure.

Fornece classes e algoritmos para carregar o catálogo de embalagens,
validar dimensões tridimensionais de objetos, estimar o espaço interno útil
com base na espessura de parede da chapa de papelão (hipótese de projeto),
aplicar margem de segurança de acondicionamento, testar compatibilidade espacial
considerando permutações ortogonais e selecionar a melhor embalagem com base
no menor volume interno útil e menor preço de referência.

Também classifica todas as embalagens do catálogo em quatro status funcionais
(RECOMMENDED, ALTERNATIVE, NOT_RECOMMENDED, INCOMPATIBLE) baseando-se em
heurísticas de ocupação volumétrica útil para facilitar a integração com o Streamlit.
"""

from __future__ import annotations

import itertools
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Hipótese padrão de projeto: espessura média estimada da parede de papelão ondulado (4 mm)
DEFAULT_WALL_THICKNESS: float = 0.4  # cm

# Margem padrão de segurança para acondicionamento e proteção por face (5 mm)
DEFAULT_MARGIN_PER_FACE: float = 0.5  # cm

# Heurística de projeto: limiar percentual de ocupação mínima para embalagens alternativas.
# NOTA: Trata-se de uma heurística interna do projeto PackMeasure para evitar caixas excessivamente
# sobredimensionadas, e NÃO de uma regra oficial dos Correios.
DEFAULT_MIN_OCCUPANCY_THRESHOLD: float = 20.0  # %

DISCLAIMER_TEXT: str = (
    "A compatibilidade é estimada com base nas hipóteses dimensionais do projeto e não "
    "garante o acondicionamento físico definitivo, nem realiza estimativa ou otimização de custo de frete. "
    "O limiar de ocupação volumétrica mínima é uma heurística própria do projeto."
)


# ============================================================================
# Enumerações
# ============================================================================


class PackageStatus(str, Enum):
    """Classificação funcional das embalagens do catálogo para a recomendação.

    RECOMMENDED: Menor embalagem compatível com as dimensões necessárias, independentemente
        da sua taxa de ocupação volumétrica.
    ALTERNATIVE: Demais embalagens compatíveis com ocupação volumétrica útil igual ou superior
        ao limiar configurável (heurística de projeto).
    NOT_RECOMMENDED: Demais embalagens compatíveis cuja ocupação volumétrica útil é inferior
        ao limiar configurado, gerando espaço ocioso excessivo.
    INCOMPATIBLE: Embalagem que não acomoda o objeto em nenhuma das seis orientações ortogonais.
    """

    RECOMMENDED = "RECOMMENDED"
    ALTERNATIVE = "ALTERNATIVE"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"
    INCOMPATIBLE = "INCOMPATIBLE"


# ============================================================================
# Exceções Customizadas
# ============================================================================


class PackagingError(Exception):
    """Exceção base para erros do módulo de embalagens."""

    pass


class CatalogError(PackagingError):
    """Falha ao localizar, ler ou validar o catálogo de embalagens."""

    pass


class CatalogNotFoundError(CatalogError):
    """Arquivo de catálogo não encontrado no caminho especificado."""

    pass


class CatalogValidationError(CatalogError):
    """Estrutura do catálogo JSON inválida ou incompleta."""

    pass


class InvalidDimensionsError(PackagingError):
    """Dimensões, margens, espessuras ou limiares inválidos."""

    pass


# ============================================================================
# Modelos de Dados
# ============================================================================


@dataclass(frozen=True)
class Package:
    """Representação de um modelo de embalagem do catálogo.

    Attributes:
        id: Identificador único da embalagem.
        name: Nome descritivo da caixa/modelo.
        length: Comprimento nominal externo cadastrado em centímetros.
        width: Largura nominal externa cadastrada em centímetros.
        height: Altura nominal externa cadastrada em centímetros.
        unit: Unidade de medida (padrão 'cm').
        price: Preço de referência em reais (BRL).
        currency: Código da moeda ('BRL').
        dimension_type: 'externas' ou 'internas'.
        internal_length: Comprimento interno confirmado (se disponível) em cm.
        internal_width: Largura interna confirmada (se disponível) em cm.
        internal_height: Altura interna confirmada (se disponível) em cm.
        source: Fonte das informações (ex: Correios Oficial).
        query_date: Data da consulta das informações.
        description: Descrição ou indicações de uso.
    """

    id: str
    name: str
    length: float
    width: float
    height: float
    unit: str = "cm"
    price: float = 0.0
    currency: str = "BRL"
    dimension_type: str = "externas"
    internal_length: Optional[float] = None
    internal_width: Optional[float] = None
    internal_height: Optional[float] = None
    source: str = ""
    query_date: str = ""
    description: str = ""

    @property
    def external_dimensions(self) -> Tuple[float, float, float]:
        """Retorna as dimensões nominais externas (comprimento, largura, altura) em cm."""
        return (self.length, self.width, self.height)

    @property
    def external_volume(self) -> float:
        """Volume externo nominal da embalagem montada em cm³."""
        return self.length * self.width * self.height

    @property
    def external_volume_liters(self) -> float:
        """Volume externo nominal da embalagem montada em litros."""
        return self.external_volume / 1000.0

    @property
    def has_confirmed_internal_dimensions(self) -> bool:
        """Indica se as dimensões internas foram explicitamente cadastradas e confirmadas."""
        if self.dimension_type.lower() == "internas":
            return True
        return (
            self.internal_length is not None
            and self.internal_width is not None
            and self.internal_height is not None
        )

    def get_internal_dimensions(
        self, wall_thickness: float = DEFAULT_WALL_THICKNESS
    ) -> Tuple[float, float, float]:
        """Obtém as dimensões internas úteis (C, L, A) em cm.

        Se dimensões internas confirmadas foram registradas no catálogo, utiliza-as diretamente.
        Caso contrário, calcula as dimensões internas estimadas subtraindo duas vezes a espessura
        da parede em cada eixo (hipótese de projeto para chapa de papelão ondulado).

        Args:
            wall_thickness: Espessura estimada de cada parede da caixa em cm.

        Returns:
            Tupla contendo (comprimento_interno, largura_interna, altura_interna) em cm.

        Raises:
            CatalogValidationError: Se a espessura de parede for incompatível com as dimensões externas.
        """
        if self.dimension_type.lower() == "internas":
            return (self.length, self.width, self.height)

        if (
            self.internal_length is not None
            and self.internal_width is not None
            and self.internal_height is not None
        ):
            return (self.internal_length, self.internal_width, self.internal_height)

        delta = 2.0 * wall_thickness
        int_l = self.length - delta
        int_w = self.width - delta
        int_h = self.height - delta

        if int_l <= 0 or int_w <= 0 or int_h <= 0:
            raise CatalogValidationError(
                f"A espessura de parede ({wall_thickness} cm) excede a capacidade física "
                f"da embalagem '{self.id}' ({self.length}x{self.width}x{self.height} cm)."
            )

        return (int_l, int_w, int_h)

    def get_internal_volume(self, wall_thickness: float = DEFAULT_WALL_THICKNESS) -> float:
        """Retorna o volume interno útil (estimado ou confirmado) em cm³."""
        int_l, int_w, int_h = self.get_internal_dimensions(wall_thickness)
        return int_l * int_w * int_h

    def get_internal_volume_liters(
        self, wall_thickness: float = DEFAULT_WALL_THICKNESS
    ) -> float:
        """Retorna o volume interno útil em litros."""
        return self.get_internal_volume(wall_thickness) / 1000.0


@dataclass
class OrientationFit:
    """Descreve o alinhamento dimensional do objeto dentro do espaço interno da caixa.

    Attributes:
        aligned_dimensions: Dimensões necessárias (com margem) alinhadas aos eixos
            [comprimento, largura, altura] da embalagem.
        clearance: Folga restante em relação ao espaço interno útil (caixa_interna - obj_necessário) em cm.
        description: Texto explicativo da orientação adotada.
    """

    aligned_dimensions: Tuple[float, float, float]
    clearance: Tuple[float, float, float]
    description: str

    @property
    def clearance_length(self) -> float:
        """Folga interna útil no eixo do comprimento em cm."""
        return self.clearance[0]

    @property
    def clearance_width(self) -> float:
        """Folga interna útil no eixo da largura em cm."""
        return self.clearance[1]

    @property
    def clearance_height(self) -> float:
        """Folga interna útil no eixo da altura em cm."""
        return self.clearance[2]


@dataclass
class PackageFit:
    """Resultado detalhado da acomodação de um objeto em uma embalagem compatível.

    Attributes:
        package: Modelo da embalagem compatível.
        internal_dimensions: Dimensões internas úteis (estimadas ou confirmadas) em cm.
        internal_volume: Volume interno útil em cm³.
        is_internal_estimated: Se as dimensões internas decorrem de estimativa de espessura.
        orientation: Detalhes do alinhamento ortogonal e folgas internas.
        bounding_box_volume: Volume da caixa delimitadora original do objeto em cm³.
        required_volume: Volume do objeto incluindo a margem de segurança em cm³.
        occupancy_ratio: Percentual de ocupação volumétrica da caixa delimitadora
            original em relação ao volume interno útil da embalagem (0 a 100%).
        occupancy_ratio_with_margin: Percentual de ocupação considerando a margem (0 a 100%).
    """

    package: Package
    internal_dimensions: Tuple[float, float, float]
    internal_volume: float
    is_internal_estimated: bool
    orientation: OrientationFit
    bounding_box_volume: float
    required_volume: float
    occupancy_ratio: float
    occupancy_ratio_with_margin: float

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário estruturado para fácil serialização / uso em UI."""
        return {
            "package_id": self.package.id,
            "package_name": self.package.name,
            "external_dimensions": {
                "length": self.package.length,
                "width": self.package.width,
                "height": self.package.height,
                "unit": self.package.unit,
                "volume_cm3": round(self.package.external_volume, 2),
                "volume_liters": round(self.package.external_volume_liters, 2),
            },
            "internal_dimensions": {
                "length": round(self.internal_dimensions[0], 2),
                "width": round(self.internal_dimensions[1], 2),
                "height": round(self.internal_dimensions[2], 2),
                "volume_cm3": round(self.internal_volume, 2),
                "volume_liters": round(self.internal_volume / 1000.0, 2),
                "is_estimated": self.is_internal_estimated,
            },
            "price": self.package.price,
            "currency": self.package.currency,
            "orientation": {
                "aligned_dimensions_cm": [
                    round(d, 2) for d in self.orientation.aligned_dimensions
                ],
                "internal_clearance_cm": [
                    round(c, 2) for c in self.orientation.clearance
                ],
                "description": self.orientation.description,
            },
            "internal_clearance": {
                "length_cm": round(self.orientation.clearance_length, 2),
                "width_cm": round(self.orientation.clearance_width, 2),
                "height_cm": round(self.orientation.clearance_height, 2),
            },
            "occupancy_ratio_internal_percent": round(self.occupancy_ratio, 2),
            "occupancy_ratio_with_margin_percent": round(
                self.occupancy_ratio_with_margin, 2
            ),
        }


@dataclass
class PackageEvaluation:
    """Avaliação completa de uma embalagem do catálogo (compatível ou incompatível).

    Attributes:
        package: Modelo da embalagem avaliada.
        status: Classificação da embalagem (PackageStatus).
        is_compatible: Indica se a embalagem acomoda o objeto em alguma orientação.
        justification: Justificativa dinâmica em português sobre a classificação.
        external_dimensions: Dimensões externas nominais da caixa (C, L, A) em cm.
        internal_dimensions: Dimensões internas úteis (C, L, A) em cm.
        internal_volume: Volume interno útil em cm³.
        is_internal_estimated: Se as medidas internas são estimadas via espessura.
        price: Preço de referência em reais (BRL).
        orientation: Detalhes da orientação quando compatível, ou None.
        clearance: Folgas por eixo (C, L, A) quando compatível, ou None.
        occupancy_ratio: Percentual de ocupação volumétrica do bounding box (0 a 100%), ou None.
        occupancy_ratio_with_margin: Percentual considerando a margem, ou None.
        deficit_details: Informações do déficit dimensional na melhor orientação quando incompatível.
    """

    package: Package
    status: PackageStatus
    is_compatible: bool
    justification: str
    external_dimensions: Tuple[float, float, float]
    internal_dimensions: Tuple[float, float, float]
    internal_volume: float
    is_internal_estimated: bool
    price: float
    orientation: Optional[OrientationFit] = None
    clearance: Optional[Tuple[float, float, float]] = None
    occupancy_ratio: Optional[float] = None
    occupancy_ratio_with_margin: Optional[float] = None
    deficit_details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte a avaliação da embalagem para dicionário estruturado para Streamlit."""
        return {
            "package_id": self.package.id,
            "package_name": self.package.name,
            "status": self.status.value,
            "is_compatible": self.is_compatible,
            "justification": self.justification,
            "price": self.price,
            "currency": self.package.currency,
            "external_dimensions_cm": {
                "length": round(self.external_dimensions[0], 2),
                "width": round(self.external_dimensions[1], 2),
                "height": round(self.external_dimensions[2], 2),
                "volume_liters": round(self.package.external_volume_liters, 2),
            },
            "internal_dimensions_cm": {
                "length": round(self.internal_dimensions[0], 2),
                "width": round(self.internal_dimensions[1], 2),
                "height": round(self.internal_dimensions[2], 2),
                "volume_liters": round(self.internal_volume / 1000.0, 2),
                "is_estimated": self.is_internal_estimated,
            },
            "occupancy_ratio_percent": (
                round(self.occupancy_ratio, 2) if self.occupancy_ratio is not None else None
            ),
            "occupancy_ratio_with_margin_percent": (
                round(self.occupancy_ratio_with_margin, 2)
                if self.occupancy_ratio_with_margin is not None
                else None
            ),
            "orientation": (
                {
                    "aligned_dimensions_cm": [
                        round(d, 2) for d in self.orientation.aligned_dimensions
                    ],
                    "clearance_cm": [round(c, 2) for c in self.orientation.clearance],
                    "description": self.orientation.description,
                }
                if self.orientation
                else None
            ),
            "clearance_cm": (
                {
                    "length": round(self.clearance[0], 2),
                    "width": round(self.clearance[1], 2),
                    "height": round(self.clearance[2], 2),
                }
                if self.clearance
                else None
            ),
            "deficit_details": self.deficit_details,
        }


@dataclass
class RecommendationResult:
    """Resultado consolidado da recomendação de embalagens.

    Attributes:
        original_dimensions: Dimensões originais do objeto (C, L, A) em cm.
        margin_per_face: Margem de segurança aplicada por face em cm.
        total_margin_per_axis: Acréscimo total aplicado ao objeto em cada dimensão (2 * margin_per_face).
        wall_thickness: Espessura estimada de parede adotada por face da caixa em cm.
        total_wall_reduction_per_axis: Redução total por eixo aplicada à caixa externa (2 * wall_thickness).
        min_occupancy_threshold: Limiar percentual configurado para status ALTERNATIVE (heurística de projeto).
        required_dimensions: Dimensões necessárias do objeto após acréscimo da margem.
        bounding_box_volume: Volume da caixa delimitadora original do objeto em cm³.
        required_volume: Volume necessário após acréscimo da margem em cm³.
        recommended: Embalagem recomendada (ótima por menor volume interno e menor preço) ou None.
        alternatives: Lista das embalagens compatíveis com status ALTERNATIVE.
        not_recommended: Lista das embalagens compatíveis com status NOT_RECOMMENDED (baixa ocupação).
        all_compatible: Lista completa de todas as embalagens compatíveis ordenadas.
        evaluations: Lista com a avaliação individual de todas as embalagens do catálogo (incluindo incompatíveis).
        disclaimer: Aviso de que a compatibilidade é estimada e não garante acondicionamento físico.
    """

    original_dimensions: Tuple[float, float, float]
    margin_per_face: float
    total_margin_per_axis: float
    wall_thickness: float
    total_wall_reduction_per_axis: float
    min_occupancy_threshold: float
    required_dimensions: Tuple[float, float, float]
    bounding_box_volume: float
    required_volume: float
    recommended: Optional[PackageFit] = None
    alternatives: List[PackageFit] = field(default_factory=list)
    not_recommended: List[PackageFit] = field(default_factory=list)
    all_compatible: List[PackageFit] = field(default_factory=list)
    evaluations: List[PackageEvaluation] = field(default_factory=list)
    disclaimer: str = DISCLAIMER_TEXT

    @property
    def has_compatible(self) -> bool:
        """Indica se ao menos uma embalagem do catálogo acomoda o objeto."""
        return self.recommended is not None

    def to_dict(self) -> Dict[str, Any]:
        """Converte o resultado consolidado para dicionário estruturado para Streamlit."""
        return {
            "success": self.has_compatible,
            "disclaimer": self.disclaimer,
            "hypotheses": {
                "wall_thickness_per_face_cm": self.wall_thickness,
                "total_wall_reduction_per_axis_cm": self.total_wall_reduction_per_axis,
                "margin_per_face_cm": self.margin_per_face,
                "total_margin_per_axis_cm": self.total_margin_per_axis,
                "min_occupancy_threshold_percent": self.min_occupancy_threshold,
                "occupancy_threshold_note": (
                    "O limiar de ocupação volumétrica mínima é uma heurística do projeto PackMeasure "
                    "e não constitui regra oficial dos Correios."
                ),
            },
            "object": {
                "original_dimensions_cm": {
                    "length": round(self.original_dimensions[0], 2),
                    "width": round(self.original_dimensions[1], 2),
                    "height": round(self.original_dimensions[2], 2),
                },
                "required_dimensions_cm": {
                    "length": round(self.required_dimensions[0], 2),
                    "width": round(self.required_dimensions[1], 2),
                    "height": round(self.required_dimensions[2], 2),
                },
                "bounding_box_volume_cm3": round(self.bounding_box_volume, 2),
                "required_volume_cm3": round(self.required_volume, 2),
            },
            "recommended": self.recommended.to_dict() if self.recommended else None,
            "alternatives": [alt.to_dict() for alt in self.alternatives],
            "not_recommended": [nr.to_dict() for nr in self.not_recommended],
            "total_compatible": len(self.all_compatible),
            "evaluations": [ev.to_dict() for ev in self.evaluations],
        }


# ============================================================================
# Mecanismo de Recomendação
# ============================================================================


class PackageRecommender:
    """Responsável por carregar o catálogo e recomendar embalagens para objetos 3D."""

    DEFAULT_CATALOG_PATH = Path("data/catalog/embalagens_correios.json")

    def __init__(self, catalog_path: Optional[Union[str, Path]] = None):
        """Inicializa o recomendador carregando o catálogo de embalagens.

        Args:
            catalog_path: Caminho do arquivo JSON do catálogo. Se None, utiliza
                o caminho padrão em data/catalog/embalagens_correios.json.

        Raises:
            CatalogError: Se o arquivo não existir ou for inválido.
        """
        self.catalog_path = Path(catalog_path or self.DEFAULT_CATALOG_PATH)
        self.packages: List[Package] = []
        self.metadata: Dict[str, Any] = {}
        self.load_catalog()

    def load_catalog(self) -> None:
        """Carrega e valida o catálogo de embalagens a partir do arquivo JSON."""
        if not self.catalog_path.is_file():
            raise CatalogNotFoundError(
                f"Arquivo de catálogo não encontrado: {self.catalog_path.resolve()}"
            )

        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise CatalogValidationError(
                f"Erro de sintaxe JSON no catálogo ({self.catalog_path}): {exc}"
            ) from exc
        except Exception as exc:
            raise CatalogError(f"Falha ao ler o catálogo ({self.catalog_path}): {exc}") from exc

        if not isinstance(data, dict):
            raise CatalogValidationError(
                f"Raiz do catálogo deve ser um objeto JSON, obtido: {type(data).__name__}"
            )

        raw_packages = data.get("embalagens")
        if not isinstance(raw_packages, list) or len(raw_packages) == 0:
            raise CatalogValidationError(
                "Catálogo não contém uma lista válida e não vazia sob a chave 'embalagens'."
            )

        self.metadata = data.get("metadados", {})
        loaded: List[Package] = []

        required_keys = {"id", "nome", "comprimento", "largura", "altura"}
        for idx, item in enumerate(raw_packages):
            if not isinstance(item, dict):
                raise CatalogValidationError(
                    f"Item #{idx} da lista de embalagens não é um objeto JSON válido."
                )

            missing = required_keys - set(item.keys())
            if missing:
                raise CatalogValidationError(
                    f"Item #{idx} ({item.get('id', 'sem id')}) está sem campos obrigatórios: {missing}"
                )

            try:
                int_l = (
                    float(item["comprimento_interno"])
                    if "comprimento_interno" in item
                    else None
                )
                int_w = (
                    float(item["largura_interna"])
                    if "largura_interna" in item
                    else None
                )
                int_h = (
                    float(item["altura_interna"])
                    if "altura_interna" in item
                    else None
                )

                pkg = Package(
                    id=str(item["id"]).strip(),
                    name=str(item["nome"]).strip(),
                    length=float(item["comprimento"]),
                    width=float(item["largura"]),
                    height=float(item["altura"]),
                    unit=str(item.get("unidade", "cm")).strip(),
                    price=float(item.get("preco", 0.0)),
                    currency=str(item.get("moeda", "BRL")).strip(),
                    dimension_type=str(item.get("tipo_dimensoes", "externas")).strip(),
                    internal_length=int_l,
                    internal_width=int_w,
                    internal_height=int_h,
                    source=str(item.get("fonte", "")).strip(),
                    query_date=str(item.get("data_consulta", "")).strip(),
                    description=str(item.get("descricao", "")).strip(),
                )
            except (ValueError, TypeError) as exc:
                raise CatalogValidationError(
                    f"Erro de conversão numérica no item #{idx} ({item.get('id')}): {exc}"
                ) from exc

            # Validações físicas da caixa externa
            if pkg.length <= 0 or pkg.width <= 0 or pkg.height <= 0:
                raise CatalogValidationError(
                    f"Dimensões da embalagem '{pkg.id}' devem ser estritamente positivas."
                )

            loaded.append(pkg)

        self.packages = loaded
        logger.info(
            "Catálogo carregado com sucesso: %d embalagens disponíveis em %s.",
            len(self.packages),
            self.catalog_path,
        )

    @staticmethod
    def _validate_numeric_param(
        val: Any,
        name: str,
        strictly_positive: bool = True,
        max_val: Optional[float] = None,
    ) -> float:
        """Valida se um parâmetro numérico é válido, finito, não-NaN e dentro da faixa.

        Args:
            val: Valor a ser validado.
            name: Nome do parâmetro para mensagens de erro.
            strictly_positive: Se True, exige valor > 0. Se False, exige valor >= 0.
            max_val: Limite superior opcional.

        Returns:
            Valor float validado.

        Raises:
            InvalidDimensionsError: Se o valor for inválido, não numérico, NaN, inf ou fora da faixa.
        """
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise InvalidDimensionsError(
                f"Parâmetro '{name}' deve ser numérico (recebido: {type(val).__name__} = {val!r})."
            )

        if math.isnan(val):
            raise InvalidDimensionsError(f"Parâmetro '{name}' não pode ser NaN.")

        if not math.isfinite(val):
            raise InvalidDimensionsError(
                f"Parâmetro '{name}' deve ser um valor finito (recebido: {val})."
            )

        if strictly_positive and val <= 0:
            raise InvalidDimensionsError(
                f"Dimensão '{name}' deve ser estritamente positiva (> 0) (recebido: {val})."
            )

        if not strictly_positive and val < 0:
            raise InvalidDimensionsError(
                f"Parâmetro '{name}' não pode ser negativo (recebido: {val})."
            )

        if max_val is not None and val > max_val:
            raise InvalidDimensionsError(
                f"Parâmetro '{name}' não pode ser superior a {max_val} (recebido: {val})."
            )

        return float(val)

    def validate_dimensions(self, length: float, width: float, height: float) -> None:
        """Valida se as dimensões fornecidas do objeto são estritamente positivas e finitas.

        Args:
            length: Comprimento em cm.
            width: Largura em cm.
            height: Altura em cm.

        Raises:
            InvalidDimensionsError: Se qualquer valor for <= 0, NaN ou infinito.
        """
        self._validate_numeric_param(length, "comprimento", strictly_positive=True)
        self._validate_numeric_param(width, "largura", strictly_positive=True)
        self._validate_numeric_param(height, "altura", strictly_positive=True)

    def recommend(
        self,
        length: float,
        width: float,
        height: float,
        margin_per_face: float = DEFAULT_MARGIN_PER_FACE,
        wall_thickness: float = DEFAULT_WALL_THICKNESS,
        min_occupancy_threshold: float = DEFAULT_MIN_OCCUPANCY_THRESHOLD,
    ) -> RecommendationResult:
        """Recomenda a melhor embalagem e avalia todas as caixas do catálogo.

        Classifica todas as embalagens em quatro status (RECOMMENDED, ALTERNATIVE,
        NOT_RECOMMENDED, INCOMPATIBLE), gerando justificativas dinâmicas e métricas
        completas tanto para opções compatíveis quanto para incompatíveis.

        Args:
            length: Comprimento do objeto em cm.
            width: Largura do objeto em cm.
            height: Altura do objeto em cm.
            margin_per_face: Margem de acondicionamento por face em cm (padrão 0.5 cm).
            wall_thickness: Espessura de parede estimada em cm por face (padrão 0.4 cm).
            min_occupancy_threshold: Limiar percentual de ocupação mínima para o status
                ALTERNATIVE (padrão 20.0%, heurística de projeto).

        Returns:
            Instância de RecommendationResult contendo a recomendação e avaliações.

        Raises:
            InvalidDimensionsError: Se dimensões, margem, espessura ou limiar forem inválidos.
        """
        # Validação de dimensões do objeto
        self.validate_dimensions(length, width, height)

        # Validação da margem de segurança (>= 0)
        self._validate_numeric_param(
            margin_per_face, "margem por face", strictly_positive=False
        )

        # Validação da espessura de parede (>= 0)
        self._validate_numeric_param(
            wall_thickness, "espessura de parede", strictly_positive=False
        )

        # Validação do limiar de ocupação volumétrica (0.0% a 100.0%)
        self._validate_numeric_param(
            min_occupancy_threshold,
            "limiar de ocupação mínima",
            strictly_positive=False,
            max_val=100.0,
        )

        # Dimensões necessárias do objeto com margem de segurança (+ 2 * margem por eixo)
        total_margin = 2.0 * margin_per_face
        req_l = length + total_margin
        req_w = width + total_margin
        req_h = height + total_margin

        # Volumes do objeto
        obj_vol = length * width * height
        req_vol = req_l * req_w * req_h

        # Redução total de parede por eixo da caixa
        total_wall_reduction = 2.0 * wall_thickness

        compatible_fits: List[PackageFit] = []
        package_evaluations: List[PackageEvaluation] = []

        # Permutações ortogonais únicas das dimensões necessárias do objeto (3! = 6)
        permutations = list(set(itertools.permutations([req_l, req_w, req_h])))

        for pkg in self.packages:
            int_dims = pkg.get_internal_dimensions(wall_thickness=wall_thickness)
            int_l, int_w, int_h = int_dims
            int_vol = pkg.get_internal_volume(wall_thickness=wall_thickness)
            is_estimated = not pkg.has_confirmed_internal_dimensions

            best_orientation_fit: Optional[OrientationFit] = None

            # 1. Avalia se cabe em alguma permutação ortogonal
            for perm in permutations:
                p_l, p_w, p_h = perm

                if p_l <= int_l and p_w <= int_w and p_h <= int_h:
                    clearance = (
                        int_l - p_l,
                        int_w - p_w,
                        int_h - p_h,
                    )

                    desc = (
                        f"C interno acomoda {p_l:.1f}cm (folga: {clearance[0]:.1f}cm), "
                        f"L interno acomoda {p_w:.1f}cm (folga: {clearance[1]:.1f}cm), "
                        f"A interno acomoda {p_h:.1f}cm (folga: {clearance[2]:.1f}cm)"
                    )

                    candidate_fit = OrientationFit(
                        aligned_dimensions=(p_l, p_w, p_h),
                        clearance=clearance,
                        description=desc,
                    )

                    if best_orientation_fit is None or min(
                        candidate_fit.clearance
                    ) > min(best_orientation_fit.clearance):
                        best_orientation_fit = candidate_fit

            # Se a embalagem é dimensionalmente compatível
            if best_orientation_fit is not None:
                occ_ratio = (obj_vol / int_vol) * 100.0 if int_vol > 0 else 0.0
                occ_ratio_margin = (
                    (req_vol / int_vol) * 100.0 if int_vol > 0 else 0.0
                )

                fit = PackageFit(
                    package=pkg,
                    internal_dimensions=int_dims,
                    internal_volume=int_vol,
                    is_internal_estimated=is_estimated,
                    orientation=best_orientation_fit,
                    bounding_box_volume=obj_vol,
                    required_volume=req_vol,
                    occupancy_ratio=occ_ratio,
                    occupancy_ratio_with_margin=occ_ratio_margin,
                )
                compatible_fits.append(fit)
            else:
                # 2. Caso incompatível: calcula a orientação com menor déficit dimensional
                best_deficit_perm: Optional[Tuple[float, float, float]] = None
                min_total_deficit = float("inf")
                best_deficits: Tuple[float, float, float] = (0.0, 0.0, 0.0)

                for perm in permutations:
                    p_l, p_w, p_h = perm
                    def_l = max(0.0, p_l - int_l)
                    def_w = max(0.0, p_w - int_w)
                    def_h = max(0.0, p_h - int_h)
                    tot_def = def_l + def_w + def_h

                    if tot_def < min_total_deficit:
                        min_total_deficit = tot_def
                        best_deficit_perm = perm
                        best_deficits = (def_l, def_w, def_h)

                # Monta a justificativa dinâmica com os eixos excedentes
                exceeded_parts: List[str] = []
                axis_names = ["comprimento", "largura", "altura"]
                deficit_map: Dict[str, float] = {}

                for ax_name, ax_def in zip(axis_names, best_deficits):
                    if ax_def > 0:
                        exceeded_parts.append(f"{ax_name} em {ax_def:.1f} cm")
                        deficit_map[f"excesso_{ax_name}_cm"] = round(ax_def, 2)

                deficit_str = ", ".join(exceeded_parts)
                justification = (
                    f"Incompatível: dimensões necessárias excedem o espaço interno útil. "
                    f"Na melhor orientação ({best_deficit_perm[0]:.1f}×{best_deficit_perm[1]:.1f}×{best_deficit_perm[2]:.1f} cm), "
                    f"excede {deficit_str} (nenhuma orientação é viável)."
                )

                deficit_details = {
                    "melhor_orientacao_cm": [
                        round(d, 2) for d in best_deficit_perm
                    ],
                    "deficits_cm": deficit_map,
                    "deficit_total_cm": round(min_total_deficit, 2),
                }

                evaluation = PackageEvaluation(
                    package=pkg,
                    status=PackageStatus.INCOMPATIBLE,
                    is_compatible=False,
                    justification=justification,
                    external_dimensions=pkg.external_dimensions,
                    internal_dimensions=int_dims,
                    internal_volume=int_vol,
                    is_internal_estimated=is_estimated,
                    price=pkg.price,
                    orientation=None,
                    clearance=None,
                    occupancy_ratio=None,
                    occupancy_ratio_with_margin=None,
                    deficit_details=deficit_details,
                )
                package_evaluations.append(evaluation)

        # Ordena as compatíveis por menor volume interno útil e menor preço
        compatible_fits.sort(key=lambda fit: (fit.internal_volume, fit.package.price))

        recommended: Optional[PackageFit] = None
        alternatives: List[PackageFit] = []
        not_recommended: List[PackageFit] = []

        # Classifica as embalagens compatíveis segundo os status definidos
        for idx, fit in enumerate(compatible_fits):
            pkg = fit.package
            occ = fit.occupancy_ratio

            if idx == 0:
                # Regra: menor embalagem compatível é sempre RECOMMENDED, independentemente da ocupação
                status = PackageStatus.RECOMMENDED
                recommended = fit
                justification = (
                    f"Recomendada: menor embalagem compatível com as dimensões necessárias "
                    f"(volume útil de {fit.internal_volume / 1000.0:.2f} L, ocupação de {occ:.1f}%)."
                )
            else:
                # Demais compatíveis: compara com o limiar configurável
                if occ >= min_occupancy_threshold:
                    status = PackageStatus.ALTERNATIVE
                    alternatives.append(fit)
                    justification = (
                        f"Alternativa: embalagem compatível com boa acomodação "
                        f"({occ:.1f}% de ocupação útil >= limiar de {min_occupancy_threshold:.0f}%), "
                        f"com maior folga disponível."
                    )
                else:
                    status = PackageStatus.NOT_RECOMMENDED
                    not_recommended.append(fit)
                    justification = (
                        f"Não indicada: embalagem compatível, porém com baixa ocupação volumétrica "
                        f"({occ:.1f}% < limiar de {min_occupancy_threshold:.0f}%), gerando espaço ocioso excessivo."
                    )

            ev = PackageEvaluation(
                package=pkg,
                status=status,
                is_compatible=True,
                justification=justification,
                external_dimensions=pkg.external_dimensions,
                internal_dimensions=fit.internal_dimensions,
                internal_volume=fit.internal_volume,
                is_internal_estimated=fit.is_internal_estimated,
                price=pkg.price,
                orientation=fit.orientation,
                clearance=fit.orientation.clearance,
                occupancy_ratio=fit.occupancy_ratio,
                occupancy_ratio_with_margin=fit.occupancy_ratio_with_margin,
                deficit_details=None,
            )
            package_evaluations.append(ev)

        # Ordena a lista geral de avaliações:
        # Primeiro compatíveis (por volume interno útil/preço), depois incompatíveis
        status_priority = {
            PackageStatus.RECOMMENDED: 1,
            PackageStatus.ALTERNATIVE: 2,
            PackageStatus.NOT_RECOMMENDED: 3,
            PackageStatus.INCOMPATIBLE: 4,
        }
        package_evaluations.sort(
            key=lambda ev: (
                status_priority[ev.status],
                ev.internal_volume,
                ev.price,
            )
        )

        return RecommendationResult(
            original_dimensions=(length, width, height),
            margin_per_face=margin_per_face,
            total_margin_per_axis=total_margin,
            wall_thickness=wall_thickness,
            total_wall_reduction_per_axis=total_wall_reduction,
            min_occupancy_threshold=min_occupancy_threshold,
            required_dimensions=(req_l, req_w, req_h),
            bounding_box_volume=obj_vol,
            required_volume=req_vol,
            recommended=recommended,
            alternatives=alternatives,
            not_recommended=not_recommended,
            all_compatible=compatible_fits,
            evaluations=package_evaluations,
        )
