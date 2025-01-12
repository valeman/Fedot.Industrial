import math
from enum import Enum
from multiprocessing import cpu_count

import numpy as np
import pywt
from fedot.core.pipelines.pipeline_builder import PipelineBuilder
from fedot.core.repository.dataset_types import DataTypesEnum
from fedot.core.repository.metrics_repository import ClassificationMetricsEnum, RegressionMetricsEnum
from fedot.core.repository.tasks import Task, TaskTypesEnum, TsForecastingParams
from torch import nn

from fedot_ind.core.metrics.metrics_implementation import calculate_classification_metric, calculate_regression_metric
from fedot_ind.core.models.nn.network_modules.losses import CenterLoss, CenterPlusLoss, ExpWeightedLoss, FocalLoss, \
    HuberLoss, LogCoshLoss, MaskedLossWrapper, RMSELoss, SMAPELoss, TweedieLoss
from fedot_ind.core.models.quantile.stat_features import autocorrelation, ben_corr, crest_factor, energy, \
    hjorth_complexity, hjorth_mobility, hurst_exponent, interquartile_range, kurtosis, mean_ema, mean_moving_median, \
    mean_ptp_distance, n_peaks, pfd, ptp_amp, q25, q5, q75, q95, shannon_entropy, skewness, slope, zero_crossing_rate
from fedot_ind.core.models.topological.topofeatures import *
from fedot_ind.core.models.topological.topofeatures import AverageHoleLifetimeFeature, \
    AveragePersistenceLandscapeFeature, BettiNumbersSumFeature, HolesNumberFeature, MaxHoleLifeTimeFeature, \
    PersistenceDiagramsExtractor, PersistenceEntropyFeature, RadiusAtMaxBNFeature, RelevantHolesNumber, \
    SimultaneousAliveHolesFeature, SumHoleLifetimeFeature
from fedot_ind.core.operation.transformation.data.hankel import HankelMatrix


def beta_thr(beta):
    return 0.56 * np.power(beta, 3) - 0.95 * np.power(beta, 2) + 1.82 * beta + 1.43


class ComputationalConstant(Enum):
    CPU_NUMBERS = math.ceil(cpu_count() * 0.7) if cpu_count() > 1 else 1
    GLOBAL_IMPORTS = {
        'numpy': 'np',
        'cupy': 'np',
        'torch': 'torch',
        'torch.nn': 'nn',
        'torch.nn.functional': 'F'
    }
    BATCH_SIZE_FOR_FEDOT_WORKER = 1000
    FEDOT_WORKER_NUM = 5
    FEDOT_WORKER_TIMEOUT_PARTITION = 2
    PATIENCE_FOR_EARLY_STOP = 15


class DataTypeConstant(Enum):
    MULTI_ARRAY = DataTypesEnum.image
    MATRIX = DataTypesEnum.table
    TRAJECTORY_MATRIX = HankelMatrix


