import pytest
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from agents.data_parser import get_thread_session

def test_retry_configuration():
    session = get_thread_session()
    adapter = session.adapters.get("https://")
    assert isinstance(adapter, HTTPAdapter)
    
    retry = adapter.max_retries
    assert isinstance(retry, Retry)

    # Verifikasi status codes yang wajib di-retry
    retryable_statuses = {429, 500, 502, 503, 504}
    for status in retryable_statuses:
        assert status in retry.status_forcelist

    # Verifikasi status codes yang TIDAK boleh di-retry
    non_retryable_statuses = {400, 401, 403, 404}
    for status in non_retryable_statuses:
        assert status not in retry.status_forcelist
