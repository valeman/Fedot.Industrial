import copy
import os
import yaml
import logging
from typing import Dict
from cases.run.utils import read_tsv
from cases.run.QuantileRunner import StatsRunner
from cases.run.SSARunner import SSARunner
from cases.run.SignalRunner import SignalRunner
from cases.run.TopologicalRunner import TopologicalRunner
from core.operation.utils.utils import project_path
from cases.run.ts_clf import TimeSeriesClf

class Industrial:
    """ Class-support for performing examples for tasks (read yaml configs, create data folders and log files)"""

    def __init__(self):
        logger = logging.getLogger('Experiment logger')
        logger.setLevel(logging.INFO)

        # create console handler and set level to debug
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # add formatter to ch
        ch.setFormatter(formatter)

        # add ch to logger
        logger.addHandler(ch)

        self.logger = logger

        self.feature_generator_dict = {
            'quantile': StatsRunner,
            'window_quantile': StatsRunner,
            'wavelet': SignalRunner,
            'spectral': SSARunner,
            'window_spectral': SSARunner,
            'topological': TopologicalRunner}


    def read_yaml_config(self, config_name: str) -> Dict:
        """ Read yaml config from './experiments/configs/config_name' directory as dictionary file
            :param config_name: yaml-config name
            :return: yaml config
        """
        path = os.path.join(project_path(), 'cases', 'config', config_name)
        with open(path, "r") as input_stream:
            self.config_dict = yaml.safe_load(input_stream)
            self.config_dict['logger'] = self.logger
            self.logger.info(f"schema ready: {self.config_dict}")


    def run_experiment(self,config_name):
        self.read_yaml_config(config_name)
        experiment_dict = copy.deepcopy(self.config_dict)

        for key in self.config_dict['dataset_list'].keys():
            experiment_dict['dataset_list'][key] = {i:read_tsv(i) for i in experiment_dict['dataset_list'][key]}

        experiment_dict['feature_generator'].clear()
        experiment_dict['feature_generator'] = dict()
        for idx,feature_generator in enumerate(self.config_dict['feature_generator']):
            experiment_dict['feature_generator'].update({feature_generator: self.feature_generator_dict[feature_generator]
                (fedot_params=experiment_dict['fedot_params'],**experiment_dict['feature_generator_params'][feature_generator])})

        classificator = TimeSeriesClf(feature_generator_dict=experiment_dict['feature_generator'],
                      model_hyperparams=experiment_dict['fedot_params'])
        _ = 1