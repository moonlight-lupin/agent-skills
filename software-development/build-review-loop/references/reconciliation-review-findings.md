# Phase 5.20 Reconciliation Review Findings

Learned from a reconciliation build phase (Aug 2026). Codex review caught 1 BLOCKING + 4 MAJOR issues in the reconciliation enhancement.

## BLOCKING: Multi-Invoice Suggestions Not Executable

Multi-invoice proposals stored `match_document_id = first_invoice_id` with `match_amount = combined_total`. `create_match` accepts only one document ID, and `confirm_match` applies the entire amount to that single invoice — normally failing because it exceeds the invoice's amount due.

**Fix:** Set `match_document_id = None` for multi-invoice proposals. They are suggestion-only — the user must create individual matches per invoice via `create_match`. The proposal includes `match_document_ids` (list) and `match_documents` (detail) so the user knows which invoices to match individually.

## MAJOR 1: Multi-Invoice Cross-Party Combinations

Combinations were built across ALL open invoices without grouping by `counter_party_id`. This could suggest combining unrelated customers' invoices and label the result with only the first customer's name.

**Fix:** Group invoices by `counter_party_id` before running combinations. Only combine invoices from the same party.

## MAJOR 2: Bank Balance Discards Opening Balance

`reconciliation_summary` summed transactions when history existed, discarding `se_accounts.balance`. This assumed a zero opening balance — an account with 1,000 balance and one 100 transaction reported 100 instead of 1,100.

**Fix:** Roll backward from the known current balance: `as_of_balance = current_balance - sum(transactions after as_of_date)`. This uses the imported current balance as the anchor point.

## MAJOR 3: Incompatible Count Units

`outstanding_count` counted bank entries (from `_bank_entries`) while `reconciled_count` counted match rows (`COUNT(*)`). Multiple confirmed matches on one entry made the counts incomparable.

**Fix:** `reconciled_count` uses `COUNT(DISTINCT rm.bank_entry_id)` — both counts now count bank entries.

## MAJOR 4: NULL Counter-Party GL Lines Omitted

`_gl_control_by_party` filtered `AND jl.counter_party_id IS NOT NULL`, omitting posted AR/AP control lines with no counter party. The tie-out could report "matched" despite an unallocated control-account balance.

**Fix:** `COALESCE(jl.counter_party_id, 0)` groups NULL lines under key 0. The reconciliation surfaces them as mismatches with `counter_party_name = "UNALLOCATED (NULL counter party)"`.

## General Patterns

- **Suggestion-only proposals:** when the execution path (create_match) only supports single documents, multi-document proposals must set the executable ID to None. The user sees the suggestion but cannot accidentally execute it.
- **Roll-backward balance calculation:** for as-of balance queries, anchor to the known current balance and subtract post-date transactions. Do not assume zero opening balance.
- **Count units must match:** when comparing counts in a summary, both counts must use the same unit (bank entries, not one entries and one match rows).
- **COALESCE for NULL foreign keys:** when grouping by a nullable FK, COALESCE to a sentinel (0) and label it clearly. Do not silently filter NULLs.