class FeatureConstant(Enum):
    STAT_METHODS = {
        'mean_': np.mean,
        'median_': np.median,
        'std_': np.std,
        'max_': np.max,
        'min_': np.min,
        'q5_': q5,
        'q25_': q25,
        'q75_': q75,
        'q95_': q95
    }

    STAT_METHODS_GLOBAL = {
        'skewness_': skewness,
        'kurtosis_': kurtosis,
        'n_peaks_': n_peaks,
        'slope_': slope,
        'ben_corr_': ben_corr,
        'interquartile_range_': interquartile_range,
        'energy_': energy,
        'cross_rate_': zero_crossing_rate,
        'autocorrelation_': autocorrelation,
        'shannon_entropy_': shannon_entropy,
        'ptp_amplitude_': ptp_amp,
        'mean_ptp_distance_': mean_ptp_distance,
        'crest_factor_': crest_factor,
        'mean_ema_': mean_ema,
        'mean_moving_median_': mean_moving_median,
        'hjorth_mobility_': hjorth_mobility,
        'hjorth_complexity_': hjorth_complexity,
        'hurst_exponent_': hurst_exponent,
        'petrosian_fractal_dimension_': pfd
    }

    PERSISTENCE_DIAGRAM_FEATURES = {'HolesNumberFeature': HolesNumberFeature(),
                                    'MaxHoleLifeTimeFeature': MaxHoleLifeTimeFeature(),
                                    'RelevantHolesNumber': RelevantHolesNumber(),
                                    'AverageHoleLifetimeFeature': AverageHoleLifetimeFeature(),
                                    'SumHoleLifetimeFeature': SumHoleLifetimeFeature(),
                                    'PersistenceEntropyFeature': PersistenceEntropyFeature(),
                                    'SimultaneousAliveHolesFeature': SimultaneousAliveHolesFeature(),
                                    'AveragePersistenceLandscapeFeature': AveragePersistenceLandscapeFeature(),
                                    'BettiNumbersSumFeature': BettiNumbersSumFeature(),
                                    'RadiusAtMaxBNFeature': RadiusAtMaxBNFeature()}

    PERSISTENCE_DIAGRAM_EXTRACTOR = PersistenceDiagramsExtractor(takens_embedding_dim=1,
                                                                 takens_embedding_delay=2,
                                                                 homology_dimensions=(
                                                                     0, 1),
                                                                 parallel=False)
    DISCRETE_WAVELETS = pywt.wavelist(kind='discrete')
    CONTINUOUS_WAVELETS = pywt.wavelist(kind='continuous')
    WAVELET_SCALES = [2, 4, 10, 20]
    SINGULAR_VALUE_MEDIAN_THR = 2.58
    SINGULAR_VALUE_BETA_THR = beta_thr


class FedotOperationConstant(Enum):
    EXCLUDED_OPERATION = ['fast_ica']
    FEDOT_TASK = {'classification': Task(TaskTypesEnum.classification),
                  'regression': Task(TaskTypesEnum.regression),
                  'ts_forecasting': Task(TaskTypesEnum.ts_forecasting,
                                         TsForecastingParams(forecast_length=1))}
    FEDOT_API_PARAMS = default_param_values_dict = dict(problem=None,
                                                        task_params=None,
                                                        timeout=None,
                                                        n_jobs=-1,
                                                        logging_level=50,
                                                        seed=42,
                                                        parallelization_mode='populational',
                                                        show_progress=True,
                                                        max_depth=6,
                                                        max_arity=3,
                                                        pop_size=20,
                                                        num_of_generations=None,
                                                        keep_n_best=1,
                                                        available_operations=None,
                                                        metric=None,
                                                        cv_folds=2,
                                                        genetic_scheme=None,
                                                        early_stopping_iterations=None,
                                                        early_stopping_timeout=10,
                                                        optimizer=None,
                                                        collect_intermediate_metric=False,
                                                        max_pipeline_fit_time=None,
                                                        initial_assumption=None,
                                                        preset=None,
                                                        use_pipelines_cache=True,
                                                        use_preprocessing_cache=True,
                                                        use_input_preprocessing=True,
                                                        use_auto_preprocessing=False,
                                                        use_meta_rules=False,
                                                        cache_dir=None,
                                                        keep_history=True,
                                                        history_dir=None,
                                                        with_tuning=True
                                                        )
    FEDOT_GET_METRICS = {'regression': calculate_regression_metric,
                         'classification': calculate_classification_metric}
    FEDOT_TUNING_METRICS = {'classification': ClassificationMetricsEnum.accuracy,
                            'regression': RegressionMetricsEnum.RMSE}
    FEDOT_HEAD_ENSEMBLE = {'regression': 'fedot_regr',
                           'classification': 'fedot_cls'}
    FEDOT_ATOMIZE_OPERATION = {'regression': 'fedot_regr',
                               'classification': 'fedot_cls'}
    AVAILABLE_CLS_OPERATIONS = [
        'rf',
        'logit',
        'scaling',
        'normalization',
        'pca',
        'knn',
        'xgboost',
        'multinb',
        'dt',
        'mlp',
        'kernel_pca',
        'isolation_forest_class']

    AVAILABLE_REG_OPERATIONS = ['rfr',
                                'scaling',
                                'normalization',
                                'pca',
                                'xgbreg',
                                'dtreg',
                                'treg',
                                'knnreg',
                                'kernel_pca',
                                'isolation_forest_reg']

    FEDOT_ASSUMPTIONS = {
        'classification': PipelineBuilder().add_node('quantile_extractor').add_node('logit'),
        'regression': PipelineBuilder().add_node('quantile_extractor').add_node('treg'),
        'ts_forecasting': PipelineBuilder().add_node('lagged').add_node('ridge')
    }


