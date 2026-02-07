"""
Model Training Pipeline
"""
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional

from ..data.loader import DataLoader
from ..data.features import FeatureEngineer
from .forecaster import DemandForecaster
from ..config import settings


class ModelTrainer:
    """End-to-end training pipeline"""

    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or settings.data_path
        self.loader = DataLoader(self.data_path)
        self.feature_engineer = FeatureEngineer()
        self.forecaster = DemandForecaster()

    def run_training_pipeline(
        self,
        save_model: bool = True,
        verbose: bool = True
    ) -> dict:
        """Run the complete training pipeline"""
        results = {
            "started_at": datetime.now().isoformat(),
            "data_path": str(self.data_path),
            "steps": []
        }

        # Step 1: Load data
        if verbose:
            print("Step 1: Loading data...")

        try:
            tables = self.loader.load_all_tables()
            results["steps"].append({
                "step": "load_data",
                "status": "success",
                "tables_loaded": len(tables)
            })
        except Exception as e:
            results["steps"].append({
                "step": "load_data",
                "status": "error",
                "error": str(e)
            })
            return results

        # Step 2: Get daily sales aggregation
        if verbose:
            print("Step 2: Aggregating daily sales...")

        try:
            daily_sales = self.loader.get_daily_sales()
            if verbose:
                print(f"   Found {len(daily_sales):,} daily sales records")
                print(f"   Unique items: {daily_sales['item_title'].nunique()}")
                print(f"   Date range: {daily_sales['date'].min()} to {daily_sales['date'].max()}")

            results["steps"].append({
                "step": "aggregate_sales",
                "status": "success",
                "records": len(daily_sales),
                "unique_items": daily_sales["item_title"].nunique()
            })
        except Exception as e:
            results["steps"].append({
                "step": "aggregate_sales",
                "status": "error",
                "error": str(e)
            })
            return results

        # Step 3: Feature engineering
        if verbose:
            print("Step 3: Engineering features...")

        try:
            featured_df = self.feature_engineer.build_forecast_features(
                daily_sales,
                target_col="total_quantity",
                group_col="item_title",
                date_col="date"
            )

            if verbose:
                print(f"   Created {len(self.feature_engineer.feature_columns)} features")

            results["steps"].append({
                "step": "feature_engineering",
                "status": "success",
                "features_created": len(self.feature_engineer.feature_columns)
            })
        except Exception as e:
            results["steps"].append({
                "step": "feature_engineering",
                "status": "error",
                "error": str(e)
            })
            return results

        # Step 4: Prepare training data
        if verbose:
            print("Step 4: Preparing training data...")

        try:
            X, y = self.feature_engineer.prepare_training_data(
                featured_df,
                target_col="total_quantity"
            )

            if verbose:
                print(f"   Training samples: {len(X):,}")
                print(f"   Features: {X.shape[1]}")

            results["steps"].append({
                "step": "prepare_data",
                "status": "success",
                "samples": len(X),
                "features": X.shape[1]
            })
        except Exception as e:
            results["steps"].append({
                "step": "prepare_data",
                "status": "error",
                "error": str(e)
            })
            return results

        # Step 5: Train model
        if verbose:
            print("Step 5: Training XGBoost model...")

        try:
            metrics = self.forecaster.train(X, y)

            if verbose:
                print(f"   MAE: {metrics['mae']:.2f}")
                print(f"   RMSE: {metrics['rmse']:.2f}")
                print(f"   R2: {metrics['r2']:.3f}")

            results["steps"].append({
                "step": "train_model",
                "status": "success",
                "metrics": {
                    "mae": round(metrics["mae"], 2),
                    "rmse": round(metrics["rmse"], 2),
                    "r2": round(metrics["r2"], 3)
                }
            })
            results["metrics"] = results["steps"][-1]["metrics"]
        except Exception as e:
            results["steps"].append({
                "step": "train_model",
                "status": "error",
                "error": str(e)
            })
            return results

        # Step 6: Save model
        if save_model:
            if verbose:
                print("Step 6: Saving model...")

            try:
                model_path = self.forecaster.save()

                if verbose:
                    print(f"   Saved to: {model_path}")

                results["steps"].append({
                    "step": "save_model",
                    "status": "success",
                    "path": str(model_path)
                })
                results["model_path"] = str(model_path)
            except Exception as e:
                results["steps"].append({
                    "step": "save_model",
                    "status": "error",
                    "error": str(e)
                })

        results["completed_at"] = datetime.now().isoformat()
        results["status"] = "success"

        if verbose:
            print("\nTraining complete!")

        return results

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """Get feature importance from trained model"""
        return self.forecaster.get_feature_importance(top_n)

    def generate_forecasts(
        self,
        days_ahead: int = 7,
        item_filter: Optional[str] = None
    ) -> pd.DataFrame:
        """Generate forecasts for future days"""
        self.loader.load_all_tables()
        daily_sales = self.loader.get_daily_sales()
        featured_df = self.feature_engineer.build_forecast_features(
            daily_sales,
            target_col="total_quantity",
            group_col="item_title",
            date_col="date"
        )

        return self.forecaster.forecast_future(
            featured_df,
            self.feature_engineer,
            days_ahead=days_ahead,
            item_filter=item_filter
        )


def train_model(data_path: Optional[str] = None, verbose: bool = True) -> dict:
    """Convenience function to train model"""
    path = Path(data_path) if data_path else None
    trainer = ModelTrainer(path)
    return trainer.run_training_pipeline(verbose=verbose)


if __name__ == "__main__":
    results = train_model(verbose=True)
    print("\nResults:", results)
