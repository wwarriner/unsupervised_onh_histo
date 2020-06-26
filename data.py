from pathlib import Path, PurePath
from typing import List, Union, Dict, Any, Optional

from PIL import Image  # TODO use image utils
import torch
import numpy as np

from inc.python_image_utilities.image_util import patchify, unpatchify
import preprocessing as pre

PathLike = Union[str, Path, PurePath]


class ImageFolderDataset(torch.utils.data.Dataset):
    def __init__(
        self,
        image_folder: PathLike,
        preprocessor: pre.ImagePreprocessor,
        extensions: List[str],
        label_folder: Optional[PathLike] = None,
    ):
        assert 1 <= len(extensions)
        image_files = self._build_files(image_folder, extensions)
        assert 1 <= len(image_files)
        if label_folder is not None:
            label_files = self._build_files(label_folder, extensions)
            assert 1 <= len(label_files)
            assert len(label_files) == len(image_files)
            assert self._check_labels(image_files, label_files)
        else:
            label_files = None
        self._pre = preprocessor
        self._image_files = image_files
        self._label_files = label_files

    def __len__(self):
        return len(self._image_files)

    def __getitem__(self, index):
        image_file_path = self._image_files[index]
        image = self._load_image(image_file_path)
        data = {"image": image, "file_path": str(image_file_path)}
        if self._label_files is not None:
            label_file_path = self._label_files[index]
            label = self._load_label(label_file_path)
            assert label.ndim == 2
            assert label.shape[:2] == image.shape[:2]
            data["label"] = label
        out = self._pre.apply(**data)
        for k, v in out.items():
            assert k is not None
            assert v is not None
        return out

    def _load_image(self, file_path):
        image = Image.open(str(file_path))
        return np.asarray(image).astype(np.uint8)

    def _load_label(self, file_path: PathLike):
        image = Image.open(str(file_path))
        label = np.asarray(image).astype(np.int32)
        label[label == 255] = -1
        return label

    @staticmethod
    def _build_files(folder: PathLike, extensions: List[str]):
        files = []
        for extension in extensions:
            glob = "**/*{:s}".format(extension)
            files.extend(list(Path(folder).glob(glob)))
        files = sorted(files, key=ImageFolderDataset._get_file_key)
        return files

    @staticmethod
    def _check_labels(train_files: List[PathLike], label_files: List[PathLike]):
        matches = True
        for train, label in zip(train_files, label_files):
            if PurePath(train).stem != PurePath(label).stem:
                matches = False
                break
        return matches

    @staticmethod
    def _get_file_key(file_path: PathLike):
        path = PurePath(file_path)
        parents = list(reversed(path.parents))
        return tuple([path.stem, *parents])


class TrainDataLoader(torch.utils.data.DataLoader):
    def __init__(self, dataset: ImageFolderDataset, batch_size: int, shuffle: bool):
        super(TrainDataLoader, self).__init__(
            dataset=dataset,
            batch_size=batch_size,
            shuffle=shuffle,
            num_workers=0,
            drop_last=False,
        )


class TestDataLoader(torch.utils.data.DataLoader):
    def __init__(self, dataset: ImageFolderDataset, batch_size: int):
        super(TestDataLoader, self).__init__(
            dataset=dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=0,
            drop_last=False,
        )


class EvalDataset(ImageFolderDataset):
    def __init__(
        self,
        eval_folder: PathLike,
        preprocessor: pre.EvalImagePreprocessor,
        input_size: int,
        extensions: List[str] = [".png"],
    ):
        super(EvalDataset, self).__init__(
            image_folder=eval_folder, preprocessor=preprocessor, extensions=extensions
        )
        self._input_size = input_size

    def __getitem__(self, index):
        out = super(EvalDataset, self).__getitem__(index)
        image = out["image"]
        (patches, patch_count, out_padding) = patchify(
            image, patch_shape=self._input_size
        )
        t = torch.zeros(patches.shape).cuda()
        for i, p in enumerate(patches):
            data = self._pre.apply(image=p)
            t[i, ...] = data["image"]
        out["image"] = t
        out["patch_count"] = patch_count
        out["padding"] = out_padding
        for k, v in out.items():
            assert k is not None
            assert v is not None
        return out

    def reassemble(self, image: np.ndarray, patch_count, padding, **kwargs):
        return {
            "image": unpatchify(
                patches=image, patch_counts=patch_count, padding=padding
            ),
            **kwargs,
        }


class EvalDataLoader(torch.utils.data.DataLoader):
    def __init__(self, dataset: EvalDataset):
        super(EvalDataLoader, self).__init__(
            dataset=dataset, batch_size=1, shuffle=False, num_workers=0, drop_last=False
        )

    def reassemble(self, data: Dict[str, Any]):
        return self.dataset.reassemble(data)