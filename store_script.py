import frappe

import frappe

frappe.connect(site="erpvagrant")
sl_entry = frappe.db.sql("SELECT name FROM `tabStock Entry` WHERE voucher_no=%s AND docstatus=1", "MAT-STE-2023-00085-1")
print(sl_entry)
frappe.destroy()
