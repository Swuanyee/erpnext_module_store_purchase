# Store Purchase Document

This document handles Store Purchase functionalities for a teak furniture and saw mill. The main features include creating and cancelling Store Purchase records, updating GL entries, Employee Advance records, and Stock Ledger records.

## Key Classes and Methods

### StorePurchase (class)

The StorePurchase class represents a store purchase document and contains the following key methods:

- onload: Sets `make_payment_via_journal_entry` from the Accounts Settings.
- set_status: Sets the document's status.
- on_submit: Handles operations upon submission, including creating GL entries, updating claims in Employee Advance, and updating the stock ledger.
- on_cancel: Handles operations on cancellation, including creating canceling GL entries, updating claims in Employee Advance, and updating the stock ledger.
- make_gl_entries: Creates GL entries for submitted store purchases if the grand total is greater than 0.
- get_gl_entries: Constructs GL entries for the store purchase by appending specific entries for payment account, advance payments, supplier payable, item debit, and liability clearing.
- get_gl_dict: Populates common properties of a GL entry record and returns it as a dictionary.
- validate_account_currency: Checks if the account currency is valid.
- update_claimed_amount_in_employee_advance: Updates claimed amounts in Employee Advance records.
- update_stock_ledger: Updates the stock ledger based on store purchase details.
- make_sl_entries: Creates and submits a Stock Entry document if immediate item usage is needed.
- get_sle: Gathers stock ledger entries for the document.
- get_sl_entries: Constructs a stock ledger entry dictionary.
- update_advances_status: Updates the status of allocated amounts in advance records.

## Usage

To use this document in ERPNext, do the following:

1. Create a new folder named `store_purchase` in `frappe-bench/apps/erpnext/erpnext/stock/doctype/`.
2. Place the code within this folder into it

After taking these steps, the Store Purchase module will be integrated into your ERPNext system.
