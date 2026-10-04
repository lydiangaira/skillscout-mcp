import pandas as pd

df = pd.read_csv("data/raw/postings.csv")

print(df.shape)
print(df.columns.tolist())
print(df.isna().sum())
print(df.iloc[0].to_dict())
print(df["job_skills"].dropna().head(3).tolist())
print(df["job_level"].value_counts())
print(df["job_type"].value_counts())
print(df["company"].value_counts().head(5))