class ModelCompressionConstant(Enum):
    ENERGY_THR = [0.9, 0.95, 0.99, 0.999]
    DECOMPOSE_MODE = 'channel'
    FORWARD_MODE = 'one_layer'
    HOER_LOSS = 0.1
    ORTOGONAL_LOSS = 10
    MODELS_FROM_LENGTH = {
        122: 'ResNet18',
        218: 'ResNet34',
        320: 'ResNet50',
        626: 'ResNet101',
        932: 'ResNet152',
    }


class TorchLossesConstant(Enum):
    CROSS_ENTROPY = nn.CrossEntropyLoss
    MULTI_CLASS_CROSS_ENTROPY = nn.BCEWithLogitsLoss
    MSE = nn.MSELoss
    RMSE = RMSELoss()
    SMAPE = SMAPELoss()
    TWEEDIE_LOSS = TweedieLoss()
    FOCAL_LOSS = FocalLoss()
    CENTER_PLUS_LOSS = CenterPlusLoss
    CENTER_LOSS = CenterLoss
    MASK_LOSS = MaskedLossWrapper
    LOG_COSH_LOSS = LogCoshLoss()
    HUBER_LOSS = HuberLoss()
    EXPONENTIAL_WEIGHTED_LOSS = ExpWeightedLoss


