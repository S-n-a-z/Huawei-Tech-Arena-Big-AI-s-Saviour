from __future__ import annotations

import gzip
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import warnings

import pandas as pd
import numpy as np
from pyproj import Transformer

logger = logging.getLogger(__name__)


# Geographic reference
SOURCE_CRS = "EPSG:27700"  # British National Grid
TARGET_CRS = "EPSG:4326"   # WGS84 (latitude/longitude)


class NaFIRSLoader:
    """Download and load NaFIRS LV Faults data."""

    # NaFIRS data from Ofgem statistical releases (CSV or CSV.GZ format)
    # Real-world column mapping from actual SHEPD/SEPD data
    
    # Try processed combined file first, fall back to raw
    DEFAULT_PATH = Path("data/processed/nafirs_lv_combined.csv.gz")
    
    # Mapping from real column names to normalized internal names
    COLUMN_MAPPING = {
        "DISTRICT_SHORT_CODE": "DISTRICT_ID",
        "REPORTING_YEAR": "REPORTING_YEAR",
        "DISTRICT_CODE": "DISTRICT_CODE",
        "REFERENCE_NUMBER": "INCIDENT_ID",
        "LV_INCIDENT_TIME": "FAULT_START_TIME",
        "PRIMARY_NRN": "NETWORK_CODE",
        "CATEGORY_DESCRIPTION": "FAULT_CATEGORY",
        "CAUSE_DESCRIPTION": "CAUSE_DESCRIPTION",
        "LV_CUST_AFF": "CUSTOMERS_AFFECTED",
        "LV_CUST_MINS_LOST": "CUSTOMER_MINUTES_OFF",
        "AVG_TIME_OFF_MINS": "AVG_OUTAGE_DURATION_MIN",
        "EQUIPMENT_DESCRIPTION": "EQUIPMENT_DESCRIPTION",
        "COMPONENT_DESCRIPTION": "COMPONENT_DESCRIPTION",
    }
    
    EXPECTED_COLUMNS = set(COLUMN_MAPPING.keys())

    def __init__(self, path: Path | None = None):
        """Initialize loader with optional custom path."""
        self.path = path or self.DEFAULT_PATH

    def load(self, decompress: bool = True) -> pd.DataFrame:
        """
        Load NaFIRS LV Faults data.
        
        Args:
            decompress: If True, automatically decompress .gz files
            
        Returns:
            DataFrame with normalized columns [DISTRICT_ID, NETWORK, INCIDENT_ID, ...]
        """
        if not self.path.exists():
            raise FileNotFoundError(f"NaFIRS data not found at {self.path}")

        logger.info(f"Loading NaFIRS data from {self.path}")
        
        if decompress and self.path.suffix == ".gz":
            with gzip.open(self.path, "rt", encoding="utf-8") as f:
                data = pd.read_csv(f, low_memory=False)
        else:
            data = pd.read_csv(self.path, low_memory=False)

        # Standardize column names (strip whitespace)
        data.columns = [col.strip() for col in data.columns]
        
        # Validate required columns
        missing = set(self.EXPECTED_COLUMNS) - set(data.columns)
        if missing:
            logger.warning(
                f"NaFIRS data missing columns: {missing}. "
                f"Available columns: {data.columns.tolist()}"
            )

        # Rename columns to normalized internal format
        rename_map = {k: v for k, v in self.COLUMN_MAPPING.items() if k in data.columns}
        data = data.rename(columns=rename_map)

        # Map district short codes to network names
        data["NETWORK"] = data["DISTRICT_ID"].map(self._get_network_from_district)
        
        # Convert datetime column
        if "FAULT_START_TIME" in data.columns:
            data["FAULT_START_TIME"] = pd.to_datetime(
                data["FAULT_START_TIME"], 
                errors="coerce"
            )

        # Convert numeric columns
        numeric_cols = ["CUSTOMERS_AFFECTED", "CUSTOMER_MINUTES_OFF", "AVG_OUTAGE_DURATION_MIN"]
        for col in numeric_cols:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")

        logger.info(f"Loaded {len(data)} NaFIRS incident records")
        logger.info(f"Networks: {data['NETWORK'].unique()}")
        logger.info(f"Date range: {data['FAULT_START_TIME'].min()} to {data['FAULT_START_TIME'].max()}")
        
        return data

    @staticmethod
    def _get_network_from_district(district_code: str) -> str:
        """Map SHEPD/SEPD district codes to network names."""
        district_to_network = {
            # SHEPD districts
            "HIGH": "SHEPD", "ARGYLL": "SHEPD", "N/EAST": "SHEPD",
            "ORKN": "SHEPD", "SHET": "SHEPD", "TAYCEN": "SHEPD", "WISLES": "SHEPD",
            # Add SEPD districts as they appear
        }
        return district_to_network.get(str(district_code), "UNKNOWN")


