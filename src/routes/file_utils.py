import abc
import hashlib
import logging
import os
import pathlib
import shutil
from io import BytesIO

from typing import Tuple, Optional
from typing.io import IO

import boto3
from urllib import request

from boto3_type_annotations.s3.client import Client as S3Client

logger = logging.getLogger(__name__)

LOCAL_FILES_DIRECTORY = os.environ.get('LOCAL_FILES_DIRECTORY') or '/tmp/scihive-papers'
EXTERNAL_BASE_URL = os.environ.get('EXTERNAL_BASE_URL') or 'http://localhost:5000'

S3_KEY = os.environ.get('S3_KEY')
S3_SECRET = os.environ.get('S3_SECRET')
S3_BUCKET = os.environ.get('S3_BUCKET')

s3_available = S3_KEY and S3_SECRET and S3_BUCKET

if not s3_available:
    logger.warn(
        f'S3 env vars are missing - Key: {bool(S3_KEY)}, Secret: {bool(S3_SECRET)}, Bucket: {bool(S3_BUCKET)}')

s3_client_instance: Optional[S3Client] = boto3.client(
    's3',
    aws_access_key_id=S3_KEY,
    aws_secret_access_key=S3_SECRET
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

    def __init__(self, s3_client: S3Client, s3_bucket: str, external_base_url: str, prefix: str) -> None:
        self._s3_client = s3_client
        self._s3_bucket = s3_bucket
        self._external_base_url = external_base_url
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
        return f'{self._external_base_url}/{self._prefix}/{path}'

    def save_file(self, filename: str, content: IO) -> None:
        upload_to = f'{self._prefix}/{filename}'
        self._s3_client.upload_fileobj(content, self._s3_bucket, upload_to)
        logger.info(f'File was uploaded to S3 - {upload_to}')


class LocalFileAccessProvider(FileAccessProvider):

    def __init__(self, base_path: str, external_base_url: str) -> None:
        self._base_path = base_path
        self._external_base_url = external_base_url
        # make sure the directory exists
        pathlib.Path(base_path).mkdir(parents=True, exist_ok=True)

    def exists(self, path: str) -> bool:
        return os.path.isfile(f'{self._base_path}/{path}')

    def get_link_to_file(self, path: str) -> str:
        return f'{self._external_base_url}/paper/files/{path}'

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
        file_hash = self.calc_hash(content)
        filename = f'{file_hash}.pdf'
        pdf_link = self._file_access_provider.get_link_to_file(filename)
        if not self._file_access_provider.exists(filename):
            self._file_access_provider.save_file(filename, BytesIO(content))

        return content, file_hash, pdf_link

    @staticmethod
    def calc_hash(content):
        return hashlib.md5(content).hexdigest()


def get_uploader():
    file_access_provider: FileAccessProvider
    if s3_available:
        file_access_provider = S3FileAccessProvider(
            s3_client=s3_client_instance,
            s3_bucket=S3_BUCKET,
            external_base_url=EXTERNAL_BASE_URL,
            prefix='papers'
        )
    else:
        logger.warning('S3 info is missing, using local file system instead')
        file_access_provider = LocalFileAccessProvider(
            base_path=LOCAL_FILES_DIRECTORY,
            external_base_url=EXTERNAL_BASE_URL
        )

    return FileUploader(file_access_provider=file_access_provider)
