"""Tests for Vertex Model Registry registration."""

from unittest.mock import MagicMock, patch

import pytest

from vertex.utils.artifacts import artifact_sha256, load_joblib_from_gcs, register_from_manifest


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


@pytest.mark.unit
class TestVerifiedJoblibLoading:
    @patch("vertex.utils.artifacts.joblib.load")
    @patch("vertex.utils.artifacts.storage.Client")
    def test_loads_only_after_checksum_verification(self, mock_storage_client, mock_joblib_load):
        payload = b"trusted-joblib-payload"
        mock_storage_client.return_value.bucket.return_value.blob.return_value.download_as_bytes.return_value = (
            payload
        )
        mock_joblib_load.return_value = "model"

        result = load_joblib_from_gcs(
            "gs://models/run/model.joblib",
            expected_sha256=artifact_sha256(payload),
        )

        assert result == "model"
        mock_joblib_load.assert_called_once()

    @patch("vertex.utils.artifacts.joblib.load")
    @patch("vertex.utils.artifacts.storage.Client")
    def test_rejects_checksum_mismatch_before_deserialization(
        self, mock_storage_client, mock_joblib_load
    ):
        mock_storage_client.return_value.bucket.return_value.blob.return_value.download_as_bytes.return_value = (
            b"replaced-payload"
        )

        with pytest.raises(ValueError, match="checksum mismatch"):
            load_joblib_from_gcs(
                "gs://models/run/model.joblib",
                expected_sha256=artifact_sha256(b"original-payload"),
            )

        mock_joblib_load.assert_not_called()

    @patch("vertex.utils.artifacts.joblib.load")
    @patch("vertex.utils.artifacts.storage.Client")
    def test_rejects_legacy_manifest_without_checksum(self, mock_storage_client, mock_joblib_load):
        mock_storage_client.return_value.bucket.return_value.blob.return_value.download_as_bytes.return_value = (
            b"legacy-payload"
        )

        with pytest.raises(ValueError, match="without manifest joblib_sha256"):
            load_joblib_from_gcs(
                "gs://models/run/model.joblib",
                expected_sha256=None,
            )

        mock_joblib_load.assert_not_called()
