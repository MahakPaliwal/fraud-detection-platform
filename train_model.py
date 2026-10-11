import pandas as pd
import pickle
import json
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report

# 1. Load dataset
df = pd.read_csv("creditcard.csv")

# 2. Split features/target
X = df.drop(columns=["Class"])
y = df["Class"]

from sklearn.preprocessing import StandardScaler

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
X_test_raw = X_test.copy()
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# Convert back to DataFrames so .head() and column-based code still works
X_train = pd.DataFrame(X_train_scaled, columns=X_train.columns, index=X_train.index)
X_test = pd.DataFrame(X_test_scaled, columns=X_test.columns, index=X_test.index)

model = LogisticRegression(max_iter=1000, class_weight="balanced")
model.fit(X_train, y_train)

# Quick sanity check
preds = model.predict(X_test)
print(classification_report(y_test, preds))
with open("scaler.pkl", "wb") as f:
    pickle.dump(scaler, f)
# 4. Save the model
with open("model.pkl", "wb") as f:
    pickle.dump(model, f)

# 5. Save a handful of sample transactions (for Step 2's stream simulator)
sample_fraud = X_test_raw[y_test == 1].head(5)
sample_normal = X_test_raw[y_test == 0].head(15)
samples = pd.concat([sample_fraud, sample_normal]).to_dict(orient="records")

with open("sample_transactions.json", "w") as f:
    json.dump(samples, f, indent=2)

print("Saved model.pkl and sample_transactions.json")