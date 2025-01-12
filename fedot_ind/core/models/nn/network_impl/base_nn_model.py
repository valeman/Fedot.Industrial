import os
from typing import Optional

import torch
import torch.nn.functional as F
from fedot.core.data.data import InputData, OutputData
from fedot.core.data.data_split import _are_stratification_allowed, train_test_data_setup
from fedot.core.operations.operation_parameters import OperationParameters
from fedot.core.repository.dataset_types import DataTypesEnum
from torch import Tensor
from torch.optim import lr_scheduler

from fedot_ind.core.architecture.abstraction.decorators import convert_inputdata_to_torch_dataset, \
    convert_to_3d_torch_array, fedot_data_type
from fedot_ind.core.architecture.settings.computational import backend_methods as np
from fedot_ind.core.architecture.settings.computational import default_device
from fedot_ind.core.models.nn.network_modules.layers.special import adjust_learning_rate, EarlyStopping


class BaseNeuralModel:
    """Class responsible for NN model implementation.

    Attributes:
        self.num_features: int, the number of features.

    Example:
        To use this operation you can create pipeline as follows::
            from fedot.core.pipelines.pipeline_builder import PipelineBuilder
            from examples.fedot.fedot_ex import init_input_data
            from fedot_ind.tools.loader import DataLoader
            from fedot_ind.core.repository.initializer_industrial_models import IndustrialModels

            train_data, test_data = DataLoader(dataset_name='Ham').load_data()
            with IndustrialModels():
                pipeline = PipelineBuilder().add_node('minirocket_features').add_node(
                    'rf').build()
                input_data = init_input_data(train_data[0], train_data[1])
                pipeline.fit(input_data)
                features = pipeline.predict(input_data)
                print(features)
    """

    def __init__(self, params: Optional[OperationParameters] = {}):
        self.num_classes = params.get('num_classes', None)
        self.epochs = params.get('epochs', 30)
        self.batch_size = params.get('batch_size', 16)
        self.activation = params.get('activation', 'ReLU')
        self.learning_rate = 0.001

        print(
            f'Epoch: {self.epochs}, Batch Size: {self.batch_size}, Activation_function: {self.activation}')

    @convert_inputdata_to_torch_dataset
    def _create_dataset(self, ts: InputData):
        return ts

    def _init_model(self, ts):
        self.model = None
        return

    def _evaluate_num_of_epochs(self, ts):
        min_num_epochs = min(100, round(ts.features.shape[0] * 1.5))
        if self.epochs is None:
            self.epochs = min_num_epochs
        else:
            self.epochs = max(min_num_epochs, self.epochs)

    def _convert_predict(self, pred, output_mode):
        pred = F.softmax(pred, dim=1)

        if output_mode == 'labels':
            y_pred = torch.argmax(pred, dim=1)
        else:
            y_pred = pred.cpu().detach().numpy()

        if self.label_encoder is not None and output_mode is 'labels':
            y_pred = self.label_encoder.inverse_transform(y_pred)

        predict = OutputData(
            idx=np.arange(len(y_pred)),
            task=self.task_type,
            predict=y_pred,
            target=self.target,
            data_type=DataTypesEnum.table)
        return predict

    def _prepare_data(self, ts, split_data: bool = True):

        stratify = _are_stratification_allowed(ts, 0.7)

        if split_data and stratify:
            train_data, val_data = train_test_data_setup(
                ts, stratify=stratify, shuffle_flag=True, split_ratio=0.7)
            train_dataset = self._create_dataset(train_data)
            val_dataset = self._create_dataset(val_data)
        else:
            train_dataset = self._create_dataset(ts)
            val_dataset = None

        train_loader = torch.utils.data.DataLoader(
            train_dataset, batch_size=self.batch_size, shuffle=True)

        if val_dataset is None:
            val_loader = val_dataset
        else:
            val_loader = torch.utils.data.DataLoader(
                val_dataset, batch_size=self.batch_size, shuffle=True)

        self.num_classes = train_dataset.classes
        self.label_encoder = train_dataset.label_encoder
        return train_loader, val_loader

    def _save_and_clear_cache(self):
        prefix = f'model_{self.__repr__()}_activation_{self.activation}_epochs_{self.epochs}_bs_{self.batch_size}.pt'
        torch.save(self.model.state_dict(), prefix)
        del self.model
        with torch.no_grad():
            torch.cuda.empty_cache()
        self.model = self.model_for_inference.to(torch.device('cpu'))
        self.model.load_state_dict(torch.load(
            prefix, map_location=torch.device('cpu')))
        os.remove(prefix)

    def _train_loop(self, train_loader, val_loader, loss_fn, optimizer):
        early_stopping = EarlyStopping()
        scheduler = lr_scheduler.OneCycleLR(optimizer=optimizer,
                                            steps_per_epoch=len(train_loader),
                                            epochs=self.epochs,
                                            max_lr=self.learning_rate)
        if val_loader is None:
            print('Not enough class samples for validation')

        for epoch in range(1, self.epochs + 1):
            training_loss = 0.0
            valid_loss = 0.0
            self.model.train()
            for batch in train_loader:
                optimizer.zero_grad()
                inputs, targets = batch
                output = self.model(inputs)
                loss = loss_fn(output, targets.float())
                loss.backward()
                optimizer.step()
                training_loss += loss.data.item() * inputs.size(0)

            training_loss /= len(train_loader.dataset)
            print('Epoch: {}, Training Loss: {:.2f}'.format(epoch, training_loss))

            if val_loader is not None:
                self.model.eval()
                for batch in val_loader:
                    inputs, targets = batch
                    output = self.model(inputs)
                    loss = loss_fn(output, targets.float())
                    valid_loss += loss.data.item() * inputs.size(0)
                valid_loss /= len(val_loader.dataset)
                print('Epoch: {},Validation Loss: {:.2f}'.format(epoch,
                                                                 valid_loss))
            early_stopping(training_loss, self.model, './')
            adjust_learning_rate(optimizer, scheduler,
                                 epoch + 1, self.learning_rate, printout=False)
            scheduler.step()

            if early_stopping.early_stop:
                print("Early stopping")
                break
            print('Updating learning rate to {}'.format(
                scheduler.get_last_lr()[0]))

    @convert_to_3d_torch_array
    def _fit_model(self, ts: InputData, split_data: bool = False):
        self._train_loop(*self._prepare_data(ts, split_data),
                         *self._init_model(ts))

    @convert_to_3d_torch_array
    def _predict_model(self, x_test, output_mode: str = 'default'):
        self.model.eval()
        x_test = Tensor(x_test).to(default_device('cpu'))
        pred = self.model(x_test)
        return self._convert_predict(pred, output_mode)

    def fit(self,
            input_data: InputData):
        """
        Method for feature generation for all series
        """
        self.num_classes = input_data.num_classes
        self.target = input_data.target
        self.task_type = input_data.task
        self._fit_model(input_data)
        self._save_and_clear_cache()

    @fedot_data_type
    def predict(self,
                input_data: InputData, output_mode: str = 'default') -> np.array:
        """
        Method for feature generation for all series
        """
        return self._predict_model(input_data, output_mode)

    @fedot_data_type
    def predict_for_fit(self,
                        input_data: InputData, output_mode: str = 'default') -> np.array:
        """
        Method for feature generation for all series
        """
        return self._predict_model(input_data, output_mode)
