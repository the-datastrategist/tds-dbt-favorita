"""Tests for safe 7z extraction in the Favorita load script."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.load_favorita_to_bigquery import extract_csvs_from_7z


@pytest.mark.unit
class TestExtractCsvsFrom7z:
    @patch("scripts.load_favorita_to_bigquery.py7zr.SevenZipFile")
    def test_rejects_path_traversal(self, mock_seven_zip_file: MagicMock) -> None:
        archive = MagicMock()
        archive.getnames.return_value = ["../outside.csv"]
        mock_seven_zip_file.return_value.__enter__.return_value = archive

        with pytest.raises(ValueError, match="Unsafe path"):
            extract_csvs_from_7z(Path("archive.7z"), Path("/tmp/extract"))

    @patch("scripts.load_favorita_to_bigquery.py7zr.SevenZipFile")
    def test_extracts_when_paths_are_safe(self, mock_seven_zip_file: MagicMock, tmp_path: Path) -> None:
        extract_dir = tmp_path / "out"
        extract_dir.mkdir()
        csv_path = extract_dir / "train.csv"
        csv_path.write_text("a,b\n1,2\n", encoding="utf-8")

        archive = MagicMock()
        archive.getnames.return_value = ["train.csv"]

        def fake_extractall(path: Path) -> None:
            (path / "train.csv").write_text("a,b\n1,2\n", encoding="utf-8")

        archive.extractall.side_effect = fake_extractall
        mock_seven_zip_file.return_value.__enter__.return_value = archive

        csv_files = extract_csvs_from_7z(tmp_path / "archive.7z", extract_dir)
        assert csv_files == [csv_path]
