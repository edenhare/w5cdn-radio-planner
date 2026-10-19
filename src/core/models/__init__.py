"""Common Internal Representation (CIR) models."""

from core.models.aviation import AirfieldRecord, AviationFrequency
from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug
from core.models.preferences import ApiTokens, UserPreferences
from core.models.radio_spec import TargetRadioSpec
from core.models.template import PresetTemplateFile

__all__ = [
    "AirfieldRecord",
    "ApiTokens",
    "AviationFrequency",
    "Codeplug",
    "PresetTemplateFile",
    "RadioChannel",
    "TargetRadioSpec",
    "UserPreferences",
]