class NaFIRSProcessor:
    """Process and aggregate NaFIRS data for resilience modeling."""

    def __init__(self, incidents: pd.DataFrame):
        """Initialize with loaded incident data."""
        self.incidents = incidents.copy()
        self._validate_data()

    def _validate_data(self) -> None:
        """Validate data quality and log issues."""
        total = len(self.incidents)
        
        # Check for missing critical fields
        if "FAULT_START_TIME" in self.incidents.columns:
            missing_start = self.incidents["FAULT_START_TIME"].isna().sum()
            if missing_start > 0:
                logger.warning(f"{missing_start}/{total} incidents missing FAULT_START_TIME")
        
        if "CUSTOMER_MINUTES_OFF" in self.incidents.columns:
            missing_cmo = self.incidents["CUSTOMER_MINUTES_OFF"].isna().sum()
            if missing_cmo > 0:
                logger.warning(f"{missing_cmo}/{total} incidents missing CUSTOMER_MINUTES_OFF")

    def calculate_outage_duration(self) -> pd.Series:
        """
        Calculate duration of each outage in minutes.
        
        Uses AVG_OUTAGE_DURATION_MIN if available (from data),
        otherwise calculates from CUSTOMER_MINUTES_OFF and CUSTOMERS_AFFECTED.
        
        Returns:
            Series of duration values (in minutes, NaN where unavailable)
        """
        if "AVG_OUTAGE_DURATION_MIN" in self.incidents.columns:
            duration = self.incidents["AVG_OUTAGE_DURATION_MIN"].copy()
            logger.debug("Using AVG_OUTAGE_DURATION_MIN from data")
        elif "CUSTOMER_MINUTES_OFF" in self.incidents.columns and \
             "CUSTOMERS_AFFECTED" in self.incidents.columns:
            # Estimate: avg duration = total customer-minutes / customers affected
            cmo = self.incidents["CUSTOMER_MINUTES_OFF"].fillna(0)
            cust = self.incidents["CUSTOMERS_AFFECTED"].fillna(0)
            duration = pd.Series([np.nan] * len(self.incidents), dtype=float, index=self.incidents.index)
            valid = (cust > 0)
            duration[valid] = cmo[valid] / cust[valid]
            logger.debug("Calculated duration from CUSTOMER_MINUTES_OFF / CUSTOMERS_AFFECTED")
        else:
            logger.warning("Cannot calculate outage duration: missing required columns")
            duration = pd.Series([np.nan] * len(self.incidents), dtype=float, index=self.incidents.index)
        
        return duration

    def aggregate_by_district_time(
        self,
        time_freq: str = "D",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> pd.DataFrame:
        """
        Aggregate outage metrics by district and time period.
        
        Args:
            time_freq: Pandas frequency string ("D" for daily, "H" for hourly, etc.)
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            DataFrame with aggregated outage metrics indexed by (NETWORK, DISTRICT_ID, time)
        """
        data = self.incidents.copy()
        
        # Filter by date range if specified
        if "FAULT_START_TIME" in data.columns:
            if start_date:
                data = data[data["FAULT_START_TIME"] >= start_date]
            if end_date:
                data = data[data["FAULT_START_TIME"] <= end_date]

        # Add duration column
        data["OUTAGE_DURATION_MIN"] = self.calculate_outage_duration()

        # Group by district and time period
        if "FAULT_START_TIME" in data.columns:
            data["TIME_PERIOD"] = data["FAULT_START_TIME"].dt.floor(time_freq)
            groupby_cols = ["NETWORK", "DISTRICT_ID", "TIME_PERIOD"]
        else:
            groupby_cols = ["NETWORK", "DISTRICT_ID"]

        # Aggregate metrics
        agg_dict = {
            "INCIDENT_ID": "count",  # Number of faults
            "CUSTOMERS_AFFECTED": "sum",
            "CUSTOMER_MINUTES_OFF": "sum",
            "OUTAGE_DURATION_MIN": ["mean", "max"],
        }

        result = data.groupby(groupby_cols, as_index=False).agg(agg_dict)
        
        # Flatten column names
        result.columns = [
            "_".join(col).strip("_") if col[1] else col[0]
            for col in result.columns.values
        ]
        
        return result.rename(columns={"INCIDENT_ID_count": "FAULT_COUNT"})

    def extract_fault_causes(self) -> pd.DataFrame:
        """
        Extract and count fault causes across the network.
        
        Returns:
            DataFrame with fault cause distributions by district
        """
        if "FAULT_TYPE" not in self.incidents.columns:
            logger.warning("FAULT_TYPE column not available for cause analysis")
            return pd.DataFrame()

        cause_dist = self.incidents.groupby(
            ["NETWORK", "DISTRICT_ID", "FAULT_TYPE"],
            as_index=False
        ).size().rename(columns={"size": "COUNT"})
        
        return cause_dist.pivot_table(
            index=["NETWORK", "DISTRICT_ID"],
            columns="FAULT_TYPE",
            values="COUNT",
            fill_value=0,
        ).reset_index()

    def regional_outage_proportion(
        self,
        time_freq: str = "D",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> pd.DataFrame:
        """
        Calculate regional outage proportion (fraction of districts with outages).
        
        This metric is used as input to the sigmoidal risk score function in
        the resilience prediction model.
        
        Args:
            time_freq: Pandas frequency string
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            DataFrame with regional outage proportion by network and time
        """
        agg = self.aggregate_by_district_time(time_freq, start_date, end_date)
        
        # Count districts with at least one fault per period
        if "TIME_PERIOD" in agg.columns:
            groupby = ["NETWORK", "TIME_PERIOD"]
        else:
            groupby = ["NETWORK"]

        districts_with_faults = agg.groupby(groupby, as_index=False).size().rename(
            columns={"size": "DISTRICTS_WITH_FAULTS"}
        )
        
        # Total districts per network
        all_districts = agg.groupby(["NETWORK"], as_index=False)[
            "DISTRICT_ID"
        ].nunique().rename(columns={"DISTRICT_ID": "TOTAL_DISTRICTS"})

        result = districts_with_faults.merge(all_districts, on="NETWORK")
        result["OUTAGE_PROPORTION"] = (
            result["DISTRICTS_WITH_FAULTS"] / result["TOTAL_DISTRICTS"]
        )
        
        return result[["NETWORK"] + groupby[1:] + ["OUTAGE_PROPORTION"]]


class NaFIRSFeatureEngine:
    """Generate features from NaFIRS data for resilience prediction models."""

    def __init__(self, processor: NaFIRSProcessor):
        """Initialize with a NaFIRSProcessor instance."""
        self.processor = processor

    def create_district_features(
        self,
        lookback_days: int = 365,
        forecast_date: datetime | None = None,
    ) -> pd.DataFrame:
        """
        Create historical features per district for day-ahead prediction.
        
        Args:
            lookback_days: Number of historical days to aggregate
            forecast_date: Reference date (default: today)
            
        Returns:
            DataFrame with district-level features
        """
        if forecast_date is None:
            forecast_date = datetime.now()

        start = forecast_date - timedelta(days=lookback_days)
        agg = self.processor.aggregate_by_district_time("D", start, forecast_date)

        if agg.empty:
            logger.warning(f"No NaFIRS data found in lookback window ({lookback_days} days)")
            return pd.DataFrame()

        # Group by district and aggregate across days
        features = agg.groupby(["NETWORK", "DISTRICT_ID"], as_index=False).agg({
            "FAULT_COUNT": ["sum", "mean", "std", "max"],
            "CUSTOMERS_AFFECTED_sum": ["sum", "mean"],
            "CUSTOMER_MINUTES_OFF_sum": ["sum", "mean"],
            "OUTAGE_DURATION_MIN_mean": ["mean", "max"],
            "OUTAGE_DURATION_MIN_max": "max",
        })

        # Flatten column names
        features.columns = [
            "_".join(col).strip("_") for col in features.columns.values
        ]

        return features

    def create_temporal_features(
        self,
        forecast_date: datetime | None = None,
    ) -> pd.DataFrame:
        """
        Create temporal features (time-of-year patterns, seasonality).
        
        Args:
            forecast_date: Reference date (default: today)
            
        Returns:
            DataFrame with temporal features
        """
        if forecast_date is None:
            forecast_date = datetime.now()

        # Calculate seasonal patterns in outages
        incidents = self.processor.incidents.copy()
        
        if "FAULT_START_TIME" not in incidents.columns:
            logger.warning("Cannot create temporal features: missing FAULT_START_TIME")
            return pd.DataFrame()

        incidents["MONTH"] = incidents["FAULT_START_TIME"].dt.month
        incidents["HOUR"] = incidents["FAULT_START_TIME"].dt.hour
        
        # Count faults by district and month
        monthly_pattern = incidents.groupby(
            ["NETWORK", "DISTRICT_ID", "MONTH"],
            as_index=False
        ).size().rename(columns={"size": "FAULT_COUNT"})

        return monthly_pattern


def load_and_process_nafirs(
    path: Path | None = None,
    lookback_days: int = 365,
) -> dict[str, Any]:
    """
    Convenience function to load NaFIRS and create features.
    
    Args:
        path: Path to NaFIRS data file (default: DEFAULT_PATH)
        lookback_days: Lookback window for feature calculation
        
    Returns:
        Dictionary containing processed data and feature dataframes
    """
    loader = NaFIRSLoader(path)
    incidents = loader.load()
    
    processor = NaFIRSProcessor(incidents)
    engine = NaFIRSFeatureEngine(processor)
    
    return {
        "incidents": incidents,
        "processor": processor,
        "district_features": engine.create_district_features(lookback_days),
        "temporal_features": engine.create_temporal_features(),
        "regional_outage_proportion": processor.regional_outage_proportion("D"),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Example usage
    try:
        result = load_and_process_nafirs()
        print(f"Loaded {len(result['incidents'])} incidents")
        print("\nDistrict features:")
        print(result["district_features"].head())
        print("\nRegional outage proportion:")
        print(result["regional_outage_proportion"].head())
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please provide NaFIRS data at data/raw/nafirs/lv_faults.csv.gz")
