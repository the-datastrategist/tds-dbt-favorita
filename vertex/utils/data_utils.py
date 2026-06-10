import hashlib
import json
import os
from datetime import datetime
from typing import Dict, Optional, Union

import pandas as pd
from google.cloud import bigquery


class BigQueryLoader:
    def __init__(self, config):
        self.config = config
        # Get project_id from config, supporting nested structure
        project_id = config.get("project_id") or config.get("inputs", {}).get("project_id")
        if not project_id:
            raise ValueError("project_id must be provided in config")
        self.client = bigquery.Client(project=project_id)

    def load_data(self, query=None, file=None):
        # Use provided query or file, or look in config
        if query:
            return self.client.query(query).to_dataframe()
        elif file:
            with open(file, "r") as f:
                query = f.read()
            return self.client.query(query).to_dataframe()
        elif "sql_file" in self.config.get("inputs", {}):
            sql_path = self.config["inputs"]["sql_file"]
            with open(sql_path, "r") as f:
                query = f.read()
            return self.client.query(query).to_dataframe()
        elif self.config.get("inputs"):
            from vertex.utils.data_loading import resolve_input_sql

            sql = resolve_input_sql(self.config)
            return self.client.query(sql).to_dataframe()
        else:
            raise ValueError("Either query or file must be provided.")

    def write_data(self, df, table_name=None, write_disposition=None):
        # Get the table name from the config if not provided
        table_name = table_name or self.config["output_table"]
        if not table_name:
            raise ValueError("Table name must be provided.")
        # Set the write disposition
        write_disposition = write_disposition or "WRITE_TRUNCATE"
        # Load the data into BigQuery
        job = self.client.load_table_from_dataframe(
            df, table_name, job_config=bigquery.LoadJobConfig(write_disposition=write_disposition)
        )
        job.result()


def parse_env_list(env_var: str, default: Optional[str] = None) -> list:
    """Parse a comma-separated environment variable into a list."""
    raw = os.getenv(env_var, default or "")
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_hash_id(data: Union[dict, str, bytes]) -> str:
    """
    Generate a SHA256 hash from a dictionary or string.

    Args:
        data (dict or str): Input data to hash.

    Returns:
        str: A SHA256 hash string.
    """
    if isinstance(data, dict):
        # Ensure consistent ordering for reproducibility
        data_str = json.dumps(data, sort_keys=True)
    elif isinstance(data, str):
        data_str = data
    elif isinstance(data, bytes):
        data_str = data.decode("utf-8", errors="replace")
    else:
        raise ValueError("Input must be a dict, str, or bytes")

    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()


def get_hash(data: Union[dict, str, bytes]) -> str:
    """Alias for get_hash_id (compatible with legacy training scripts)."""
    return get_hash_id(data)


def get_timestamp() -> str:
    """
    Returns the current datetime as a string in 'YYYYMMDD_HHMMSS' format.
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def split_by_time_percentile(df: pd.DataFrame, date_col: str = "date", test_size: float = 0.2):
    """
    Splits a DataFrame into train and test sets based on unique dates,
    keeping the latest `test_size` percent of dates in the test set.

    Args:
        df (pd.DataFrame): Input DataFrame with repeated dates.
        date_col (str): Column name containing datetime values.
        test_size (float): Fraction of unique dates to allocate to the test set.

    Returns:
        train_df (pd.DataFrame): Rows corresponding to earlier dates.
        test_df (pd.DataFrame): Rows corresponding to latest dates.
    """
    if date_col not in df.columns:
        raise ValueError(f"Column '{date_col}' not found in DataFrame.")

    # Sort unique dates
    unique_dates = sorted(df[date_col].dropna().unique())
    split_idx = int(len(unique_dates) * (1 - test_size))
    cutoff_date = unique_dates[split_idx]

    # Partition based on cutoff date
    train_df = df[df[date_col] < cutoff_date].sort_values(date_col)
    test_df = df[df[date_col] >= cutoff_date].sort_values(date_col)

    return train_df.reset_index(drop=True), test_df.reset_index(drop=True)


def load_config_from_yaml(file_name: str, config_name: Optional[str] = None) -> Dict:
    """
    Load a config from YAML with defaults merged (delegates to vertex.config.load_config).
    """
    from vertex.config.load_config import load_all_configs, load_model_config

    if config_name is None:
        return load_all_configs(file_name)[0]
    return load_model_config(config_name, file_name)
