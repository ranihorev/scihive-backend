import abc
import hashlib
import logging
import os
import pathlib
import shutil

from typing import Tuple, Optional
from typing.io import IO

import boto3
from urllib import request

from boto3_type_annotations.s3.client import Client as S3Client
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

LOCAL_FILES_DIRECTORY = os.environ.get('LOCAL_FILES_DIRECTORY') or '/tmp/scihive-papers'
EXTERNAL_BASE_ADDRESS = os.environ.get('EXTERNAL_BASE_ADDRESS') or 'http://localhost:5000'

s3_key = os.environ.get('S3_KEY')
s3_secret = os.environ.get('S3_SECRET')
s3_bucket = os.environ.get('S3_BUCKET_NAME')

s3_available = s3_key and s3_secret and s3_bucket
s3_client: Optional[S3Client] = boto3.client(
    's3',
    aws_access_key_id=s3_key,
    aws_secret_access_key=s3_secret
) if s3_available else None


class FileAccessProvider(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def exists(self, path: str) -> bool:
        pass

    @abc.abstractmethod
    def get_link_to_file(self, path: str) -> str:
        pass

    @abc.abstractmethod
    def save_file(self, filename: str, content: IO) -> None:
        pass


class S3FileAccessProvider(FileAccessProvider):

    def __init__(self, s3_client: S3Client, s3_bucket: str, prefix: str) -> None:
        self._s3_client = s3_client
        self._s3_bucket = s3_bucket
        self._prefix = prefix

    def exists(self, path: str) -> bool:
        prefixed_key = f'{self._prefix}/{path}'
        response = self._s3_client.list_objects_v2(
            Bucket=self._s3_bucket,
            Prefix=prefixed_key,
        )
        for obj in response.get('Contents', []):
            if obj['Key'] == prefixed_key:
                return True
        return False

    def get_link_to_file(self, path: str) -> str:
        return f'https://{self._s3_bucket}.s3.amazonaws.com/{self._prefix}/{path}'

    def save_file(self, filename: str, content: IO) -> None:
        self._s3_client.upload_fileobj(content, self._s3_bucket, f'{self._prefix}/{filename}')


class LocalFileAccessProvider(FileAccessProvider):

    def __init__(self, base_path: str, external_base_address: str) -> None:
        self._base_path = base_path
        self._external_base_address = external_base_address
        # make sure the directory exists
        pathlib.Path(base_path).mkdir(parents=True, exist_ok=True)

    def exists(self, path: str) -> bool:
        return os.path.isfile(f'{self._base_path}/{path}')

    def get_link_to_file(self, path: str) -> str:
        return f'{self._external_base_address}/paper/files/{path}'

    def save_file(self, filename: str, content: IO) -> None:
        with open(f'{self._base_path}/{filename}', 'wb') as output:
            shutil.copyfileobj(content, output)


class FileUploader:

    def __init__(self, file_access_provider: FileAccessProvider) -> None:
        self._file_access_provider = file_access_provider

    def upload_from_arxiv(self, url: str) -> str:
        filename = url.split('/')[-1]
        if self._file_access_provider.exists(filename):
            return self._file_access_provider.get_link_to_file(filename)

        self._file_access_provider.save_file(filename, request.urlopen(url))
        return self._file_access_provider.get_link_to_file(filename)

    def upload_from_file(self, file_stream: IO) -> Tuple[bytes, str, str]:
        content = file_stream.read()
        file_hash = self._calc_hash(content)
        filename = f'{file_hash}.pdf'
        pdf_link = self._file_access_provider.get_link_to_file(filename)
        if not self._file_access_provider.exists(filename):
            file_stream.seek(0)
            self._file_access_provider.save_file(filename, file_stream)

        return content, file_hash, pdf_link

    @staticmethod
    def _calc_hash(content):
        return hashlib.md5(content).hexdigest()


def get_uploader():
    file_access_provider: FileAccessProvider
    if s3_available:
        file_access_provider = S3FileAccessProvider(
            s3_client=s3_client,
            s3_bucket=s3_bucket,
            prefix='papers'
        )
    else:
        logger.warning('S3 info is missing missing, using local file system instead')
        file_access_provider = LocalFileAccessProvider(LOCAL_FILES_DIRECTORY, EXTERNAL_BASE_ADDRESS)

    return FileUploader(file_access_provider=file_access_provider)
