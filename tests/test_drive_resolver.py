import pytest
from unittest.mock import MagicMock
from utils.drive_resolver import (
    is_google_drive_url,
    extract_google_file_id,
    extract_google_file_id_and_type,
    get_canonical_drive_url,
    get_direct_download_url,
    classify_drive_response,
    resolve_and_validate_gdrive_url
)

def test_is_google_drive_url():
    assert is_google_drive_url("https://drive.google.com/file/d/ABC123/view") is True
    assert is_google_drive_url("https://drive.google.com/open?id=ABC123") is True
    assert is_google_drive_url("https://drive.google.com/uc?id=ABC123") is True
    assert is_google_drive_url("https://docs.google.com/document/d/DOC123/edit") is True
    assert is_google_drive_url("https://docs.google.com/spreadsheets/d/SHEET123/edit") is True
    assert is_google_drive_url("https://docs.google.com/presentation/d/SLIDE123/edit") is True
    assert is_google_drive_url("https://drive.google.com/drive/folders/FOLDER123") is True
    
    # Non-drive URLs
    assert is_google_drive_url("https://example.com/report.pdf") is False
    assert is_google_drive_url("https://google.com/search?q=test") is False
    assert is_google_drive_url("") is False
    assert is_google_drive_url(None) is False

def test_extract_google_file_id_and_type():
    # 1. Standard File
    file_id, r_type, r_key = extract_google_file_id_and_type("https://drive.google.com/file/d/ABC123_XYZ/view?usp=sharing")
    assert file_id == "ABC123_XYZ"
    assert r_type == "file"
    assert r_key is None

    # 2. Open parameter
    file_id, r_type, r_key = extract_google_file_id_and_type("https://drive.google.com/open?id=OPEN_ID_999")
    assert file_id == "OPEN_ID_999"
    assert r_type == "file"

    # 3. Google Doc
    file_id, r_type, r_key = extract_google_file_id_and_type("https://docs.google.com/document/d/DOC_ID_456/edit#heading=h.123")
    assert file_id == "DOC_ID_456"
    assert r_type == "doc"

    # 4. Google Sheet
    file_id, r_type, r_key = extract_google_file_id_and_type("https://docs.google.com/spreadsheets/d/SHEET_ID_789/edit?gid=0")
    assert file_id == "SHEET_ID_789"
    assert r_type == "sheet"

    # 5. Google Slide
    file_id, r_type, r_key = extract_google_file_id_and_type("https://docs.google.com/presentation/d/SLIDE_ID_101/edit")
    assert file_id == "SLIDE_ID_101"
    assert r_type == "slide"

    # 6. Google Drive Folder
    file_id, r_type, r_key = extract_google_file_id_and_type("https://drive.google.com/drive/folders/FOLDER_ID_555")
    assert file_id == "FOLDER_ID_555"
    assert r_type == "folder"

    # 7. Preserving resourcekey
    file_id, r_type, r_key = extract_google_file_id_and_type("https://drive.google.com/file/d/FILE_KEY_123/view?resourcekey=SEC_KEY_99")
    assert file_id == "FILE_KEY_123"
    assert r_key == "SEC_KEY_99"

def test_get_canonical_drive_url():
    assert get_canonical_drive_url("ABC123", "file") == "https://drive.google.com/file/d/ABC123/view"
    assert get_canonical_drive_url("DOC123", "doc") == "https://docs.google.com/document/d/DOC123/edit"
    assert get_canonical_drive_url("SHEET123", "sheet") == "https://docs.google.com/spreadsheets/d/SHEET123/edit"
    assert get_canonical_drive_url("SLIDE123", "slide") == "https://docs.google.com/presentation/d/SLIDE123/edit"
    assert get_canonical_drive_url("FOLDER123", "folder") == "https://drive.google.com/drive/folders/FOLDER123"
    assert get_canonical_drive_url("ABC123", "file", resource_key="KEY888") == "https://drive.google.com/file/d/ABC123/view?resourcekey=KEY888"

