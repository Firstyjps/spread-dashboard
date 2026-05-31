import joblib
import pandas as pd
import os
import xgboost as xgb

class SpreadPredictor:
    def __init__(self, model_dir="."):
        self.model_short_path = os.path.join(model_dir, "xgboost_short_reg.pkl")
        self.features_short_path = os.path.join(model_dir, "xgboost_short_reg_features.pkl")
        
        self.model_short = None
        self.features_short = None
        
        self.load_models()
        
    def load_models(self):
        if os.path.exists(self.model_short_path) and os.path.exists(self.features_short_path):
            self.model_short = joblib.load(self.model_short_path)
            self.features_short = joblib.load(self.features_short_path)
            print(f"Loaded XGBoost Regression model.")
        else:
            print(f"Warning: Models not found in {self.model_short_path}")
            
    def predict_short(self, current_features: dict) -> float:
        """
        Predicts the maximum favorable spread movement (in bps) for a short position 
        within the next 2 hours.
        Returns the expected bps movement. If > 12 bps, we should short.
        """
        if not self.model_short or not self.features_short:
            return 0.0
            
        # Prepare DataFrame exactly as the model expects
        try:
            df = pd.DataFrame([current_features])
            X = df[self.features_short]
            # XGBRegressor outputs the prediction directly (we trained it to output bps)
            prediction_bps = self.model_short.predict(X)[0]
            return float(prediction_bps)
        except Exception as e:
            print(f"Prediction Error: {e}")
            return 0.0

if __name__ == "__main__":
    # Test inference
    predictor = SpreadPredictor(model_dir=os.path.dirname(__file__))
    
    # Dummy current market state
    dummy_market = {
        'exchange_spread_mid': 0.0050,
        'spread': 0.0050,
        'mean_10': 0.0048,
        'std_10': 0.0002,
        'zscore_10': 1.0,
        'min_10': 0.0046,
        'max_10': 0.0052,
        'dist_min_10': 0.0004,
        'dist_max_10': -0.0002,
        'mean_50': 0.0045,
        'std_50': 0.0003,
        'zscore_50': 1.66,
        'min_50': 0.0040,
        'max_50': 0.0055,
        'dist_min_50': 0.0010,
        'dist_max_50': -0.0005,
        'mean_300': 0.0040,
        'std_300': 0.0005,
        'zscore_300': 2.0,
        'min_300': 0.0030,
        'max_300': 0.0060,
        'dist_min_300': 0.0020,
        'dist_max_300': -0.0010,
        'roc_10': 0.05,
        'roc_50': 0.10
    }
    
    expected_profit_bps = predictor.predict_short(dummy_market)
    print(f"Predicted Short Profit: {expected_profit_bps:.2f} bps")
    
    fee_threshold = 7.2
    target_margin = 4.8
    total_hurdle = fee_threshold + target_margin
    
    if expected_profit_bps >= total_hurdle:
        print("ACTION: 🔥 EXECUTE SHORT SPREAD! 🔥")
    else:
        print("ACTION: Wait. Not enough predicted profit.")
