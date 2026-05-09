-- Ajoute user_id aux factures pour tracer qui a ajouté chaque facture
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);
