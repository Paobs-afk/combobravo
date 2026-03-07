# ComboBravo Project

Restaurant-themed Market-Basket Analysis (MBA) machine learning system with an evolving backend and a white/red operations dashboard.

Now includes:
- multi-page UI (Overview, Analysis, Rules, Upload)
- top navigation with shared dataset/iteration controls
- dataset upload for custom CSVs (auto split into 3 learning batches)

## 1) What This System Builds

- Ingests transactions from batch files (`batch1.csv` -> `batch3.csv`)
- Mines frequent patterns and association rules
- Auto-selects thresholds (`minsup`, `minconf`) using an evaluation loop
- Detects drift and adapts long-term vs recent model blending
- Outputs business-ready recommendations:
  - top bundles
  - full rule metrics
  - homepage item ranking
  - cross-sell/frequently-bought-together suggestions
  - promo recommendations
  - segment snapshots (morning/lunch/dinner)
  - top 10 meals overall

## 2) Business Context Chosen

- Scenario: Restaurant kiosk recommender backend
- Users: owner, cashier, admin, customer
- Decisions improved:
  - combo creation
  - checkout cross-sell prompts
  - homepage menu ordering
  - promotion strategy

## 3) Method Used and Difference from Apriori

- Primary engine: FP-Growth (auto-selected by density/size)
- Difference from Apriori:
  - Apriori generates many candidate itemsets level-by-level
  - FP-Growth compresses data into an FP-tree and avoids full candidate explosion
- Why this fits:
  - datasets are 1,000+ transactions with food baskets that can be dense
  - FP-Growth is faster and more memory-efficient at this scale

## 4) Real Self-Learning Mechanisms Implemented

- 3 learning iterations:
  - Iteration 1: batch1
  - Iteration 2: batch1 + batch2
  - Iteration 3: batch1 + batch2 + batch3
- Intelligent behavior included:
  - auto-threshold tuning with objective function
  - holdout hit-rate evaluation loop
  - rule scoring model (confidence/lift/support/stability/profit)
  - drift detection (Jensen-Shannon distance)
  - adaptive blend of long-term and recent rules
  - rule portfolio tracking (stable/emerging/fading)

## 5) Dataset Coverage

- Dataset A: >= 1,500 transactions, >= 16 unique items
- Dataset B: >= 1,500 transactions, >= 17 unique items
- Varying basket sizes and realistic restaurant items

## 6) NPM One-Command Run (Frontend + Backend)

From project root:

```bash
npm install
npm run dev
```

`npm run dev` does:

- regenerates iteration outputs for both datasets
- starts backend (`127.0.0.1:8000`)
- starts frontend (`localhost:5173`)

Optional first-time setup helpers:

```bash
npm run setup
npm run train
```

## 7) Alternative Batch Launcher

If you prefer double-click launch on Windows:

```bash
start_combobravo.bat
```

Open:

- Frontend: `http://localhost:5173`
- Backend: `http://127.0.0.1:8000`

## 8) API Endpoints

- `GET /api/datasets`
- `GET /api/recommendations/{dataset}/{iteration}`
- `GET /api/rules/{dataset}/{iteration}`
- `GET /api/menu-rank/{dataset}/{iteration}`
- `GET /api/segments/{dataset}/{iteration}`
- `GET /api/top-meals/{dataset}`
- `GET /api/overview/{dataset}/{iteration}`
- `POST /api/upload-dataset`
- `POST /api/run/{dataset}`
- `POST /api/run-all`

Use `dataset` as `A`, `B`, or uploaded dataset id (for example `custom_my_sales`).
