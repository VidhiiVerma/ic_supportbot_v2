from app.db import fetch_df

df = fetch_df("SELECT * FROM ic_implementation.ic_intelligence.payout_summary WHERE ` IC Earnings Value` = 9938")
if not df.empty:
    print("--- FOUND THE REPRESENTATIVE IN DATABASE ---")
    for col in df.columns:
        print(f"{col}: {df.iloc[0][col]}")
else:
    print("No representative found with exact IC Earnings Value = 9938")