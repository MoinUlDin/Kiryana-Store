-- Phase 3: purchase entry (stock-in). paid_paisa / paid_method / supplier_id are here from day one
-- so the v2 supplier ledger needs no data migration.

CREATE TABLE purchases (
    id            INTEGER PRIMARY KEY,
    supplier_id   INTEGER REFERENCES suppliers(id),
    invoice_no    TEXT,
    purchase_date TEXT NOT NULL,                       -- local business date, YYYY-MM-DD
    total_paisa   INTEGER NOT NULL CHECK (total_paisa >= 0),
    paid_paisa    INTEGER NOT NULL DEFAULT 0,
    paid_method   TEXT CHECK (paid_method IS NULL OR paid_method IN ('cash', 'card', 'wallet')),
    note          TEXT,
    created_by    INTEGER,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (paid_paisa >= 0 AND paid_paisa <= total_paisa),
    CHECK (paid_paisa = 0 OR paid_method IS NOT NULL)
);
CREATE INDEX idx_purchases_date ON purchases(purchase_date);
-- The same invoice from the same supplier cannot be entered twice (it would double the stock).
CREATE UNIQUE INDEX idx_purchases_invoice ON purchases(supplier_id, invoice_no)
    WHERE supplier_id IS NOT NULL AND invoice_no IS NOT NULL;

CREATE TABLE purchase_lines (
    id               INTEGER PRIMARY KEY,
    purchase_id      INTEGER NOT NULL REFERENCES purchases(id),
    item_id          INTEGER NOT NULL REFERENCES items(id),
    qty_milli        INTEGER NOT NULL CHECK (qty_milli > 0),
    cost_paisa       INTEGER NOT NULL CHECK (cost_paisa >= 0),   -- per base unit
    line_total_paisa INTEGER NOT NULL CHECK (line_total_paisa >= 0),
    expiry_date      TEXT,
    batch_id         INTEGER REFERENCES item_batches(id),
    avg_cost_before  INTEGER NOT NULL DEFAULT 0,
    avg_cost_after   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_purchase_lines_purchase ON purchase_lines(purchase_id);
CREATE INDEX idx_purchase_lines_item     ON purchase_lines(item_id);

ALTER TABLE item_batches ADD COLUMN purchase_line_id INTEGER REFERENCES purchase_lines(id);
