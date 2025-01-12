from copy import copy
from typing import List, Iterable, Union, Optional

import pandas as pd
from fedot.core.operations.evaluation.operation_implementations.data_operations.ts_transformations import \
    transform_features_and_target_into_lagged
from fedot.core.repository.dataset_types import DataTypesEnum
from fedot.preprocessing.data_types import TYPE_TO_ID

from fedot_ind.core.architecture.settings.computational import backend_methods as np
from fedot.core.operations.operation_parameters import OperationParameters
from fedot.core.data.array_utilities import atleast_4d
from fedot.core.data.data import InputData, OutputData

from fedot_ind.core.architecture.preprocessing.data_convertor import NumpyConverter


def postprocess_predicts(self, merged_predicts: np.array) -> np.array:
    """ Post-process merged predictions (e.g. reshape). """
    return merged_predicts


def transform_lagged(self, input_data: InputData):
    train_data = copy(input_data)
    forecast_length = train_data.task.task_params.forecast_length

    # Correct window size parameter
    self._check_and_correct_window_size(train_data.features, forecast_length)
    window_size = self.window_size

    new_idx, transformed_cols, new_target = transform_features_and_target_into_lagged(train_data,
                                                                                      forecast_length,
                                                                                      window_size)

    # Update target for Input Data
    train_data.target = new_target
    train_data.idx = new_idx
    output_data = self._convert_to_output(train_data,
                                          transformed_cols,
                                          data_type=DataTypesEnum.image)
    return output_data


def transform_smoothing(self, input_data: InputData) -> OutputData:
    """Method for smoothing time series

    Args:
        input_data: data with features, target and ids to process

    Returns:
        output data with smoothed time series
    """

    source_ts = input_data.features
    if input_data.data_type == DataTypesEnum.multi_ts:
        full_smoothed_ts = []
        for ts_n in range(source_ts.shape[1]):
            ts = pd.Series(source_ts[:, ts_n])
            smoothed_ts = self._apply_smoothing_to_series(ts)
            full_smoothed_ts.append(smoothed_ts)
        output_data = self._convert_to_output(input_data,
                                              np.array(full_smoothed_ts).T,
                                              data_type=input_data.data_type)
    else:
        source_ts = pd.Series(input_data.features.flatten())
        smoothed_ts = np.ravel(self._apply_smoothing_to_series(source_ts))
        output_data = self._convert_to_output(input_data,
                                              smoothed_ts,
                                              data_type=input_data.data_type)

    return output_data


def transform_lagged_for_fit(self, input_data: InputData) -> OutputData:
    """Method for transformation of time series to lagged form for fit stage

    Args:
        input_data: data with features, target and ids to process

    Returns:
        output data with transformed features table
    """
    input_data.features = input_data.features.squeeze()
    new_input_data = copy(input_data)
    forecast_length = new_input_data.task.task_params.forecast_length

    # Correct window size parameter
    self._check_and_correct_window_size(
        new_input_data.features, forecast_length)
    window_size = self.window_size
    new_idx, transformed_cols, new_target = transform_features_and_target_into_lagged(
        input_data,
        forecast_length,
        window_size)

    # Update target for Input Data
    new_input_data.target = new_target
    new_input_data.idx = new_idx
    output_data = self._convert_to_output(new_input_data,
                                          transformed_cols,
                                          data_type=DataTypesEnum.image)
    return output_data


def update_column_types(self, output_data: OutputData):
    """Update column types after lagged transformation. All features becomes ``float``
    """

    _, features_n_cols, _ = output_data.predict.shape
    feature_type_ids = np.array([TYPE_TO_ID[float]] * features_n_cols)
    col_type_ids = {'features': feature_type_ids}

    if output_data.target is not None and len(output_data.target.shape) > 1:
        _, target_n_cols = output_data.target.shape
        target_type_ids = np.array([TYPE_TO_ID[float]] * target_n_cols)
        col_type_ids['target'] = target_type_ids
    output_data.supplementary_data.col_type_ids = col_type_ids


def preprocess_predicts(*args) -> List[np.array]:
    predicts = args[1]
    if len(predicts[0].shape) <= 3:
        return predicts
    else:
        reshaped_predicts = list(map(atleast_4d, predicts))

        # And check image sizes
        img_wh = [predict.shape[1:3] for predict in reshaped_predicts]
        # Can merge only images of the same size
        invalid_sizes = len(set(img_wh)) > 1
        if invalid_sizes:
            raise ValueError(
                "Can't merge images of different sizes: " + str(img_wh))
        return reshaped_predicts


def merge_predicts(*args) -> np.array:
    predicts = args[1]

    predicts = [NumpyConverter(
        data=prediction).convert_to_torch_format() for prediction in predicts]
    sample_shape, channel_shape, elem_shape = [
        (x.shape[0], x.shape[1], x.shape[2]) for x in predicts][0]

    sample_wise_concat = [x.shape[0] == sample_shape for x in predicts]
    chanel_concat = [x.shape[1] == channel_shape for x in predicts]
    element_wise_concat = [x.shape[2] == elem_shape for x in predicts]

    channel_match = all(chanel_concat)
    element_match = all(element_wise_concat)
    sample_match = all(sample_wise_concat)

    if sample_match and element_match:
        return np.concatenate(predicts, axis=1)
    elif sample_match and channel_match:
        return np.concatenate(predicts, axis=2)
    else:
        prediction_2d = np.concatenate(
            [x.reshape(x.shape[0], x.shape[1] * x.shape[2]) for x in predicts], axis=1)
        return prediction_2d.reshape(prediction_2d.shape[0], 1, prediction_2d.shape[1])


def predict_operation(self, fitted_operation, data: InputData, params: Optional[OperationParameters] = None,
                      output_mode: str = 'default', is_fit_stage: bool = False):
    is_main_target = data.supplementary_data.is_main_target
    data_flow_length = data.supplementary_data.data_flow_length
    self._init(data.task, output_mode=output_mode, params=params,
               n_samples_data=data.features.shape[0])

    if is_fit_stage:
        prediction = self._eval_strategy.predict_for_fit(
            trained_operation=fitted_operation,
            predict_data=data,
            output_mode=output_mode)
    else:
        prediction = self._eval_strategy.predict(
            trained_operation=fitted_operation,
            predict_data=data,
            output_mode=output_mode)
    prediction = self.assign_tabular_column_types(prediction, output_mode)

    # any inplace operations here are dangerous!
    if is_main_target is False:
        prediction.supplementary_data.is_main_target = is_main_target

    prediction.supplementary_data.data_flow_length = data_flow_length
    return prediction


def predict(self, fitted_operation, data: InputData, params: Optional[Union[OperationParameters, dict]] = None,
            output_mode: str = 'labels'):
    """This method is used for defining and running of the evaluation strategy
    to predict with the data provided

    Args:
        fitted_operation: trained operation object
        data: data used for prediction
        params: hyperparameters for operation
        output_mode: string with information about output of operation,
        for example, is the operation predict probabilities or class labels
    """
    return self._predict(fitted_operation, data, params, output_mode, is_fit_stage=False)


def predict_for_fit(self, fitted_operation, data: InputData, params: Optional[OperationParameters] = None,
                    output_mode: str = 'default'):
    """This method is used for defining and running of the evaluation strategy
    to predict with the data provided during fit stage

    Args:
        fitted_operation: trained operation object
        data: data used for prediction
        params: hyperparameters for operation
        output_mode: string with information about output of operation,
            for example, is the operation predict probabilities or class labels
    """
    return self._predict(fitted_operation, data, params, output_mode, is_fit_stage=True)
