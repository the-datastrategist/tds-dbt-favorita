"""Tests for Vertex Model Registry registration."""

from unittest.mock import MagicMock, patch

import pytest

from vertex.utils.artifacts import register_from_manifest


@pytest.mark.unit
class TestRegisterFromManifest:
    @patch("google.cloud.aiplatform", create=True)
    @patch("vertex.utils.artifacts.storage.Client")
    def test_register_from_manifest(self, mock_storage_client, mock_aiplatform):
        mock_blob = MagicMock()
        mock_blob.download_as_text.return_value = (
            '{"joblib_gcs_uri": "gs://b/p/model.joblib", "model_file": "model.joblib"}'
        )
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client.return_value.bucket.return_value = mock_bucket

        mock_model = MagicMock()
        mock_model.resource_name = "projects/p/locations/us-central1/models/1"
        mock_aiplatform.Model.upload.return_value = mock_model

        resource = register_from_manifest(
            manifest_uri="gs://b/p/manifest.json",
            display_name="test_model",
            project_id="test-project",
            region="us-central1",
        )
        assert resource.endswith("/models/1")
        mock_aiplatform.Model.upload.assert_called_once()
        mock_model.wait.assert_called_once()
