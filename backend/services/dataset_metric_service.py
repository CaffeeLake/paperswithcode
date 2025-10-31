"""
Dataset-Metric service for managing relationships between datasets and metrics.

This service provides methods for managing which metrics are allowed for each dataset,
and validates evaluation submissions against these relationships.
"""

from typing import List, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.models.database import (
    Dataset as DBDataset,
    Metric as DBMetric,
    DatasetMetric as DBDatasetMetric,
)
from backend.models.api import DatasetMetricLink, DatasetMetrics
from backend.utils.exceptions import DatabaseError


class DatasetMetricService:
    """Service class for dataset-metric relationship operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_dataset_metrics(self, dataset_id: int) -> DatasetMetrics:
        """
        Get all allowed metrics for a dataset.

        Args:
            dataset_id: Dataset ID

        Returns:
            DatasetMetrics object with list of allowed metrics

        Raises:
            DatabaseError: If database query fails
            ValueError: If dataset not found
        """
        try:
            # Check if dataset exists
            dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            if not dataset:
                raise ValueError(f"Dataset with ID {dataset_id} not found")

            # Get all metrics linked to this dataset
            links = (
                self.db.query(DBDatasetMetric, DBMetric)
                .join(DBMetric, DBDatasetMetric.metric_id == DBMetric.id)
                .filter(DBDatasetMetric.dataset_id == dataset_id)
                .all()
            )

            # Build response
            metric_links = []
            for link, metric in links:
                metric_link = DatasetMetricLink(
                    dataset_id=str(dataset_id),
                    metric_id=str(metric.id),
                    metric_name=metric.name,
                    metric_direction=metric.direction,
                    created_at=link.created_at,
                )
                metric_links.append(metric_link)

            return DatasetMetrics(
                dataset_id=str(dataset_id),
                dataset_name=dataset.name,
                metrics=metric_links,
            )

        except ValueError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve dataset metrics: {str(e)}")

    def get_allowed_metric_names(self, dataset_id: int) -> Set[str]:
        """
        Get set of allowed metric names for a dataset.

        Args:
            dataset_id: Dataset ID

        Returns:
            Set of metric names (e.g., {'AP', 'AP50', 'AP75'})

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Query for metric names linked to this dataset
            metric_names = (
                self.db.query(DBMetric.name)
                .join(DBDatasetMetric, DBMetric.id == DBDatasetMetric.metric_id)
                .filter(DBDatasetMetric.dataset_id == dataset_id)
                .all()
            )

            return {name[0] for name in metric_names}

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve allowed metric names: {str(e)}")

    def validate_metrics_for_dataset(
        self, dataset_id: int, metric_keys: List[str], best_metric: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that all provided metrics are allowed for the dataset.

        Args:
            dataset_id: Dataset ID
            metric_keys: List of metric names from evaluation (keys from metrics dict)
            best_metric: Optional best_metric field to validate

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if all metrics are valid
            - (False, error_message) if validation fails

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Get allowed metrics for this dataset
            allowed_metrics = self.get_allowed_metric_names(dataset_id)

            # If no metrics are linked to the dataset, allow all metrics
            # (for backwards compatibility during migration)
            if not allowed_metrics:
                return True, None

            # Check all provided metrics
            invalid_metrics = [m for m in metric_keys if m not in allowed_metrics]

            if invalid_metrics:
                allowed_list = ", ".join(sorted(allowed_metrics))
                invalid_list = ", ".join(invalid_metrics)
                error_msg = (
                    f"Invalid metrics for this dataset: {invalid_list}. "
                    f"Allowed metrics: {allowed_list}"
                )
                return False, error_msg

            # Validate best_metric if provided
            if best_metric and best_metric not in allowed_metrics:
                allowed_list = ", ".join(sorted(allowed_metrics))
                error_msg = (
                    f"Invalid best_metric '{best_metric}' for this dataset. "
                    f"Allowed metrics: {allowed_list}"
                )
                return False, error_msg

            return True, None

        except DatabaseError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to validate metrics: {str(e)}")

    def add_metric_to_dataset(
        self, dataset_id: int, metric_name: str
    ) -> DatasetMetricLink:
        """
        Add a metric to a dataset's allowed metrics list.

        Args:
            dataset_id: Dataset ID
            metric_name: Metric name (e.g., 'AP', 'WER')

        Returns:
            DatasetMetricLink object

        Raises:
            ValueError: If dataset or metric not found, or link already exists
            DatabaseError: If database operation fails
        """
        try:
            # Check if dataset exists
            dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            if not dataset:
                raise ValueError(f"Dataset with ID {dataset_id} not found")

            # Check if metric exists
            metric = (
                self.db.query(DBMetric).filter(DBMetric.name == metric_name).first()
            )
            if not metric:
                raise ValueError(f"Metric '{metric_name}' not found")

            # Check if link already exists
            existing_link = (
                self.db.query(DBDatasetMetric)
                .filter(
                    and_(
                        DBDatasetMetric.dataset_id == dataset_id,
                        DBDatasetMetric.metric_id == metric.id,
                    )
                )
                .first()
            )

            if existing_link:
                raise ValueError(
                    f"Metric '{metric_name}' is already linked to dataset {dataset_id}"
                )

            # Create the link
            new_link = DBDatasetMetric(dataset_id=dataset_id, metric_id=metric.id)
            self.db.add(new_link)
            self.db.commit()
            self.db.refresh(new_link)

            return DatasetMetricLink(
                dataset_id=str(dataset_id),
                metric_id=str(metric.id),
                metric_name=metric.name,
                metric_direction=metric.direction,
                created_at=new_link.created_at,
            )

        except ValueError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to add metric to dataset: {str(e)}")

    def remove_metric_from_dataset(self, dataset_id: int, metric_name: str) -> bool:
        """
        Remove a metric from a dataset's allowed metrics list.

        Args:
            dataset_id: Dataset ID
            metric_name: Metric name (e.g., 'AP', 'WER')

        Returns:
            True if removed successfully

        Raises:
            ValueError: If dataset, metric, or link not found
            DatabaseError: If database operation fails
        """
        try:
            # Check if dataset exists
            dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            if not dataset:
                raise ValueError(f"Dataset with ID {dataset_id} not found")

            # Check if metric exists
            metric = (
                self.db.query(DBMetric).filter(DBMetric.name == metric_name).first()
            )
            if not metric:
                raise ValueError(f"Metric '{metric_name}' not found")

            # Find and delete the link
            link = (
                self.db.query(DBDatasetMetric)
                .filter(
                    and_(
                        DBDatasetMetric.dataset_id == dataset_id,
                        DBDatasetMetric.metric_id == metric.id,
                    )
                )
                .first()
            )

            if not link:
                raise ValueError(
                    f"Metric '{metric_name}' is not linked to dataset {dataset_id}"
                )

            self.db.delete(link)
            self.db.commit()

            return True

        except ValueError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to remove metric from dataset: {str(e)}")

    def set_dataset_metrics(
        self, dataset_id: int, metric_names: List[str]
    ) -> DatasetMetrics:
        """
        Set all allowed metrics for a dataset (replaces existing).

        Args:
            dataset_id: Dataset ID
            metric_names: List of metric names to allow

        Returns:
            DatasetMetrics object with updated metrics

        Raises:
            ValueError: If dataset not found or any metric not found
            DatabaseError: If database operation fails
        """
        try:
            # Check if dataset exists
            dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            if not dataset:
                raise ValueError(f"Dataset with ID {dataset_id} not found")

            # Check if all metrics exist
            metrics = (
                self.db.query(DBMetric).filter(DBMetric.name.in_(metric_names)).all()
            )

            if len(metrics) != len(metric_names):
                found_names = {m.name for m in metrics}
                missing_names = set(metric_names) - found_names
                raise ValueError(
                    f"The following metrics were not found: {', '.join(missing_names)}"
                )

            # Delete all existing links for this dataset
            self.db.query(DBDatasetMetric).filter(
                DBDatasetMetric.dataset_id == dataset_id
            ).delete()

            # Create new links
            for metric in metrics:
                new_link = DBDatasetMetric(dataset_id=dataset_id, metric_id=metric.id)
                self.db.add(new_link)

            self.db.commit()

            # Return updated metrics
            return self.get_dataset_metrics(dataset_id)

        except ValueError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to set dataset metrics: {str(e)}")