class BenchmarkDatasets(Enum):
    MULTI_REG_BENCH = [
        "AppliancesEnergy",
        "AustraliaRainfall",
        "BeijingPM10Quality",
        "BeijingPM25Quality",
        "BenzeneConcentration",
        "BIDMC32HR",
        "BIDMC32RR",
        "BIDMC32SpO2",
        "Covid3Month",
        "FloodModeling1",
        "FloodModeling2",
        "FloodModeling3",
        "HouseholdPowerConsumption1",
        "HouseholdPowerConsumption2",
        "IEEEPPG",
        "LiveFuelMoistureContent",
        "NewsHeadlineSentiment",
        "NewsTitleSentiment",
        "PPGDalia",
    ]
    UNI_CLF_BENCH = [
        "ACSF1",
        "Adiac",
        "ArrowHead",
        "Beef",
        "BeetleFly",
        "BirdChicken",
        "BME",
        "Car",
        "CBF",
        "Chinatown",
        "ChlorineConcentration",
        "CinCECGTorso",
        "Coffee",
        "Computers",
        "CricketX",
        "CricketY",
        "CricketZ",
        "Crop",
        "DiatomSizeReduction",
        "DistalPhalanxOutlineCorrect",
        "DistalPhalanxOutlineAgeGroup",
        "DistalPhalanxTW",
        "Earthquakes",
        "ECG200",
        "ECG5000",
        "ECGFiveDays",
        "ElectricDevices",
        "EOGHorizontalSignal",
        "EOGVerticalSignal",
        "EthanolLevel",
        "FaceAll",
        "FaceFour",
        "FacesUCR",
        "FiftyWords",
        "Fish",
        "FordA",
        "FordB",
        "FreezerRegularTrain",
        "FreezerSmallTrain",
        "Fungi",
        "GunPoint",
        "GunPointAgeSpan",
        "GunPointMaleVersusFemale",
        "GunPointOldVersusYoung",
        "Ham",
        "HandOutlines",
        "Haptics",
        "Herring",
        "HouseTwenty",
        "InlineSkate",
        "InsectEPGRegularTrain",
        "InsectEPGSmallTrain",
        "InsectWingbeatSound",
        "ItalyPowerDemand",
        "LargeKitchenAppliances",
        "Lightning2",
        "Lightning7",
        "Mallat",
        "Meat",
        "MedicalImages",
        "MiddlePhalanxOutlineCorrect",
        "MiddlePhalanxOutlineAgeGroup",
        "MiddlePhalanxTW",
        "MixedShapesRegularTrain",
        "MixedShapesSmallTrain",
        "MoteStrain",
        "NonInvasiveFetalECGThorax1",
        "NonInvasiveFetalECGThorax2",
        "OliveOil",
        "OSULeaf",
        "PhalangesOutlinesCorrect",
        "Phoneme",
        "PigAirwayPressure",
        "PigArtPressure",
        "PigCVP",
        "Plane",
        "PowerCons",
        "ProximalPhalanxOutlineCorrect",
        "ProximalPhalanxOutlineAgeGroup",
        "ProximalPhalanxTW",
        "RefrigerationDevices",
        "Rock",
        "ScreenType",
        "SemgHandGenderCh2",
        "SemgHandMovementCh2",
        "SemgHandSubjectCh2",
        "ShapeletSim",
        "ShapesAll",
        "SmallKitchenAppliances",
        "SmoothSubspace",
        "SonyAIBORobotSurface1",
        "SonyAIBORobotSurface2",
        "StarlightCurves",
        "Strawberry",
        "SwedishLeaf",
        "Symbols",
        "SyntheticControl",
        "ToeSegmentation1",
        "ToeSegmentation2",
        "Trace",
        "TwoLeadECG",
        "TwoPatterns",
        "UMD",
        "UWaveGestureLibraryAll",
        "UWaveGestureLibraryX",
        "UWaveGestureLibraryY",
        "UWaveGestureLibraryZ",
        "Wafer",
        "Wine",
        "WordSynonyms",
        "Worms",
        "WormsTwoClass",
        "Yoga",
    ]
    MULTI_CLF_BENCH = [
        "ArticularyWordRecognition",
        "AtrialFibrillation",
        "BasicMotions",
        "Cricket",
        "DuckDuckGeese",
        "EigenWorms",
        "Epilepsy",
        "EthanolConcentration",
        "ERing",
        "FaceDetection",
        "FingerMovements",
        "HandMovementDirection",
        "Handwriting",
        "Heartbeat",
        "Libras",
        "LSST",
        "MotorImagery",
        "NATOPS",
        "PenDigits",
        "PEMS-SF",
        "PhonemeSpectra",
        "RacketSports",
        "SelfRegulationSCP1",
        "SelfRegulationSCP2",
        "StandWalkJump",
        "UWaveGestureLibrary",
    ]


STAT_METHODS = FeatureConstant.STAT_METHODS.value
STAT_METHODS_GLOBAL = FeatureConstant.STAT_METHODS_GLOBAL.value
PERSISTENCE_DIAGRAM_FEATURES = FeatureConstant.PERSISTENCE_DIAGRAM_FEATURES.value
PERSISTENCE_DIAGRAM_EXTRACTOR = FeatureConstant.PERSISTENCE_DIAGRAM_EXTRACTOR.value
DISCRETE_WAVELETS = FeatureConstant.DISCRETE_WAVELETS.value
CONTINUOUS_WAVELETS = FeatureConstant.CONTINUOUS_WAVELETS.value
WAVELET_SCALES = FeatureConstant.WAVELET_SCALES.value
SINGULAR_VALUE_MEDIAN_THR = FeatureConstant.SINGULAR_VALUE_MEDIAN_THR.value
SINGULAR_VALUE_BETA_THR = FeatureConstant.SINGULAR_VALUE_BETA_THR

