import os

from torchvision.transforms import Compose, Resize, ToTensor

from fedot_ind.api.main import FedotIndustrial
from fedot_ind.api.utils.path_lib import PROJECT_PATH

DATASETS_PATH = os.path.abspath(PROJECT_PATH + '/tests/data/datasets')


def test_image_classification(tmp_path):
    fed = FedotIndustrial(task='image_classification', num_classes=3)
    fed.fit(
        dataset_path=os.path.join(DATASETS_PATH, 'Agricultural/train'),
        transform=Compose([ToTensor(), Resize((256, 256))]),
        num_epochs=2,
    )
    fed.predict(
        data_path=os.path.join(DATASETS_PATH, 'Agricultural/val'),
        transform=Compose([ToTensor(), Resize((256, 256))]),
    )
    fed.predict_proba(
        data_path=os.path.join(DATASETS_PATH, 'Agricultural/val'),
        transform=Compose([ToTensor(), Resize((256, 256))]),
    )
    fed.get_metrics()
    fed.save_metrics()


def test_image_classification_svd(tmp_path):
    fed = FedotIndustrial(
        task='image_classification',
        num_classes=3,
        optimization='svd',
        optimization_params={'energy_thresholds': [0.9]}
    )
    fed.fit(
        dataset_path=os.path.join(DATASETS_PATH, 'Agricultural/train'),
        transform=Compose([ToTensor(), Resize((256, 256))]),
        num_epochs=2,
        finetuning_params={'num_epochs': 1},
    )
    fed.predict(
        data_path=os.path.join(DATASETS_PATH, 'Agricultural/val'),
        transform=Compose([ToTensor(), Resize((256, 256))]),
    )


# def test_object_detection(tmp_path):
#     fed = FedotIndustrial(task='object_detection', num_classes=4)
#     fed.fit(
#         dataset_path=os.path.join(DATASETS_PATH, 'minerals/minerals.yaml'),
#         num_epochs=2,
#     )
#     fed.predict(data_path=os.path.join(DATASETS_PATH, 'minerals/train/images'))
#     fed.predict_proba(data_path=os.path.join(DATASETS_PATH, 'minerals/train/images'))
#     fed.get_metrics()
