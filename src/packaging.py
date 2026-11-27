"""Módulo de catálogo e recomendação de embalagens dos Correios para o PackMeasure.

Fornece classes e algoritmos para carregar o catálogo de embalagens,
validar dimensões tridimensionais de objetos, estimar o espaço interno útil
com base na espessura de parede da chapa de papelão (hipótese de projeto),
aplicar margem de segurança de acondicionamento, testar compatibilidade espacial
considerando permutações ortogonais e selecionar a melhor embalagem com base
no menor volume interno útil e menor preço de referência.
"""

from __future__ import annotations

import itertools
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Hipótese padrão de projeto: espessura média estimada da parede de papelão ondulado (4 mm)
DEFAULT_WALL_THICKNESS: float = 0.4  # cm

# Margem padrão de segurança para acondicionamento e proteção por face (5 mm)
DEFAULT_MARGIN_PER_FACE: float = 0.5  # cm

DISCLAIMER_TEXT: str = (
    "A compatibilidade é estimada com base nas hipóteses dimensionais do projeto e não "
    "garante o acondicionamento físico definitivo, nem realiza estimativa ou otimização de custo de frete."
)


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
    """Dimensões, margens ou espessuras inválidas (não positivas, nulas, infinitas ou NaN)."""

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

    def get_internal_dimensions(self, wall_thickness: float = DEFAULT_WALL_THICKNESS) -> Tuple[float, float, float]:
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

        # Cálculo estimado subtraindo 2 * wall_thickness em cada eixo
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

    def get_internal_volume_liters(self, wall_thickness: float = DEFAULT_WALL_THICKNESS) -> float:
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
class RecommendationResult:
    """Resultado consolidado da recomendação de embalagens.

    Attributes:
        original_dimensions: Dimensões originais do objeto (C, L, A) em cm.
        margin_per_face: Margem de segurança aplicada por face em cm.
        total_margin_per_axis: Acréscimo total aplicado ao objeto em cada dimensão (2 * margin_per_face).
        wall_thickness: Espessura estimada de parede adotada por face da caixa em cm.
        total_wall_reduction_per_axis: Redução total por eixo aplicada à caixa externa (2 * wall_thickness).
        required_dimensions: Dimensões necessárias do objeto após acréscimo da margem.
        bounding_box_volume: Volume da caixa delimitadora original do objeto em cm³.
        required_volume: Volume necessário após acréscimo da margem em cm³.
        recommended: Embalagem recomendada (ótima por menor volume interno e menor preço) ou None.
        alternatives: Lista das demais embalagens compatíveis ordenadas.
        all_compatible: Lista completa de embalagens compatíveis ordenadas.
        disclaimer: Aviso de que a compatibilidade é estimada e não garante acondicionamento físico.
    """

    original_dimensions: Tuple[float, float, float]
    margin_per_face: float
    total_margin_per_axis: float
    wall_thickness: float
    total_wall_reduction_per_axis: float
    required_dimensions: Tuple[float, float, float]
    bounding_box_volume: float
    required_volume: float
    recommended: Optional[PackageFit] = None
    alternatives: List[PackageFit] = field(default_factory=list)
    all_compatible: List[PackageFit] = field(default_factory=list)
    disclaimer: str = DISCLAIMER_TEXT

    @property
    def has_compatible(self) -> bool:
        """Indica se ao menos uma embalagem do catálogo acomoda o objeto."""
        return self.recommended is not None

    def to_dict(self) -> Dict[str, Any]:
        """Converte o resultado consolidado para dicionário estruturado."""
        return {
            "success": self.has_compatible,
            "disclaimer": self.disclaimer,
            "hypotheses": {
                "wall_thickness_per_face_cm": self.wall_thickness,
                "total_wall_reduction_per_axis_cm": self.total_wall_reduction_per_axis,
                "margin_per_face_cm": self.margin_per_face,
                "total_margin_per_axis_cm": self.total_margin_per_axis,
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
            "total_compatible": len(self.all_compatible),
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
                int_l = float(item["comprimento_interno"]) if "comprimento_interno" in item else None
                int_w = float(item["largura_interna"]) if "largura_interna" in item else None
                int_h = float(item["altura_interna"]) if "altura_interna" in item else None

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
    ) -> float:
        """Valida se um parâmetro numérico é válido, finito, não-NaN e positivo/não-negativo.

        Args:
            val: Valor a ser validado.
            name: Nome do parâmetro para identificação em mensagens de erro.
            strictly_positive: Se True, exige valor > 0. Se False, exige valor >= 0.

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
            raise InvalidDimensionsError(f"Parâmetro '{name}' deve ser um valor finito (recebido: {val}).")

        if strictly_positive and val <= 0:
            raise InvalidDimensionsError(
                f"Dimensão '{name}' deve ser estritamente positiva (> 0) (recebido: {val})."
            )

        if not strictly_positive and val < 0:
            raise InvalidDimensionsError(
                f"Parâmetro '{name}' não pode ser negativo (recebido: {val})."
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
    ) -> RecommendationResult:
        """Recomenda a melhor embalagem e identifica alternativas compatíveis.

        Avalia todas as 6 permutações ortogonais de acomodação do objeto no
        espaço interno útil (estimado ou confirmado) de cada embalagem cadastrada.
        Aplica a margem de segurança de acondicionamento (padrão 0.5 cm por face)
        ao objeto e deduz a espessura de parede estimada (padrão 0.4 cm por face)
        das embalagens com dimensões nominais externas.

        Ordena as opções compatíveis primariamente pelo menor volume interno útil
        e secundariamente pelo menor preço de referência.

        Args:
            length: Comprimento do objeto em cm.
            width: Largura do objeto em cm.
            height: Altura do objeto em cm.
            margin_per_face: Margem de acondicionamento por face em cm (padrão 0.5 cm,
                acrescentando 1.0 cm ao total de cada dimensão do objeto).
            wall_thickness: Espessura de parede estimada em cm por face (padrão 0.4 cm,
                deduzindo 0.8 cm ao total de cada dimensão externa da caixa).

        Returns:
            Instância de RecommendationResult contendo a recomendação e detalhes.

        Raises:
            InvalidDimensionsError: Se dimensões, margem ou espessura forem inválidas.
        """
        # Validação de dimensões do objeto
        self.validate_dimensions(length, width, height)

        # Validação da margem de segurança (pode ser 0, mas não negativa nem NaN/inf)
        self._validate_numeric_param(margin_per_face, "margem por face", strictly_positive=False)

        # Validação da espessura de parede (pode ser 0, mas não negativa nem NaN/inf)
        self._validate_numeric_param(wall_thickness, "espessura de parede", strictly_positive=False)

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

        # Permutações ortogonais únicas das dimensões necessárias do objeto (3! = 6)
        permutations = list(set(itertools.permutations([req_l, req_w, req_h])))

        for pkg in self.packages:
            # Obtém dimensões internas úteis (confirmadas ou estimadas via espessura)
            int_dims = pkg.get_internal_dimensions(wall_thickness=wall_thickness)
            int_l, int_w, int_h = int_dims
            int_vol = pkg.get_internal_volume(wall_thickness=wall_thickness)
            is_estimated = not pkg.has_confirmed_internal_dimensions

            best_orientation_fit: Optional[OrientationFit] = None

            # Testa as permutações ortogonais contra o espaço interno útil
            for perm in permutations:
                p_l, p_w, p_h = perm

                # Condição estrita de compatibilidade dimensional interna
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

                    # Seleciona a orientação com melhor distribuição de folga (maior folga mínima)
                    if best_orientation_fit is None or min(candidate_fit.clearance) > min(
                        best_orientation_fit.clearance
                    ):
                        best_orientation_fit = candidate_fit

            # Se coube em ao menos uma orientação ortogonal
            if best_orientation_fit is not None:
                occ_ratio = (obj_vol / int_vol) * 100.0 if int_vol > 0 else 0.0
                occ_ratio_margin = (req_vol / int_vol) * 100.0 if int_vol > 0 else 0.0

                compatible_fits.append(
                    PackageFit(
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
                )

        # Ordenação:
        # 1º Menor volume interno útil da embalagem
        # 2º Menor preço conhecido de referência
        compatible_fits.sort(key=lambda fit: (fit.internal_volume, fit.package.price))

        recommended = compatible_fits[0] if compatible_fits else None
        alternatives = compatible_fits[1:] if len(compatible_fits) > 1 else []

        return RecommendationResult(
            original_dimensions=(length, width, height),
            margin_per_face=margin_per_face,
            total_margin_per_axis=total_margin,
            wall_thickness=wall_thickness,
            total_wall_reduction_per_axis=total_wall_reduction,
            required_dimensions=(req_l, req_w, req_h),
            bounding_box_volume=obj_vol,
            required_volume=req_vol,
            recommended=recommended,
            alternatives=alternatives,
            all_compatible=compatible_fits,
        )
