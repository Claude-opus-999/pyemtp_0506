"""Models — physical element implementations: lumped, switches, nonlinear, lines, transformers, sources."""

from .base import Device
from .multiport import MultiPortDevice
from .lumped import (
    ResistorDevice, InductorDevice, CapacitorDevice, SeriesRLDevice,
    _update_series_rl_history_static,
)
from .switches import SwitchDevice
from .nonlinear import (
    NonlinearResistorDevice, LPMFlashoverDevice,
    InsulatorFlashoverLPM, LPMConfig, LPMInsulatorType,
    SegmentedSolverHelper, SegmentedMOAResistor,
)
from .lines import (
    BergeronLineDevice, ULMLineDevice,
    BergeronLine, TransmissionLineInterface, TransmissionLineFactory, DelayBuffer,
    FitULMData, FitULMReader, ULMLine, ULMModel, ULMBatchPack,
)
from .fitulm import FitULMSpec, FitULMResolver
from .transformers import (
    UMECTransformerDevice,
    UMECTransformer, UMECTransformerData, WindingType,
    create_umec_transformer_3ph_bank,
)
from .sources import (
    BaseLightningCurrentSource, TWOEXPFCurrentSource, HEIDLERFCurrentSource,
    LightningWaveform, STANDARD_DOUBLE_EXPONENTIAL_PARAMS,
    create_lightning_current_source, create_standard_twoexpf_current_source,
)

__all__ = [
    "Device", "MultiPortDevice",
    "ResistorDevice", "InductorDevice", "CapacitorDevice", "SeriesRLDevice",
    "_update_series_rl_history_static",
    "SwitchDevice",
    "NonlinearResistorDevice", "LPMFlashoverDevice",
    "InsulatorFlashoverLPM", "LPMConfig", "LPMInsulatorType",
    "SegmentedSolverHelper", "SegmentedMOAResistor",
    "BergeronLineDevice", "ULMLineDevice",
    "BergeronLine", "TransmissionLineInterface", "TransmissionLineFactory", "DelayBuffer",
    "FitULMData", "FitULMReader", "ULMLine", "ULMModel", "ULMBatchPack",
    "FitULMSpec", "FitULMResolver",
    "UMECTransformerDevice",
    "UMECTransformer", "UMECTransformerData", "WindingType",
    "create_umec_transformer_3ph_bank",
    "BaseLightningCurrentSource", "TWOEXPFCurrentSource", "HEIDLERFCurrentSource",
    "LightningWaveform", "STANDARD_DOUBLE_EXPONENTIAL_PARAMS",
    "create_lightning_current_source", "create_standard_twoexpf_current_source",
]
