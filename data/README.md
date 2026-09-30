# Data

This project uses the **Lending Club loan dataset** (about 2.2M loans issued 2007-2018).

1. Go to Kaggle and search for **"All Lending Club loan data"** (by wordsforthewise).
2. Download it and find the file `accepted_2007_to_2018Q4.csv.gz`.
3. Place it here, **still zipped**: `data/raw/accepted_2007_to_2018Q4.csv.gz` (DuckDB reads .gz directly).

The raw file is excluded from Git via `.gitignore`.

Only 23 of the 150+ columns are used: fields known **at the time of application** plus the final loan status. Payment-history fields (total payments, recoveries, last payment date) are deliberately excluded because they would leak the outcome into the model.
