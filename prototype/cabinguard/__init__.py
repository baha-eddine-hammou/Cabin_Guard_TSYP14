"""
CabinGuard-ADI: Multimodal Edge-AI Framework for Driver Medical Crisis Differentiation & MRM.
Phase 1 PoC Prototype & Simulation Suite.
"""
from .config import *
from .simulator import MultimodalSensorSimulator, ScenarioType, SensorFrame
from .feature_extraction import FeatureExtractor, ProcessedFeatures
from .classifier import BayesianEtiologyClassifier, ClassificationResult
from .watchdog import CrossSensorWatchdog, WatchdogDecision
from .safety_controller import VehicleSafetyController, MRMState, VehicleDynamicsState
from .telematics import TelematicsEngine, CANFDFrame, ETSIDENMMessage, MedicalExtensionContainer
from .physdrive_adapter import PhysDriveAdapter, PhysDriveSession
from .dataset_types import DatasetWindow, SignalRecord, SignalStatus
from .uci_adapters import MHealthAdapter, UciHarAdapter
from .mitbih_adapter import MitBihAdapter
from .learned_classifier import LearnedEtiologyClassifier
from .dataset_models import (
    MitBihArrhythmiaClassifier,
    MHealthActivityClassifier,
    UciHarActivityClassifier,
    PhysDriveQualityModel,
)

__version__ = "1.0.0"

