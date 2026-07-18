# Shopify Inventory Tracker Rules

## Sales Reports and Analytics
- **Strict Event Filtering**: When calculating sales, revenue, items sold, or transaction histories, you must ONLY count/sum events with type `Sale` or `Sold Out`.
- **Exclude Non-Sales**: NEVER include `Restock` (inventory increases) or `New Arrival` (new product additions) events in sales revenue or purchase quantities. These are stock adjustments, not customer purchases.
