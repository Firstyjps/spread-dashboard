import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib
import os

def train_model(data_path: str, model_output_path: str):
    print(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path)
    
    # Drop non-feature columns
    features = [col for col in df.columns if col not in ['ts', 'target_short', 'target_long', 'future_min', 'future_max', 'symbol']]
    
    X = df[features]
    # We predict target_short (Max favorable movement for short)
    # The target is in decimals (e.g. 0.0012 for 12 bps). We multiply by 10000 to train the model to predict bps directly.
    y_short = df['target_short'] * 10000
    
    print(f"Features used ({len(features)}): {features}")
    
    # Time-series split
    X_train, X_test, y_train, y_test = train_test_split(X, y_short, test_size=0.2, shuffle=False)
    
    print(f"Training XGBoost Regressor on {len(X_train)} samples...")
    
    model_short = xgb.XGBRegressor(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        random_state=42,
        n_jobs=-1
    )
    
    model_short.fit(X_train, y_train)
    
    print("\nEvaluating Model...")
    y_pred = model_short.predict(X_test)
    
    mae = mean_absolute_error(y_test, y_pred)
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    
    print("Regression Metrics (Test Set - in bps):")
    print(f"Mean Absolute Error (MAE): {mae:.2f} bps")
    print(f"Mean Squared Error (MSE):  {mse:.2f} bps^2")
    print(f"R-squared (R2):            {r2:.4f}")
    
    os.makedirs(os.path.dirname(model_output_path) or ".", exist_ok=True)
    joblib.dump(model_short, model_output_path)
    
    # Save feature names
    joblib.dump(features, model_output_path.replace('.pkl', '_features.pkl'))
    
    print(f"\nModel saved to {model_output_path}")

if __name__ == "__main__":
    train_model(
        data_path=r"C:\Users\Firsty\train_data_hype_reg.csv",
        model_output_path=r"C:\Users\Firsty\OneDrive\เอกสาร\เดสก์ท็อป\spread-dashboard\backend\app\ai\models\xgboost_short_reg.pkl"
    )
