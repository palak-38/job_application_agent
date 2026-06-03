from unittest.mock import MagicMock, patch
from app.services.resume_reader import read_resume_as_text


def test_read_resume_returns_correct_text():
    fake_resume = "John Doe\nSoftware Engineer\nPython, FastAPI, Docker"

    def fake_media_download(buffer, request):
        buffer.write(fake_resume.encode("utf-8"))
        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)
        return mock_downloader

    with patch("app.services.resume_reader.build_google_services") as mock_build, \
         patch("app.services.resume_reader.MediaIoBaseDownload", side_effect=fake_media_download):
        mock_build.return_value = {"drive": MagicMock()}
        result = read_resume_as_text()

    assert result == fake_resume


def test_read_resume_returns_non_empty_string():
    fake_resume = "Any resume content here"

    def fake_media_download(buffer, request):
        buffer.write(fake_resume.encode("utf-8"))
        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)
        return mock_downloader

    with patch("app.services.resume_reader.build_google_services") as mock_build, \
         patch("app.services.resume_reader.MediaIoBaseDownload", side_effect=fake_media_download):
        mock_build.return_value = {"drive": MagicMock()}
        result = read_resume_as_text()

    assert isinstance(result, str)
    assert len(result) > 0