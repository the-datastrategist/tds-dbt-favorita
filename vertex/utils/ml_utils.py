"""Feature-matrix helpers for Vertex training scripts."""

import pandas as pd


def sanitize_feature_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names for ML and BigQuery compatibility."""
    out = df.copy()
    out.columns = [
        str(col)
        .strip()
        .replace(" ", "_")
        .replace("[", "_")
        .replace("]", "_")
        .replace("<", "_")
        for col in out.columns
    ]
    return out
