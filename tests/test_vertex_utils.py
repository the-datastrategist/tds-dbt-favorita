"""Tests for Vertex AI utilities."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from vertex.utils.vertex_utils import VertexModelSaver, VertexModelLogger


class TestVertexModelSaver:
    """Test VertexModelSaver class."""
    
    @pytest.fixture
    def sample_config(self):
        """Fixture providing sample config."""
        return {
            'name': 'test_model',
            'inputs': {
                'project_id': 'test-project',
                'region': 'us-central1',
                'gcs_model_path': 'gs://test-bucket/models/'
            }
        }
    
    @pytest.fixture
    def sample_model(self):
        """Fixture providing sample model."""
        from xgboost import XGBRegressor
        model = XGBRegressor()
        # Train on dummy data
        import numpy as np
        X = np.random.rand(10, 5)
        y = np.random.rand(10)
        model.fit(X, y)
        return model
    
    def test_init(self, sample_config, sample_model):
        """Test VertexModelSaver initialization."""
        saver = VertexModelSaver(sample_config, sample_model)
        
        assert saver.config == sample_config
        assert saver.model == sample_model
        assert saver.model_name.startswith('test_model')
        assert 'gs://test-bucket/models/' in saver.model_artifact_uri
    
    @patch('vertex.utils.vertex_utils.storage')
    @patch('vertex.utils.vertex_utils.joblib')
    @patch('vertex.utils.vertex_utils.aiplatform')
    @patch('vertex.utils.vertex_utils.os.makedirs')
    def test_save_model(self, mock_makedirs, mock_aiplatform, mock_joblib, mock_storage, 
                       sample_config, sample_model):
        """Test saving model to GCS."""
        saver = VertexModelSaver(sample_config, sample_model)
        
        # Mock storage client
        mock_client = Mock()
        mock_bucket = Mock()
        mock_blob = Mock()
        mock_storage.Client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        
        # Mock Vertex AI
        mock_experiment = Mock()
        mock_aiplatform.Experiment.run.return_value = mock_experiment
        
        saver.save_model()
        
        # Verify joblib was called to save model
        mock_joblib.dump.assert_called_once()
        # Verify blob upload was called
        mock_blob.upload_from_filename.assert_called_once()
