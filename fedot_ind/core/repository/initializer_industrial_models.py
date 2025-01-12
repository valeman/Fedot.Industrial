import pathlib

from fedot.api.api_utils.api_composer import ApiComposer
from fedot.api.api_utils.api_params_repository import ApiParamsRepository
from fedot.core.composer.metrics import F1, Accuracy
from fedot.core.data.merge.data_merger import ImageDataMerger, TSDataMerger
from fedot.core.operations.evaluation.operation_implementations.data_operations.ts_transformations import \
    LaggedImplementation, TsSmoothingImplementation
from fedot.core.operations.operation import Operation
from fedot.core.pipelines.tuning.search_space import PipelineSearchSpace
from fedot.core.pipelines.verification import class_rules
from fedot.core.repository.operation_types_repository import OperationTypesRepository
from golem.core.optimisers.genetic.operators.crossover import Crossover

from fedot_ind.api.utils.path_lib import PROJECT_PATH
from fedot_ind.core.repository.industrial_implementations.abstract import merge_predicts, preprocess_predicts, \
    predict_for_fit, predict, predict_operation, postprocess_predicts, update_column_types, transform_lagged, \
    transform_lagged_for_fit, transform_smoothing
from fedot_ind.core.repository.industrial_implementations.metric import metric_f1, metric_acc
from fedot_ind.core.repository.industrial_implementations.optimisation import _get_default_industrial_mutations, \
    MutationStrengthEnumIndustrial, has_no_data_flow_conflicts_in_industrial_pipeline, _crossover_by_type
from fedot_ind.core.tuning.search_space import get_industrial_search_space


class IndustrialModels:
    def __init__(self):
        self.industrial_data_operation_path = pathlib.Path(PROJECT_PATH, 'fedot_ind',
                                                           'core',
                                                           'repository',
                                                           'data',
                                                           'industrial_data_operation_repository.json')
        self.base_data_operation_path = pathlib.Path(
            'data_operation_repository.json')

        self.industrial_model_path = pathlib.Path(PROJECT_PATH, 'fedot_ind',
                                                  'core',
                                                  'repository',
                                                  'data',
                                                  'industrial_model_repository.json')
        self.base_model_path = pathlib.Path('model_repository.json')

    def setup_repository(self):
        OperationTypesRepository.__repository_dict__.update(
            {'data_operation': {'file': self.industrial_data_operation_path,
                                'initialized_repo': True,
                                'default_tags': []}})

        OperationTypesRepository.assign_repo(
            'data_operation', self.industrial_data_operation_path)

        OperationTypesRepository.__repository_dict__.update(
            {'model': {'file': self.industrial_model_path,
                       'initialized_repo': True,
                       'default_tags': []}})
        OperationTypesRepository.assign_repo(
            'model', self.industrial_model_path)

        setattr(PipelineSearchSpace, "get_parameters_dict",
                get_industrial_search_space)
        setattr(ApiParamsRepository, "_get_default_mutations",
                _get_default_industrial_mutations)
        setattr(Crossover, '_crossover_by_type', _crossover_by_type)

        setattr(ImageDataMerger, "preprocess_predicts", preprocess_predicts)
        setattr(ImageDataMerger, "merge_predicts", merge_predicts)
        setattr(Operation, "_predict", predict_operation)
        setattr(Operation, "predict", predict)
        setattr(Operation, "predict_for_fit", predict_for_fit)
        setattr(TSDataMerger, 'postprocess_predicts', postprocess_predicts)

        # setattr(F1, "metric", metric_f1)
        # setattr(Accuracy, "metric", metric_acc)

        setattr(LaggedImplementation,
                '_update_column_types', update_column_types)
        setattr(LaggedImplementation, 'transform', transform_lagged)
        setattr(LaggedImplementation, 'transform_for_fit',
                transform_lagged_for_fit)
        setattr(TsSmoothingImplementation, 'transform', transform_smoothing)

        # class_rules.append(has_no_data_flow_conflicts_in_industrial_pipeline)
        MutationStrengthEnum = MutationStrengthEnumIndustrial
        return OperationTypesRepository

    def __enter__(self):
        """
        Switching to industrial models
        """
        OperationTypesRepository.__repository_dict__.update(
            {'data_operation': {'file': self.industrial_data_operation_path,
                                'initialized_repo': True,
                                'default_tags': []}})

        OperationTypesRepository.assign_repo(
            'data_operation', self.industrial_data_operation_path)

        OperationTypesRepository.__repository_dict__.update(
            {'model': {'file': self.industrial_model_path,
                       'initialized_repo': True,
                       'default_tags': []}})
        OperationTypesRepository.assign_repo(
            'model', self.industrial_model_path)

        setattr(PipelineSearchSpace, "get_parameters_dict",
                get_industrial_search_space)
        setattr(ApiComposer, "_get_default_mutations",
                _get_default_industrial_mutations)
        class_rules.append(has_no_data_flow_conflicts_in_industrial_pipeline)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Switching to fedot models.
        """
        OperationTypesRepository.__repository_dict__.update(
            {'data_operation': {'file': self.base_data_operation_path,
                                'initialized_repo': None,
                                'default_tags': [
                                    OperationTypesRepository.DEFAULT_DATA_OPERATION_TAGS]}})
        OperationTypesRepository.assign_repo(
            'data_operation', self.base_data_operation_path)

        OperationTypesRepository.__repository_dict__.update(
            {'model': {'file': self.base_model_path,
                       'initialized_repo': None,
                       'default_tags': []}})
        OperationTypesRepository.assign_repo('model', self.base_model_path)
