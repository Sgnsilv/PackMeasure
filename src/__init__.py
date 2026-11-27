"""Módulo principal do pacote PackMeasure."""

from src.capture import (
    CameraConfig,
    CameraDevice,
    CameraError,
    CameraOpenError,
    CameraSource,
    FrameValidationError,
    PackMeasureError,
    StereoCameraCapture,
    StereoCaptureError,
    StereoPair,
)
from src.packaging import (
    CatalogError,
    CatalogNotFoundError,
    CatalogValidationError,
    InvalidDimensionsError,
    OrientationFit,
    Package,
    PackageFit,
    PackageRecommender,
    PackagingError,
    RecommendationResult,
)

__all__ = [
    # Módulo de captura
    "CameraConfig",
    "CameraDevice",
    "CameraError",
    "CameraOpenError",
    "CameraSource",
    "FrameValidationError",
    "PackMeasureError",
    "StereoCameraCapture",
    "StereoCaptureError",
    "StereoPair",
    # Módulo de embalagens
    "CatalogError",
    "CatalogNotFoundError",
    "CatalogValidationError",
    "InvalidDimensionsError",
    "OrientationFit",
    "Package",
    "PackageFit",
    "PackageRecommender",
    "PackagingError",
    "RecommendationResult",
]
