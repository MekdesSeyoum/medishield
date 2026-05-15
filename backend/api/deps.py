from db.case_store import CaseStore
from minio import Minio
from storage.minio_client import get_minio


def get_case_store() -> CaseStore:
    return CaseStore()


def get_minio_client() -> Minio:
    return get_minio()
