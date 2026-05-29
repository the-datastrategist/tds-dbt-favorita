"""Prediction script for Vertex AI models."""
import argparse
import pandas as pd
from google.cloud import aiplatform
from google.cloud import storage
import joblib
from vertex.utils.data_utils import BigQueryLoader, load_config_from_yaml


class VertexPredictor:
    """Class to load models and generate predictions from Vertex AI."""
    
    def __init__(self, config):
        """
        Initialize predictor with configuration.
        
        Args:
            config (dict): Configuration dictionary containing model parameters.
        """
        self.config = config
        self.model = None
        self.bq_loader = BigQueryLoader(config)
        
        # Initialize Vertex AI client
        project_id = config.get("inputs", {}).get("project_id") or config.get("project_id")
        region = config.get("inputs", {}).get("region") or config.get("region", "us-central1")
        
        aiplatform.init(project=project_id, location=region)
    
    def load_model_from_gcs(self, model_uri):
        """
        Load model from Google Cloud Storage.
        
        Args:
            model_uri (str): GCS URI to the model file (e.g., gs://bucket/model.joblib)
        
        Returns:
            Loaded model object
        """
        # Parse GCS URI
        if model_uri.startswith("gs://"):
            bucket_name, blob_path = model_uri.replace("gs://", "").split("/", 1)
        else:
            raise ValueError(f"Invalid GCS URI: {model_uri}")
        
        # Download model to local temp file
        import tempfile
        import os
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.joblib') as tmp_file:
            blob.download_to_filename(tmp_file.name)
            self.model = joblib.load(tmp_file.name)
            os.unlink(tmp_file.name)
        
        print(f"[INFO] Loaded model from {model_uri}")
        return self.model
    
    def load_model_from_vertex(self, model_name):
        """
        Load model from Vertex AI Model Registry.
        
        Args:
            model_name (str): Name of the model in Vertex AI
        
        Returns:
            Loaded model object
        """
        models = aiplatform.Model.list(filter=f'display_name="{model_name}"')
        
        if not models:
            raise ValueError(f"Model '{model_name}' not found in Vertex AI")
        
        model = models[0]
        model_uri = model.uri
        
        print(f"[INFO] Found model in Vertex AI: {model.resource_name}")
        print(f"[INFO] Model URI: {model_uri}")
        
        return self.load_model_from_gcs(model_uri)
    
    def prepare_prediction_data(self):
        """
        Prepare data for prediction from BigQuery or file.
        
        Returns:
            pandas.DataFrame: Data prepared for prediction
        """
        # Load data from BigQuery
        df = self.bq_loader.load_data()
        
        # Exclude columns if specified
        excluded_columns = self.config.get("inputs", {}).get("excluded_columns", [])
        prediction_df = df.drop(columns=excluded_columns, errors="ignore")
        
        print(f"[INFO] Prepared {len(prediction_df)} rows for prediction")
        return prediction_df, df
    
    def predict(self, model_uri=None, model_name=None):
        """
        Generate predictions using the loaded model.
        
        Args:
            model_uri (str, optional): GCS URI to model file
            model_name (str, optional): Vertex AI model name
        
        Returns:
            pandas.DataFrame: Predictions with original data
        """
        # Load model
        if model_uri:
            self.load_model_from_gcs(model_uri)
        elif model_name:
            self.load_model_from_vertex(model_name)
        else:
            model_uri = self.config.get("inputs", {}).get("model_uri")
            model_name = self.config.get("inputs", {}).get("model_name")
            if model_uri:
                self.load_model_from_gcs(model_uri)
            elif model_name:
                self.load_model_from_vertex(model_name)
            else:
                raise ValueError("Either model_uri or model_name must be provided")
        
        # Prepare prediction data
        prediction_X, original_df = self.prepare_prediction_data()
        
        # Generate predictions
        predictions = self.model.predict(prediction_X)
        print(f"[INFO] Generated {len(predictions)} predictions")
        
        # Combine with original data
        result_df = original_df.copy()
        result_df['prediction'] = predictions
        result_df['prediction_timestamp'] = pd.Timestamp.now()
        
        return result_df
    
    def save_predictions(self, predictions_df):
        """
        Save predictions to BigQuery.
        
        Args:
            predictions_df (pandas.DataFrame): DataFrame containing predictions
        """
        prediction_table = self.config.get("outputs", {}).get("prediction_table")
        
        if prediction_table:
            self.bq_loader.write_data(
                df=predictions_df,
                table_name=prediction_table,
                write_disposition="WRITE_APPEND"
            )
            print(f"[INFO] Saved predictions to BigQuery: {prediction_table}")
        else:
            print("[WARNING] No prediction_table specified in config, skipping save")
    
    def run(self, model_uri=None, model_name=None):
        """
        Run complete prediction pipeline.
        
        Args:
            model_uri (str, optional): GCS URI to model file
            model_name (str, optional): Vertex AI model name
        """
        predictions = self.predict(model_uri=model_uri, model_name=model_name)
        self.save_predictions(predictions)
        return predictions


def main():
    """Main entry point for prediction script."""
    parser = argparse.ArgumentParser(
        description="Generate predictions using Vertex AI models."
    )
    parser.add_argument(
        "--f", "--file_path",
        type=str,
        required=True,
        help="Path to the YAML config file.",
        dest="file_path"
    )
    parser.add_argument(
        "--c", "--config_name",
        type=str,
        default=None,
        help="Name of the config to load.",
        dest="config_name"
    )
    parser.add_argument(
        "--model_uri",
        type=str,
        default=None,
        help="GCS URI to model file (overrides config).",
        dest="model_uri"
    )
    parser.add_argument(
        "--model_name",
        type=str,
        default=None,
        help="Vertex AI model name (overrides config).",
        dest="model_name"
    )
    
    args = parser.parse_args()
    
    # Load config
    config = load_config_from_yaml(
        file_name=args.file_path,
        config_name=args.config_name
    )
    
    # Initialize and run predictor
    predictor = VertexPredictor(config)
    predictions = predictor.run(
        model_uri=args.model_uri,
        model_name=args.model_name
    )
    
    print(f"[INFO] Prediction completed. Generated {len(predictions)} predictions.")


if __name__ == "__main__":
    main()
