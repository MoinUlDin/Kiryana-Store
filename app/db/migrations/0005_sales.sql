-- Phase 4: bills. Customers / udhar / returns come in Phase 6 and add columns and tables to these.

CREATE TABLE bill_counter (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    last_bill_no INTEGER NOT NULL DEFAULT 0
);
INSERT INTO bill_counter(id, last_bill_no) VALUES (1, 0);

CREATE TABLE orders (
    id                  INTEGER PRIMARY KEY,
    bill_no             INTEGER NOT NULL UNIQUE,            -- gapless: taken inside the checkout transaction
    business_date       TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    cashier_id          INTEGER NOT NULL REFERENCES users(id),
    subtotal_paisa      INTEGER NOT NULL CHECK (subtotal_paisa >= 0),
    item_discount_paisa INTEGER NOT NULL DEFAULT 0 CHECK (item_discount_paisa >= 0),
    bill_discount_paisa INTEGER NOT NULL DEFAULT 0 CHECK (bill_discount_paisa >= 0),
    tax_paisa           INTEGER NOT NULL DEFAULT 0,
    rounding_paisa      INTEGER NOT NULL DEFAULT 0,
    payable_paisa       INTEGER NOT NULL CHECK (payable_paisa >= 0),
    status              TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('completed', 'voided')),
    voided_at           TEXT,
    voided_by           INTEGER REFERENCES users(id),
    void_reason         TEXT,
    note                TEXT,
    CHECK (status = 'completed' OR (voided_at IS NOT NULL AND void_reason IS NOT NULL)),
    -- the bill's arithmetic is enforced by the database itself
    CHECK (payable_paisa = subtotal_paisa - item_discount_paisa - bill_discount_paisa + rounding_paisa)
);
CREATE INDEX idx_orders_date    ON orders(business_date);
CREATE INDEX idx_orders_cashier ON orders(cashier_id, business_date);

CREATE TABLE order_lines (
    id                  INTEGER PRIMARY KEY,
    order_id            INTEGER NOT NULL REFERENCES orders(id),
    item_id             INTEGER REFERENCES items(id),       -- NULL for a Misc item
    is_misc             INTEGER NOT NULL DEFAULT 0 CHECK (is_misc IN (0, 1)),
    name_snapshot       TEXT NOT NULL,
    name_ur_snapshot    TEXT,
    unit_snapshot       TEXT NOT NULL,
    qty_milli           INTEGER NOT NULL CHECK (qty_milli > 0),
    unit_price_paisa    INTEGER NOT NULL CHECK (unit_price_paisa >= 0),
    cost_snapshot_paisa INTEGER NOT NULL DEFAULT 0 CHECK (cost_snapshot_paisa >= 0),  -- average cost when sold (for profit)
    entry_mode          TEXT NOT NULL DEFAULT 'qty' CHECK (entry_mode IN ('qty', 'amount')),
    gross_paisa         INTEGER NOT NULL CHECK (gross_paisa >= 0),
    discount_paisa      INTEGER NOT NULL DEFAULT 0 CHECK (discount_paisa >= 0),
    bill_discount_paisa INTEGER NOT NULL DEFAULT 0 CHECK (bill_discount_paisa >= 0),  -- this line's share of the bill discount
    line_total_paisa    INTEGER NOT NULL CHECK (line_total_paisa >= 0),
    tax_paisa           INTEGER NOT NULL DEFAULT 0,
    CHECK ((is_misc = 1 AND item_id IS NULL) OR (is_misc = 0 AND item_id IS NOT NULL)),
    CHECK (line_total_paisa = gross_paisa - discount_paisa - bill_discount_paisa)
);
CREATE INDEX idx_order_lines_order ON order_lines(order_id);
CREATE INDEX idx_order_lines_item  ON order_lines(item_id);

CREATE TABLE payments (
    id           INTEGER PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES orders(id),
    method       TEXT NOT NULL CHECK (method IN ('cash', 'card', 'wallet', 'udhar')),
    amount_paisa INTEGER NOT NULL CHECK (amount_paisa > 0),
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_payments_order ON payments(order_id);

-- Bills put on hold survive a restart or a power cut.
CREATE TABLE held_bills (
    id         INTEGER PRIMARY KEY,
    cashier_id INTEGER NOT NULL REFERENCES users(id),
    label      TEXT NOT NULL,
    cart_json  TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
