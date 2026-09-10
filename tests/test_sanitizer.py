import pytest
from utils.file_saver import sanitize_filename, get_filename_from_url_and_headers, convert_gdrive_url_to_download_link

def test_sanitize_filename():
    assert sanitize_filename("Laporan / Tahunan : 2025?.pdf") == "Laporan__Tahunan__2025.pdf"
    assert sanitize_filename("  file<>|*name  ") == "filename"
    assert sanitize_filename("") == "downloaded_file"
    assert sanitize_filename("a" * 150, max_length=50) == "a" * 50

def test_convert_gdrive_url():
    # Folder
    url_folder = "https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRs"
    target, res_type, is_folder = convert_gdrive_url_to_download_link(url_folder)
    assert is_folder is True
    assert res_type == "gdrive_folder"

    # Single File
    url_file = "https://drive.google.com/file/d/1XyZAbCdEfGhIjKlMnOp/view"
    target, res_type, is_folder = convert_gdrive_url_to_download_link(url_file)
    assert is_folder is False
    assert res_type == "gdrive_file"
    assert "export=download&id=1XyZAbCdEfGhIjKlMnOp" in target

    # Google Doc
    url_doc = "https://docs.google.com/document/d/1DocId123/edit"
    target, res_type, is_folder = convert_gdrive_url_to_download_link(url_doc)
    assert res_type == "gdoc"
    assert "export?format=pdf" in target

    # Google Sheet
    url_sheet = "https://docs.google.com/spreadsheets/d/1SheetId123/edit"
    target, res_type, is_folder = convert_gdrive_url_to_download_link(url_sheet)
    assert res_type == "gsheet"
    assert "export?format=csv" in target
