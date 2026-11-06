-- Phase 2: catalog and stock.

CREATE TABLE categories (
    id        INTEGER PRIMARY KEY,
    name_en   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name_ur   TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE brands (
    id        INTEGER PRIMARY KEY,
    name_en   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name_ur   TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- Basic in v1 (purchase entry picks from it); the supplier ledger arrives in v2.
CREATE TABLE suppliers (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone     TEXT,
    address   TEXT,
    note      TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- Prices are per BASE unit (per kg, per litre, per piece), in paisa.
-- Quantities are thousandths of the base unit (2.5 kg = 2500).
-- There is deliberately NO check that cost <= sale price: the client wants a warning, not a block.
CREATE TABLE items (
    id              INTEGER PRIMARY KEY,
    name_en         TEXT NOT NULL,
    name_ur         TEXT,
    short_code      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    barcode         TEXT UNIQUE,
    category_id     INTEGER REFERENCES categories(id),
    brand_id        INTEGER REFERENCES brands(id),
    supplier_id     INTEGER REFERENCES suppliers(id),
    unit            TEXT NOT NULL CHECK (unit IN ('piece', 'kg', 'litre')),
    allow_fraction  INTEGER NOT NULL DEFAULT 0 CHECK (allow_fraction IN (0, 1)),
    cost_paisa      INTEGER NOT NULL DEFAULT 0 CHECK (cost_paisa >= 0),
    sale_paisa      INTEGER NOT NULL CHECK (sale_paisa >= 0),
    tax_bp          INTEGER CHECK (tax_bp IS NULL OR tax_bp BETWEEN 0 AND 10000),
    stock_milli     INTEGER NOT NULL DEFAULT 0 CHECK (stock_milli >= 0),
    low_stock_milli INTEGER NOT NULL DEFAULT 0 CHECK (low_stock_milli >= 0),
    image_path      TEXT,
    search_key      TEXT NOT NULL DEFAULT '',
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_items_name     ON items(name_en COLLATE NOCASE);
CREATE INDEX idx_items_category ON items(category_id);
CREATE INDEX idx_items_active   ON items(is_active);

-- Every receipt of stock is a batch (opening stock, purchases, upward corrections).
-- Invariant: items.stock_milli = SUM(qty_left_milli) over the item's batches.
CREATE TABLE item_batches (
    id             INTEGER PRIMARY KEY,
    item_id        INTEGER NOT NULL REFERENCES items(id),
    source         TEXT NOT NULL CHECK (source IN ('purchase', 'opening', 'adjustment')),
    qty_in_milli   INTEGER NOT NULL CHECK (qty_in_milli > 0),
    qty_left_milli INTEGER NOT NULL CHECK (qty_left_milli >= 0 AND qty_left_milli <= qty_in_milli),
    cost_paisa     INTEGER NOT NULL CHECK (cost_paisa >= 0),
    expiry_date    TEXT,
    received_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_batches_item ON item_batches(item_id, expiry_date);

-- Append-only history. Invariant: items.stock_milli = SUM(qty_milli) over the item's movements.
CREATE TABLE stock_movements (
    id         INTEGER PRIMARY KEY,
    item_id    INTEGER NOT NULL REFERENCES items(id),
    batch_id   INTEGER REFERENCES item_batches(id),
    kind       TEXT NOT NULL CHECK (kind IN ('opening', 'purchase', 'sale', 'return_restock', 'void_restore',
                                             'adjust_damage', 'adjust_loss', 'adjust_expiry', 'adjust_count', 'quick_fix')),
    qty_milli  INTEGER NOT NULL CHECK (qty_milli <> 0),
    ref_type   TEXT,
    ref_id     INTEGER,
    reason     TEXT,
    user_id    INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_movements_item ON stock_movements(item_id, created_at);

CREATE TRIGGER stock_movements_no_update BEFORE UPDATE ON stock_movements
BEGIN SELECT RAISE(ABORT, 'stock_movements is append-only'); END;
CREATE TRIGGER stock_movements_no_delete BEFORE DELETE ON stock_movements
BEGIN SELECT RAISE(ABORT, 'stock_movements is append-only'); END;
