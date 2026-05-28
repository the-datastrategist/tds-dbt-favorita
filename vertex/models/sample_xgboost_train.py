import xgboost as xgb
from sklearn.metrics import mean_squared_error
from sklearn.metrics import explained_variance_score
import numpy as np
import pandas as pd
import argparse
from vertex.utils.data_utils import BigQueryLoader, get_timestamp, get_hash_id
from vertex.utils.data_utils import split_by_time_percentile
from vertex.utils.data_utils import load_config_from_yaml
from vertex.utils.vertex_utils import VertexModelSaver


class XGBoostForecaster:
    def __init__(self, config):
        self.config = config
        self.model_run_datetime = get_timestamp()
        self.model = None
        self.vertex_storage = None
        self.bq_loader = BigQueryLoader(config)

    def _get_training_data(self):
        # Load from query or file
        if "sql_query" in self.config["inputs"]:
            df = self.bq_loader.load_data(query=self.config["sql_query"])
        elif "sql_file" in self.config["inputs"]:
            df = self.bq_loader.load_data(file=self.config["sql_file"])

        # Adjust date column if it exists
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def prepare_data(self):
        # Prepare the data
        df = self._get_training_data()
        test_size = self.config.get("inputs", {}).get("test_size", 0.2)
        self.train_df, self.test_df = split_by_time_percentile(
            df, test_size=test_size, date_col="date")

        print(f"[INFO] Got training data. {self.train_df.shape[0]} rows and {self.train_df.shape[1]} columns.")
        print(f"[INFO] Got test data. {self.test_df.shape[0]} rows and {self.test_df.shape[1]} columns.")

        # Specify the target column (y)
        if "target_column" in self.config["inputs"]:
            self.train_y = self.train_df[self.config["inputs"]["target_column"]]
            self.test_y = self.test_df[self.config["inputs"]["target_column"]]
            print(f"[INFO] Got target data from column `{self.config['inputs']['target_column']}`.")
        else:
            raise ValueError("Target column not specified in the config.")

        # Specify the feature columns (X)
        excluded_columns = self.config.get("inputs", {}).get("excluded_columns", [])
        self.train_X = self.train_df.drop(columns=excluded_columns, errors="ignore")
        self.test_X = self.test_df.drop(columns=excluded_columns, errors="ignore")

    def train(self):
        # Prep training data
        self.prepare_data()

        # Run the model
        params = self.config["inputs"].get("model_params", {})
        self.model = xgb.XGBRegressor(objective="reg:squarederror", **params)
        self.model.fit(self.train_X, self.train_y)
        print(f"[INFO] Trained model.")
        
        # Save the model to GCS
        if "gcs_model_path" in self.config["inputs"]:
            self.save_model()
            print(f"[INFO] Saved model to {self.config['inputs']['gcs_model_path']}.")
        else:
            raise ValueError("GCS model path not specified in the config. Add `gcs_model_path` to inputs.")

    def predict_and_evaluate(self):
        # Make predictions
        self.pred_y = self.model.predict(self.test_X)
        print(f"[INFO] Made {len(self.pred_y)} predictions.")

        # Create a DataFrame for predictions
        self.predictions = pd.DataFrame({
            "prediction_date": self.test_df["date"],
            "prediction": self.pred_y,
            "actual": self.test_y,
            "error": self.test_y - self.pred_y,
        })

    def calculate_performance_metrics(self):
        # Calculate mean absolute outcome
        mean_abs_error = self.predictions['error'].abs().mean()
        mean_abs_actual = self.predictions['actual'].abs().mean()
        error_variance = self.predictions['error'].var()

        # Get performance metrics
        mean_abs_pct_error = round(mean_abs_error / mean_abs_actual, 8) if mean_abs_actual else None
        pct_error_variance = round(error_variance / mean_abs_actual, 8) if mean_abs_actual else None
        
        self.performance_metrics = {
            "rmse": round(np.sqrt(mean_squared_error(self.test_y, self.pred_y)), 8),
            "rsquared": round(explained_variance_score(self.test_y, self.pred_y), 8),
            "mean_abs_error": round(mean_abs_error, 8),
            "mean_abs_actual": round(mean_abs_actual, 8) if mean_abs_actual else None,
            "mean_actual": round(self.predictions['actual'].mean(), 8),
            "mean_abs_pct_error": mean_abs_pct_error,
            "error_variance": round(error_variance, 8),
            "pct_error_variance": pct_error_variance
        }
        print(f"[INFO] Calculated performance metrics.")

    def save_model(self):
        # Save the model to GCS and log to VertexAI
        self.vertex_storage = VertexModelSaver(config=self.config, model=self.model)
        self.vertex_storage.save_model()
        print(f"[INFO] Saved model to VertexAI.")

    def save_predictions(self):
        # Update predictions with metadata
        if self.vertex_storage:
            self.predictions["config_id"] = self.vertex_storage.config_id
            self.predictions["model_id"] = self.vertex_storage.model_id
            self.predictions["model_name"] = self.vertex_storage.model_name
            self.predictions["model_artifact_uri"] = self.vertex_storage.model_artifact_uri
            self.predictions["model_save_datetime"] = self.vertex_storage.model_save_datetime
            self.predictions["model_run_datetime"] = self.model_run_datetime

        # Save predictions to BQ
        prediction_table = self.config.get("outputs", {}).get("prediction_table", None)
        if prediction_table:
            self.bq_loader.write_data(
                df=self.predictions,
                table_name=prediction_table,
                write_disposition="WRITE_APPEND"
            )
            print(f"[INFO] Saving predictions to BigQuery: {prediction_table}.")

    def save_performance_metrics(self):
        # Create a DataFrame for performance metrics
        performance = pd.DataFrame.from_dict(data=self.performance_metrics, orient='index')
        performance = performance.reset_index()
        performance.columns = ['parameter', 'value']
        performance['model_id'] = self.vertex_storage.model_id
        performance['model_name'] = self.vertex_storage.model_name

        # Add metadata to performance metrics
        performance_index = {
            "model_id": self.vertex_storage.model_id,
            "model_name": self.vertex_storage.model_name,
            "model_artifact_uri": self.vertex_storage.model_artifact_uri,
            "model_save_datetime": self.vertex_storage.model_save_datetime,
            "model_run_datetime": self.model_run_datetime,
            "target_column": self.config.get("inputs", {}).get("target_column", "")
        }
        performance_index_df = pd.DataFrame.from_dict(performance_index, orient='index').T
        performance = performance_index_df.merge(
            performance,
            how='inner',
            on='model_id',
            suffixes=('_drop', '')
        )
        self.performance = performance[[col for col in performance.columns if '_drop' not in col]]

        # Save performance metrics to BQ
        performance_table = self.config.get("outputs", {}).get("performance_table", None)
        if performance_table:
            self.bq_loader.write_data(
                df=self.performance,
                table_name=performance_table,
                write_disposition="WRITE_APPEND"
            )
            print(f"[INFO] Saving model performance metrics to BigQuery: {performance_table}.")

    def run(self):
        self.prepare_data()
        self.train()
        self.predict_and_evaluate()
        self.calculate_performance_metrics()
        self.save_model()
        self.save_predictions()
        self.save_performance_metrics()


def main():
    """Main entry point for training script."""
    # Get arguments from command line
    parser = argparse.ArgumentParser(description="Run XGBoost forecasting model with a given config.")
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
    args = parser.parse_args()

    # Load the config
    config = load_config_from_yaml(
        file_name=args.file_path,
        config_name=args.config_name
    )

    # Initialize and run the model
    model = XGBoostForecaster(config)
    model.run()


if __name__ == "__main__":
    main()
