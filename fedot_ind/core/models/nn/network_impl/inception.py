from typing import Optional

from fastai.torch_core import Module
from fastcore.meta import delegates
from fedot.core.operations.operation_parameters import OperationParameters
from torch import nn, optim

from fedot_ind.core.architecture.settings.computational import default_device
from fedot_ind.core.models.nn.network_impl.base_nn_model import BaseNeuralModel
from fedot_ind.core.models.nn.network_modules.layers.pooling_layers import GAP1d
from fedot_ind.core.models.nn.network_modules.layers.special import InceptionBlock, InceptionModule
from fedot_ind.core.repository.constanst_repository import CROSS_ENTROPY, MULTI_CLASS_CROSS_ENTROPY, RMSE


@delegates(InceptionModule.__init__)
class InceptionTime(Module):
    def __init__(self,
                 input_dim,
                 output_dim,
                 seq_len=None,
                 number_of_filters=32,
                 nb_filters=None,
                 **kwargs):
        if number_of_filters is None:
            number_of_filters = nb_filters
        self.inception_block = InceptionBlock(
            input_dim, number_of_filters, **kwargs)
        self.gap = GAP1d(1)
        self.fc = nn.Linear(number_of_filters * 4, output_dim)

    def forward(self, x):
        x = self.inception_block(x)
        x = self.gap(x)
        x = self.fc(x)
        return x


class InceptionTimeModel(BaseNeuralModel):
    """Class responsible for InceptionTime model implementation.

    Attributes:
        self.num_features: int, the number of features.

    Example:
        To use this operation you can create pipeline as follows::
            from fedot.core.pipelines.pipeline_builder import PipelineBuilder
            from examples.fedot.fedot_ex import init_input_data
            from fedot_ind.tools.loader import DataLoader
            from fedot_ind.core.repository.initializer_industrial_models import IndustrialModels
            train_data, test_data = DataLoader(dataset_name='Lightning7').load_data()
            input_data = init_input_data(train_data[0], train_data[1])
            val_data = init_input_data(test_data[0], test_data[1])
            with IndustrialModels():
                pipeline = PipelineBuilder().add_node('inception_model', params={'epochs': 100,
                                                                                 'batch_size': 10}).build()
                pipeline.fit(input_data)
                target = pipeline.predict(val_data).predict
                metric = evaluate_metric(target=test_data[1], prediction=target)

    """

    def __init__(self, params: Optional[OperationParameters] = {}):
        super().__init__(params)
        self.num_classes = params.get('num_classes', 1)

    def __repr__(self):
        return "InceptionNN"

    def _init_model(self, ts):
        self.model = InceptionTime(input_dim=ts.features.shape[1],
                                   output_dim=self.num_classes).to(default_device())
        self.model_for_inference = InceptionTime(input_dim=ts.features.shape[1],
                                                 output_dim=self.num_classes)
        self._evaluate_num_of_epochs(ts)
        optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)
        if ts.task.task_type == 'classification':
            if ts.num_classes == 2:
                loss_fn = CROSS_ENTROPY
            else:
                loss_fn = MULTI_CLASS_CROSS_ENTROPY
        else:
            loss_fn = RMSE
        return loss_fn, optimizer
