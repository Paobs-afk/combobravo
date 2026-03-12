# ComboBravo System Report (Presentation Draft)

## 1) Project Title
**ComboBravo: Intelligent Market Basket Analysis System for Restaurant Recommendations**

## 2) Objective
Build a practical recommendation system that uses MBA metrics to drive decisions:
- bundle creation
- homepage ranking
- checkout cross-sell prompts
- promo recommendations
- item placement insights

## 3) Users and Business Context
- Owner: monitors high-impact bundles and promotions
- Cashier: receives checkout cross-sell suggestions
- Admin: imports datasets and retrains model
- Customer: sees better menu order and item combos

## 4) Data and Iterative Learning
- Storage: Supabase (`cb_datasets`, `cb_transactions`, `cb_item_margins`)
- Learning approach: 3 iterations (via `batch_no` or progressive transaction windows)
- Supports CSV upload via UI and direct Supabase import

## 5) Method and Intelligence Layer
- Frequent itemset mining: FP-Growth / Apriori (auto-selected)
- Rule metrics: support, confidence, lift, leverage, conviction
- Rule scoring: confidence + lift + support + stability + profit
- Drift detection: Jensen-Shannon distance
- Adaptive blending: long-term + recent rule view

## 6) Required Outputs Delivered
- Top bundles with explanation
- Top association rules with full measures
- Homepage ranking logic
- Frequently bought together simulation
- Cross-sell suggestions on cart add
- Promo recommendation generator
- Business insights including placement hints

## 7) UI and System Features
- React dashboard with KPI cards and visualizations
- Rule explorer with filters
- Segment dashboard (morning/lunch/dinner)
- Upload page and dataset switcher

## 8) Reliability Improvements
- Unified Python backend with Supabase-backed data source
- Environment-based configuration (`.env`) for database credentials
- Shared data access layer for API + MBA engine

## 9) Conclusion
ComboBravo converts MBA output into directly usable operational decisions and is ready for live demo with Supabase datasets.