def test_get_direct_download_url():
    # File
    url, is_folder = get_direct_download_url("ABC123", "file", resource_key="RK1")
    assert "drive.google.com/uc?export=download&id=ABC123&resourcekey=RK1" in url
    assert is_folder is False

    # Doc
    url, is_folder = get_direct_download_url("DOC123", "doc")
    assert "docs.google.com/document/d/DOC123/export?format=pdf" in url
    assert is_folder is False

    # Sheet
    url, is_folder = get_direct_download_url("SHEET123", "sheet")
    assert "docs.google.com/spreadsheets/d/SHEET123/export?format=csv" in url
    assert is_folder is False

    # Folder
    url, is_folder = get_direct_download_url("FOLDER123", "folder")
    assert url is None
    assert is_folder is True

def test_classify_drive_response():
    # 1. Accessible normal
    assert classify_drive_response(200, 200, "https://drive.google.com/file/d/123/view", "<html>Normal Drive Viewer</html>") == "accessible"

    # 2. Redirect resolved (303 -> 200)
    assert classify_drive_response(303, 200, "https://drive.google.com/file/d/123/view", "<html>Normal Viewer</html>") == "redirect_resolved"

    # 3. Permission required (Redirected to ServiceLogin or 403)
    assert classify_drive_response(302, 200, "https://accounts.google.com/ServiceLogin?continue=...", "") == "permission_required"
    assert classify_drive_response(200, 403, "https://drive.google.com/file/d/123/view", "") == "permission_required"
    assert classify_drive_response(200, 200, "https://drive.google.com/file/d/123/view", "You need permission to access this file") == "permission_required"

    # 4. Not found (404 or page text)
    assert classify_drive_response(200, 404, "https://drive.google.com/file/d/123/view", "") == "not_found"
    assert classify_drive_response(200, 200, "https://drive.google.com/file/d/123/view", "Maaf, file yang Anda minta tidak ada.") == "not_found"

    # 5. Deleted or unavailable
    assert classify_drive_response(200, 200, "https://drive.google.com/file/d/123/view", "File is in owner's trash") == "deleted_or_unavailable"

    # 6. Rate limited
    assert classify_drive_response(200, 429, "https://drive.google.com/file/d/123/view", "") == "rate_limited"

def test_resolve_and_validate_gdrive_url_mocked():
    # Mock HTTP Session for 303 -> 200 redirect
    mock_session = MagicMock()
    mock_history_item = MagicMock()
    mock_history_item.status_code = 303

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://drive.google.com/file/d/ABC123/view"
    mock_resp.history = [mock_history_item]
    mock_resp.iter_content.return_value = [b"<html><head><title>Research Document</title></head></html>"]

    mock_session.get.return_value = mock_resp

    raw_url = "https://drive.google.com/open?id=ABC123"
    res = resolve_and_validate_gdrive_url(raw_url, session=mock_session)

    assert res.is_google_drive is True
    assert res.google_file_id == "ABC123"
    assert res.canonical_url == "https://drive.google.com/file/d/ABC123/view"
    assert res.initial_http_status == 303
    assert res.final_http_status == 200
    assert res.drive_status == "redirect_resolved"
    assert res.is_downloadable is True
    assert "https://drive.google.com/uc?export=download&id=ABC123" in res.download_url

def test_resolve_permission_required_mocked():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://accounts.google.com/ServiceLogin?service=wise"
    mock_resp.history = [MagicMock(status_code=302)]
    mock_resp.iter_content.return_value = [b"Sign in with your Google Account to access this document"]
    mock_session.get.return_value = mock_resp

    raw_url = "https://docs.google.com/document/d/PRIVATE_DOC_789/edit"
    res = resolve_and_validate_gdrive_url(raw_url, session=mock_session)

    assert res.is_google_drive is True
    assert res.google_file_id == "PRIVATE_DOC_789"
    assert res.drive_status == "permission_required"
    assert res.is_downloadable is False
    assert res.download_url is None