AVAILABLE_REG_OPERATIONS = FedotOperationConstant.AVAILABLE_REG_OPERATIONS.value
AVAILABLE_CLS_OPERATIONS = FedotOperationConstant.AVAILABLE_CLS_OPERATIONS.value
EXCLUDED_OPERATION = FedotOperationConstant.EXCLUDED_OPERATION.value
FEDOT_HEAD_ENSEMBLE = FedotOperationConstant.FEDOT_HEAD_ENSEMBLE.value
FEDOT_TASK = FedotOperationConstant.FEDOT_TASK.value
FEDOT_ATOMIZE_OPERATION = FedotOperationConstant.FEDOT_ATOMIZE_OPERATION.value
FEDOT_GET_METRICS = FedotOperationConstant.FEDOT_GET_METRICS.value
FEDOT_TUNING_METRICS = FedotOperationConstant.FEDOT_TUNING_METRICS.value
FEDOT_ASSUMPTIONS = FedotOperationConstant.FEDOT_ASSUMPTIONS.value
FEDOT_API_PARAMS = FedotOperationConstant.FEDOT_API_PARAMS.value

CPU_NUMBERS = ComputationalConstant.CPU_NUMBERS.value
BATCH_SIZE_FOR_FEDOT_WORKER = ComputationalConstant.BATCH_SIZE_FOR_FEDOT_WORKER.value
FEDOT_WORKER_NUM = ComputationalConstant.FEDOT_WORKER_NUM.value
FEDOT_WORKER_TIMEOUT_PARTITION = ComputationalConstant.FEDOT_WORKER_TIMEOUT_PARTITION.value
PATIENCE_FOR_EARLY_STOP = ComputationalConstant.PATIENCE_FOR_EARLY_STOP.value

MULTI_ARRAY = DataTypeConstant.MULTI_ARRAY.value
MATRIX = DataTypeConstant.MATRIX.value
TRAJECTORY_MATRIX = DataTypeConstant.TRAJECTORY_MATRIX.value

ENERGY_THR = ModelCompressionConstant.ENERGY_THR.value
DECOMPOSE_MODE = ModelCompressionConstant.DECOMPOSE_MODE.value
FORWARD_MODE = ModelCompressionConstant.FORWARD_MODE.value
HOER_LOSS = ModelCompressionConstant.HOER_LOSS.value
ORTOGONAL_LOSS = ModelCompressionConstant.ORTOGONAL_LOSS.value
MODELS_FROM_LENGTH = ModelCompressionConstant.MODELS_FROM_LENGTH.value

CROSS_ENTROPY = TorchLossesConstant.CROSS_ENTROPY.value
MULTI_CLASS_CROSS_ENTROPY = TorchLossesConstant.MULTI_CLASS_CROSS_ENTROPY.value
MSE = TorchLossesConstant.MSE.value
RMSE = TorchLossesConstant.RMSE.value
SMAPE = TorchLossesConstant.SMAPE.value
TWEEDIE_LOSS = TorchLossesConstant.TWEEDIE_LOSS.value
FOCAL_LOSS = TorchLossesConstant.FOCAL_LOSS.value
CENTER_PLUS_LOSS = TorchLossesConstant.CENTER_PLUS_LOSS.value
CENTER_LOSS = TorchLossesConstant.CENTER_LOSS.value
MASK_LOSS = TorchLossesConstant.MASK_LOSS.value
LOG_COSH_LOSS = TorchLossesConstant.LOG_COSH_LOSS.value
HUBER_LOSS = TorchLossesConstant.HUBER_LOSS.value
EXPONENTIAL_WEIGHTED_LOSS = TorchLossesConstant.EXPONENTIAL_WEIGHTED_LOSS.value

MULTI_REG_BENCH = BenchmarkDatasets.MULTI_REG_BENCH.value
UNI_CLF_BENCH = BenchmarkDatasets.UNI_CLF_BENCH.value
MULTI_CLF_BENCH = BenchmarkDatasets.MULTI_CLF_BENCH.value
