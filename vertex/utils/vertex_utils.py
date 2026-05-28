from google.cloud import aiplatform
from google.cloud import storage
import joblib
import os
from vertex.utils.data_utils import get_hash_id, get_timestamp


class VertexModelLogger:
    def __init__(self, config, saver):
        self.config = config
        self.saver = saver

        # Get project and region from config
        project_id = config.get("inputs", {}).get("project_id") or config.get("project_id")
        region = config.get("inputs", {}).get("region") or config.get("region", "us-central1")

        # Initialize the Vertex AI client
        aiplatform.init(
            project=project_id,
            location=region
        )
        self.experiment = aiplatform.Experiment.run(name=self.saver.model_name)

    def log_metrics(self, metrics):
        for k, v in metrics.items():
            self.experiment.log_metric(k, v)

    def register_model(self):
        model = aiplatform.Model.upload(
            display_name=self.saver.model_name,
            artifact_uri=self.saver.model_artifact_uri,
            serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.0-24:latest"
        )
        model.wait()
        print(f"Model registered: {model.resource_name}")


class VertexModelSaver:
    """
    Class to save and register models in Google Cloud Storage and Vertex AI.

    Args:
        config (dict): Configuration dictionary containing model parameters and paths.
        model: Trained model object to save.
    
    Functions:
        save_model(): Saves the model to Google Cloud Storage and registers it in Vertex AI.
    """
    def __init__(self, config, model):
        self.config = config
        self.model = model
        self.config_id = get_hash_id(config)
        
        # Hash the model's state for ID generation
        try:
            import pickle
            model_bytes = pickle.dumps(model)
            self.model_id = get_hash_id(model_bytes)
        except Exception:
            # Fallback to timestamp-based ID
            self.model_id = get_timestamp()
        
        self.model_save_datetime = get_timestamp()
        model_name_base = config.get("name", "model")
        self.model_name = f"{model_name_base}_{self.model_save_datetime}_{self.config_id[:8]}_{self.model_id[:8]}"
        
        # Get GCS path from config
        gcs_model_path = config.get("inputs", {}).get("gcs_model_path", "gs://models/")
        if not gcs_model_path.endswith("/"):
            gcs_model_path += "/"
        self.model_artifact_uri = f"{gcs_model_path}{self.model_name}.joblib"

    def save_model(self):
        # Create tmp directory if it doesn't exist
        os.makedirs("vertex/models/tmp", exist_ok=True)
        
        # Get local/tmp storage path
        local_path = f"vertex/models/tmp/{self.model_name}.joblib"

        # Save model to local
        joblib.dump(self.model, local_path)

        # Save model to GCS
        gcs_path = self.model_artifact_uri
        bucket_name, *blob_path_parts = gcs_path.replace("gs://", "").split("/", 1)
        blob_path = blob_path_parts[0] if blob_path_parts else f"{self.model_name}.joblib"
        
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_filename(local_path)
        print(f"Model uploaded to GCS: {self.model_artifact_uri}")

        # Register model in Vertex AI
        self.logger = VertexModelLogger(config=self.config, saver=self)
        self.logger.register_model()
        print(f"Model saved to GCS: {self.model_artifact_uri}")
