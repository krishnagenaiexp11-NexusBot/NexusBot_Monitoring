"""
engine/data_pipeline.py
V2 Data Pipeline — production-grade ingestion layer for NexusBot V2.

Responsibilities:
  - Load CSV from Streamlit upload, file path, or raw DataFrame
  - Auto-normalize MT5/broker column name variants
  - Validate canonical OHLCV schema (after normalization)
  - Detect timeframe from timestamp deltas
  - Build H1 and M15 resampled views for regime/MTF engines
  - Return validation summary + normalization report for UI display

This is the single source-of-truth ingestion layer.
All downstream engines receive canonical schema only.
"""
import io
import pandas as pd

from utils.validation import (
    validate_ohlcv,
    get_dataset_summary,
    get_normalization_report,
    DataValidationError,
)
from utils.timeframes import detect_timeframe, resample_to_h1, resample_to_m15


class DataPipeline:
    """
    Handles data loading, normalization, validation, and resampling for app_v2.
    Supports: Streamlit UploadedFile, filesystem paths, raw DataFrames.

    Accepted formats (auto-detected, no manual edits needed):
      - MT5 broker CSV exports with Date/Time separate columns
      - MT5 exports with TickVol, tick_volume, or Volume column names
      - Standard OHLCV CSVs with any casing of column names
      - NexusBot legacy datasets
    """

    def load_from_upload(self, uploaded_file) -> dict:
        """
        Loads a Streamlit UploadedFile object.

        Returns the pipeline output dict (see _process docstring).
        Raises DataValidationError with a descriptive message on failure.
        """
        try:
            raw_bytes = uploaded_file.read()
            # Try common separators: comma first, then semicolon (MT5 default in some locales)
            df = self._read_csv_robust(io.BytesIO(raw_bytes))
        except DataValidationError:
            raise
        except Exception as exc:
            raise DataValidationError(f"Cannot read CSV file: {exc}")

        return self._process(df, name=getattr(uploaded_file, "name", "dataset.csv"))

    def load_from_path(self, path: str) -> dict:
        """Loads a CSV from a filesystem path."""
        try:
            with open(path, "rb") as f:
                df = self._read_csv_robust(f)
        except DataValidationError:
            raise
        except Exception as exc:
            raise DataValidationError(f"Cannot read CSV at '{path}': {exc}")
        return self._process(df, name=path)

    def load_from_dataframe(self, df: pd.DataFrame, name: str = "dataframe") -> dict:
        """Accepts a pre-loaded DataFrame."""
        return self._process(df.copy(), name=name)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _read_csv_robust(self, file_obj) -> pd.DataFrame:
        """
        Tries to read CSV with multiple separators / encodings.
        Priority: comma → semicolon → tab.
        Falls back to latin-1 encoding if UTF-8 fails.
        """
        errors = []

        # Read all bytes so we can retry without re-reading file_obj
        if hasattr(file_obj, "read"):
            raw = file_obj.read()
            if isinstance(raw, str):
                raw = raw.encode("utf-8", errors="replace")
        else:
            raw = file_obj

        for sep in (",", ";", "\t"):
            for encoding in ("utf-8", "latin-1", "utf-8-sig"):
                try:
                    df = pd.read_csv(
                        io.BytesIO(raw),
                        sep=sep,
                        encoding=encoding,
                        # Skip comment lines (some MT5 exports have header comments)
                        comment="#",
                        # Avoid treating empty strings as NaN in column name detection
                        skipinitialspace=True,
                    )
                    # Must have at least 3 columns to be a real OHLCV file
                    if df.shape[1] >= 3 and len(df) >= 10:
                        return df
                except Exception as exc:
                    errors.append(f"sep={sep!r} enc={encoding}: {exc}")

        raise DataValidationError(
            f"Could not parse CSV with any separator (comma, semicolon, tab). "
            f"Errors: {'; '.join(errors[:3])}"
        )

    def _process(self, df: pd.DataFrame, name: str) -> dict:
        """
        Full pipeline:
          1. Capture normalization report from raw columns
          2. Validate + normalize → canonical schema
          3. Detect timeframe
          4. Build H1 / M15 resampled views
          5. Build validation summary with row counts

        Returns:
            {
                "df"               : pd.DataFrame   — canonical validated data
                "h1_df"            : pd.DataFrame   — H1 resampled view
                "m15_df"           : pd.DataFrame   — M15 resampled view
                "timeframe"        : str             — e.g. "H1", "M15"
                "summary"          : dict            — row counts, date range, etc.
                "normalization"    : dict            — column mapping report
                "name"             : str             — source filename
            }
        """
        rows_loaded = len(df)

        # ── Capture normalization report BEFORE validation mutates the df ─────
        norm_report = get_normalization_report(df)
        norm_report["rows_loaded"] = rows_loaded

        # ── Validate + normalize ──────────────────────────────────────────────
        df = validate_ohlcv(df)

        rows_after   = len(df)
        rows_removed = rows_loaded - rows_after

        # ── Timeframe detection ───────────────────────────────────────────────
        timeframe = detect_timeframe(df)

        # ── H1 / M15 resampled views ──────────────────────────────────────────
        h1_df  = resample_to_h1(df)  if len(df) >= 50 else df.copy()
        m15_df = resample_to_m15(df) if len(df) >= 30 else df.copy()

        if len(h1_df) < 10:
            h1_df = df.copy()
        if len(m15_df) < 10:
            m15_df = df.copy()

        # ── Validation summary ────────────────────────────────────────────────
        base_summary = get_dataset_summary(df)
        summary = {
            **base_summary,
            "rows_loaded":   rows_loaded,
            "rows_removed":  rows_removed,
            "timeframe_guess": timeframe,
            "date_range":    f"{base_summary.get('start', '')[:10]} → {base_summary.get('end', '')[:10]}",
        }

        # Add to normalization report
        norm_report["rows_removed"]    = rows_removed
        norm_report["timeframe_guess"] = timeframe

        return {
            "df":            df,
            "h1_df":         h1_df,
            "m15_df":        m15_df,
            "timeframe":     timeframe,
            "summary":       summary,
            "normalization": norm_report,
            "name":          name,
        }
