from src.scripts.segmentation.preprocess import Preprocessor
import sys
from datetime import datetime

import torch
from torch.utils.data import ConcatDataset

from src.scripts.segmentation import data


def build_dataloaders(config):
    dataset_class = data.__dict__[config.dataset.name]
    dataloaders = _create_dataloaders(config, dataset_class, "train")  # type: ignore

    mapping_assignment_dataloader = _create_mapping_loader(
        config,
        dataset_class,  # type: ignore
        config.dataset.partitions.map_assign,
        "test",
    )

    mapping_test_dataloader = _create_mapping_loader(
        config,
        dataset_class,  # type: ignore
        config.dataset.partitions.map_test,
        "test",
    )

    return dataloaders, mapping_assignment_dataloader, mapping_test_dataloader


def _create_dataloaders(config, dataset_class, purpose):
    # unlike in clustering, each dataloader here returns pairs of images - we
    # need the matrix relation between them
    dataloaders = []
    do_shuffle = config.dataset.num_dataloaders == 1
    count = config.dataset.num_dataloaders
    for d_i in range(count):
        print("Creating dataloader {:d}/{:d}".format(d_i + 1, count))
        preprocessor = Preprocessor(config, purpose)
        train_dataloader = torch.utils.data.DataLoader(
            _create_dataset(config, dataset_class, purpose, preprocessor),
            batch_size=config.dataloader_batch_size,
            shuffle=do_shuffle,
            num_workers=0,
            drop_last=False,
        )
        if d_i > 0:
            assert len(train_dataloader) == len(dataloaders[d_i - 1])
        dataloaders.append(train_dataloader)

    print(("Number of batches per epoch: {:d}".format(len(dataloaders[0]))))
    return dataloaders


def _create_mapping_loader(config, dataset_class, partitions, purpose):
    preprocessor = Preprocessor(config, purpose)
    return torch.utils.data.DataLoader(
        _create_dataset(config, dataset_class, purpose, preprocessor),
        batch_size=config.dataset.batch_size,
        # full batch
        shuffle=False,
        # no point since not trained on
        num_workers=0,
        drop_last=False,
    )


def _create_dataset(config, dataset_class, purpose, preprocessor):
    train_images = [
        dataset_class(
            **{
                "config": config,
                "split": partition,
                "purpose": purpose,
                "preload": False,
                "preprocessor": preprocessor,
            }
        )
        for partition in config.dataset.partitions.train
    ]
    return ConcatDataset(train_images)
