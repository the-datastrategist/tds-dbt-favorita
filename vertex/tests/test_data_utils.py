"""Tests for data utilities."""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from vertex.utils.data_utils import get_hash_id, get_timestamp, split_by_time_percentile, load_config_from_yaml
import os


class TestGetHashId:
    """Test hash ID generation."""
    
    def test_hash_dict(self):
        """Test hashing a dictionary."""
        data = {"key1": "value1", "key2": "value2"}
        hash1 = get_hash_id(data)
        hash2 = get_hash_id(data)
        assert hash1 == hash2
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA256 produces 64-char hex string
    
    def test_hash_string(self):
        """Test hashing a string."""
        data = "test_string"
        hash1 = get_hash_id(data)
        hash2 = get_hash_id(data)
        assert hash1 == hash2
        assert isinstance(hash1, str)
    
    def test_hash_consistency(self):
        """Test that same data produces same hash."""
        data1 = {"a": 1, "b": 2}
        data2 = {"b": 2, "a": 1}  # Same keys, different order
        hash1 = get_hash_id(data1)
        hash2 = get_hash_id(data2)
        assert hash1 == hash2  # Should be same due to sort_keys=True


class TestGetTimestamp:
    """Test timestamp generation."""
    
    def test_timestamp_format(self):
        """Test timestamp is in correct format."""
        timestamp = get_timestamp()
        assert isinstance(timestamp, str)
        # Should match YYYYMMDD_HHMMSS format
        assert len(timestamp) == 15
        assert timestamp[8] == "_"


class TestSplitByTimePercentile:
    """Test time-based train/test split."""
    
    def test_split_basic(self):
        """Test basic time-based split."""
        dates = pd.date_range(start='2023-01-01', end='2023-12-31', freq='D')
        df = pd.DataFrame({
            'date': dates,
            'value': range(len(dates))
        })
        
        train_df, test_df = split_by_time_percentile(df, date_col='date', test_size=0.2)
        
        assert len(train_df) + len(test_df) == len(df)
        assert train_df['date'].max() < test_df['date'].min()
        assert len(test_df) / len(df) == pytest.approx(0.2, rel=0.1)
    
    def test_split_no_date_column(self):
        """Test error when date column missing."""
        df = pd.DataFrame({'value': [1, 2, 3]})
        with pytest.raises(ValueError, match="Column 'date' not found"):
            split_by_time_percentile(df, date_col='date')
    
    def test_split_with_repeated_dates(self):
        """Test split with repeated dates."""
        dates = pd.to_datetime(['2023-01-01', '2023-01-01', '2023-01-02', '2023-01-02', '2023-01-03'])
        df = pd.DataFrame({
            'date': dates,
            'value': range(len(dates))
        })
        
        train_df, test_df = split_by_time_percentile(df, date_col='date', test_size=0.5)
        
        # All rows from earlier dates should be in train
        assert train_df['date'].max() < test_df['date'].min()


class TestLoadConfigFromYaml:
    """Test YAML config loading."""
    
    def test_load_first_config(self, tmp_path):
        """Test loading first config when no name specified."""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("""
configs:
  - name: config1
    value: 1
  - name: config2
    value: 2
""")
        
        config = load_config_from_yaml(str(config_file))
        assert config['name'] == 'config1'
        assert config['value'] == 1
    
    def test_load_named_config(self, tmp_path):
        """Test loading config by name."""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("""
configs:
  - name: config1
    value: 1
  - name: config2
    value: 2
""")
        
        config = load_config_from_yaml(str(config_file), config_name='config2')
        assert config['name'] == 'config2'
        assert config['value'] == 2
    
    def test_config_not_found(self, tmp_path):
        """Test error when config name not found."""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("""
configs:
  - name: config1
    value: 1
""")
        
        with pytest.raises(ValueError, match="Config with name 'config3' not found"):
            load_config_from_yaml(str(config_file), config_name='config3')
    
    def test_file_not_found(self):
        """Test error when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            load_config_from_yaml("nonexistent_file.yaml")
