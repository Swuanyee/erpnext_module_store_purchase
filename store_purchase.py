# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cstr, flt, get_link_to_form, formatdate

import erpnext
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.stock.stock_ledger import make_sl_entries
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from erpnext.controllers.accounts_controller import AccountsController
from erpnext.accounts.utils import get_account_currency, get_fiscal_years, get_fiscal_year, validate_fiscal_year
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
)


class StorePurchase(Document):
	company_currency = 'MMK'

	def onload(self):
		self.get("__onload").make_payment_via_journal_entry = frappe.db.get_single_value(
			"Accounts Settings", "make_payment_via_journal_entry"
		)

	def set_status(self):
		status = {"0": "Draft", "1": "Submitted", "2": "Cancelled"}
		precision = self.precision("grand_total")

	def on_submit(self):
		self.make_gl_entries()
		self.docstatus = 1
		self.update_claimed_amount_in_employee_advance()
		self.update_stock_ledger()
		self.update_advances_status()

	def on_cancel(self):
		self.make_gl_entries(cancel=True)
		self.ignore_linked_doctypes = ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry")
		self.docstatus = 2
		self.update_claimed_amount_in_employee_advance()
		self.update_stock_ledger()
		self.update_advances_status()

	def make_gl_entries(self, cancel=False):
		if flt(self.grand_total > 0):
			gl_entries = self.get_gl_entries()
			make_gl_entries(gl_entries, cancel=cancel)

	def get_gl_entries(self):
		gl_entries = []
		payment_account = get_bank_cash_account(self.mode_of_payment, self.company).get("account")

		# credit to the payment account
		gl_entries.append(
			self.get_gl_dict(
				{
					"account": payment_account,
					"credit": self.total_claimed_amount,
					"credit_in_account_currency": self.total_claimed_amount,
					"voucher_no": self.name,
					"voucher_type": self.doctype,
					"remarks": self.remark,
				}
			)
		)

		# loop through the advance payments
		for data in self.advances:
			gl_entries.append(
				self.get_gl_dict(
					{
						"account": data.advance_account,
						"credit": data.allocated_amount,
						"credit_in_account_currency": data.allocated_amount,
						"party_type": "Employee",
						"party": self.employee,
						"against_voucher_type": "Employee Advance",
						"against_voucher": data.employee_advance,
						"voucher_no": self.name,
						"voucher_type": self.doctype,
					}
				)
			)

		# loop through store purchase details and make gl entries
		for data in self.store_purchase_detail:
			# supplier payable credit entry
			gl_entries.append(
				self.get_gl_dict(
					{
						"account": data.supplier_payable_account,
						"credit": data.amount,
						"credit_in_account_currency": data.amount,
						"against": data.item_debit_account,
						"party_type": "Supplier",
						"party": data.supplier,
						"voucher_type": self.doctype,
						"voucher_no": self.name,
						"remark": f'{data.qty} {data.stock_uom} of {data.item} from {data.supplier}'
					},
				)
			)

			# item debit entry
			gl_entries.append(
				self.get_gl_dict(
					{
						"account": 'General Store Inventory (Assets - MMK) - PPWD',
						"debit": data.amount,
						"debit_in_account_currency": data.amount,
						"against": data.supplier_payable_account,
						"party_type": 'Customer',
						"party": data.customer,
						"voucher_type": self.doctype,
						"voucher_no": self.name,
						"remark": f'{data.qty} {data.stock_uom} of {data.item} from {data.supplier}'
					}
				)
			)

			# liability clearing entry
			if data.paid_amount:
				gl_entries.append(
					self.get_gl_dict(
						{
							"account": data.supplier_payable_account,
							"debit": data.paid_amount,
							"debit_in_account_currency": data.paid_amount,
							"against": data.supplier_payable_account,
							"party_type": "Supplier",
							"party": data.supplier,
							"voucher_type": self.doctype,
							"voucher_no": self.name,
							"remark": f'Payment for {data.qty} {data.stock_uom} of {data.item} from {data.supplier}'
						}
					)
				)

				"""
				if data.immediate_use == 1:
					if data.reference_type and data.reference:
						reference_type = data.reference_type
						reference = data.reference
					else:
						reference_type = None
						reference = None
					gl_entries.append(
						self.get_gl_dict(
							{
								"account": 'General Store Inventory (Assets - MMK) - PPWD',
								"credit": data.amount,
								"credit_in_account_currency": data.amount,
								"party_type": 'Customer',
								"party": data.customer,
								"voucher_type": self.doctype,
								"voucher_no": self.name,
								"against_voucher_type": reference_type,
								"against_voucher": reference,
								"remark": f'{data.qty} {data.stock_uom} of {data.item} from {data.supplier}'
							}
						)
					)
					gl_entries.append(
						self.get_gl_dict(
							{
								"account": data.item_debit_account,
								"debit": data.amount,
								"debit_in_account_currency": data.amount,
								"party_type": "Customer",
								"party": data.customer,
								"voucher_type": self.doctype,
								"voucher_no": self.name,
								"against_voucher_type": reference_type,
								"against_voucher": reference,
								"cost_center": 'Main - PPWD',
								"remark": f'{data.qty} {data.stock_uom} of {data.item} from {data.supplier}'
							}
						)
					)
				"""
		return gl_entries

	def get_gl_dict(self, args, account_currency=None, item=None):
		"""this method populates the common properties of a gl entry record"""

		posting_date = args.get("posting_date") or self.get("posting_date")
		fiscal_years = get_fiscal_years(posting_date, company=self.company)
		if len(fiscal_years) > 1:
			frappe.throw(
				_("Multiple fiscal years exist for the date {0}. Please set company in Fiscal Year").format(
					formatdate(posting_date)
				)
			)
		else:
			fiscal_year = fiscal_years[0][0]

		gl_dict = frappe._dict(
			{
				"company": self.company,
				"posting_date": posting_date,
				"fiscal_year": fiscal_year,
				"voucher_type": self.doctype,
				"voucher_no": self.name,
				"remarks": self.get("remarks") or self.get("remark"),
				"debit": 0,
				"credit": 0,
				"debit_in_account_currency": 0,
				"credit_in_account_currency": 0,
				"is_opening": self.get("is_opening") or "No",
				"party_type": None,
				"party": None,
				"project": self.get("project"),
				"post_net_value": args.get("post_net_value"),
			}
		)

		accounting_dimensions = get_accounting_dimensions()
		dimension_dict = frappe._dict()

		for dimension in accounting_dimensions:
			dimension_dict[dimension] = self.get(dimension)
			if item and item.get(dimension):
				dimension_dict[dimension] = item.get(dimension)

		gl_dict.update(dimension_dict)
		gl_dict.update(args)

		if not account_currency:
			account_currency = get_account_currency(gl_dict.account)

		if gl_dict.account and self.doctype not in [
			"Journal Entry",
			"Period Closing Voucher",
			"Payment Entry",
			"Purchase Receipt",
			"Purchase Invoice",
			"Stock Entry",
		]:
			self.validate_account_currency(gl_dict.account, account_currency)

		if gl_dict.account and self.doctype not in [
			"Journal Entry",
			"Period Closing Voucher",
			"Payment Entry",
		]:
			set_balance_in_account_currency(
				gl_dict, account_currency, self.get("conversion_rate"), self.company_currency
			)

		return gl_dict

	def validate_account_currency(self, account, account_currency=None):
		valid_currency = [self.company_currency]
		if self.get("currency") and self.currency != self.company_currency:
			valid_currency.append(self.currency)

	def update_claimed_amount_in_employee_advance(self):
		for d in self.get("advances"):
			update_claimed_amount(d)

	def update_stock_ledger(self):
		"""
		This function updates the stock ledger based on the store purchase details in the ERPNext system.

		Steps:
		1. Create an empty list `sl_entries` to store the stock ledger entries.
		2. Call the `get_sle` function with `sl_entries` as an argument, which iterates through the `store_purchase_detail`,
		   checks if there is a warehouse associated with each detail, and calls the `get_sl_entries` function to construct
		   stock ledger entry dictionaries, which are subsequently added to the `sl_entries` list.
		3. If the document is being canceled (docstatus == 2), reverse the `sl_entries` list.
		4. Call the `make_sl_entries` function with the `sl_entries` list as an argument, which creates and submits a Stock
		   Entry document if immediate item usage is needed and handles the cancellation of Stock Entry documents when necessary.
		5. Create and update the stock ledger entries with the necessary information.
		"""
		sl_entries = []
		self.get_sle(sl_entries)

		if self.docstatus == 2:
			sl_entries.reverse()

		self.make_sl_entries(sl_entries)

	def make_sl_entries(self, sl_entries, allow_negative_stock=False, via_landed_cost_voucher=False):
		make_sl_entries(sl_entries, allow_negative_stock, via_landed_cost_voucher)

		##check if any of the item in store_purchase_detail is immedidate use
		immediate_use = False
		for d in self.get("store_purchase_detail"):
			if d.immediate_use:
				immediate_use = True
				# exit loop
				break
		if immediate_use == True and self.docstatus != 2:
			doc = frappe.new_doc("Stock Entry")
			doc.stock_entry_type = "Material Consumption for Manufacture"
			doc.company = self.company
			doc.posting_date = self.posting_date
			doc.voucher_no = self.name
			for d in self.get("store_purchase_detail"):
				if d.immediate_use and self.docstatus != 2:
					# doc.posting_time = self.posting_time
					doc.append("items", {
						"item_code": d.item,
						"qty": d.qty,
						"uom": d.stock_uom,
						"s_warehouse": d.warehouse,
						"party": d.customer,
						"party_doctype": d.reference_type,
						"party_reference": d.reference,
						"basic_rate": d.rate,
						"amount": d.amount,
						"expense_account": d.item_debit_account
					});
			doc.save()
			doc.submit()

	# frappe.db.get_value(doctype, filters, fieldname)

	def get_sle(self, sl_entries, finished_item_row=False):
		for d in self.get("store_purchase_detail"):
			if cstr(d.warehouse):
				sle = self.get_sl_entries(
					d,
					{
						"warehouse": cstr(d.warehouse),
						"actual_qty": flt(d.qty),
						"incoming_rate": flt(d.rate),
					},
				)
				# if cstr(d.s_warehouse) or (finished_item_row and d.name == finished_item_row.name):
				#	sle.recalculate_rate = 1
				sl_entries.append(sle)

	def get_sl_entries(self, d, args):
		sl_dict = frappe._dict(
			{
				"item_code": d.get("item", None),
				"warehouse": d.get("warehouse"),
				"posting_date": self.get("posting_date"),
				"posting_time": self.get("posting_time"),
				"fiscal_year": get_fiscal_year(self.get("posting_date"), company=self.get("company"))[0],
				"voucher_type": self.doctype,
				"voucher_no": self.name,
				"voucher_detail_no": d.name,
				"actual_qty": (self.docstatus == 1 and 1 or -1) * flt(d.get("stock_qty")),
				"stock_uom": d.stock_uom,
				# "stock_uom": frappe.db.get_value(
				#	"Item", args.get("item") or d.get("item"), "stock_uom"
				# ),
				"incoming_rate": d.get("rate"),
				"company": self.get("company"),
				# "batch_no": cstr(d.get("batch_no")).strip(),
				# "serial_no": d.get("serial_no"),
				# "project": d.get("project") or self.get("project"),
				"is_cancelled": 1 if self.docstatus == 2 else 0,
			}
		)

		sl_dict.update(args)
		# self.update_inventory_dimensions(d, sl_dict)

		return sl_dict

	def update_advances_status(self):
		# check if there are any allocated amount in advances
		for d in self.get("advances"):
			if d.allocated_amount > 0:
				# get the employee advance
				employee_advance = frappe.get_doc("Employee Advance", d.employee_advance)
				if employee_advance.claimed_amount == employee_advance.paid_amount:
					frappe.db.set_value("Employee Advance", d.employee_advance, "status", "Claimed")
				elif employee_advance.paid_amount == employee_advance.claimed_amount + employee_advance.return_amount \
					and employee_advance.returned_amount > 0 \
					and employee_advance.claimed_amount > 0:
					frappe.db.set_value("Employee Advance", d.employee_advance, "status", "Partly Claimed and Returned")
				elif employee_advance.paid_amount == employee_advance.return_amount:
					frappe.db.set_value("Employee Advance", d.employee_advance, "status", "Returned")
				elif employee_advance.paid_amount > employee_advance.claimed_amount + employee_advance.return_amount:
					frappe.db.set_value("Employee Advance", d.employee_advance, "status", "Paid")


@frappe.whitelist()
def get_supplier_account(supplier, company):
	supplier_account = frappe.db.get_value("Party Account",
										   {
											   "parent": supplier,
											   "parenttype": "Supplier",
											   "company": company
										   }, "account")
	return supplier_account


@frappe.whitelist()
def get_item_account(item, company):
	item_account = frappe.db.get_value("Item Default",
									   {
										   "parent": item,
										   "company": company
									   }, "expense_account")
	return item_account


@frappe.whitelist()
def get_advances(employee, advance_id=None):
	advance = frappe.qb.DocType("Employee Advance")

	query = frappe.qb.from_(advance).select(
		advance.name,
		advance.posting_date,
		advance.paid_amount,
		advance.claimed_amount,
		advance.advance_account,
	)

	if not advance_id:
		query = query.where(
			(advance.docstatus == 1)
			& (advance.employee == employee)
			& (advance.paid_amount > 0)
			& (advance.status.notin(["Claimed", "Returned", "Partly Claimed and Returned"]))
		)
	else:
		query = query.where(advance.name == advance_id)

	return query.run(as_dict=True)


def calculate_total_amount(self):
	self.total_claimed_amount = 0
	self.grand_total = 0
	for data in self.get("store_purchase_detail"):
		self.total_claimed_amount += data.allocated_amount
		self.grand_total += data.amount


def update_claimed_amount(data):
	claimed_amount = (
		frappe.db.sql(
			"""
		SELECT sum(ifnull(allocated_amount, 0))
		FROM `tabExpense Claim Advance` eca, `tabStore Purchase` sp
		WHERE
			eca.employee_advance = %s
			AND sp.name = eca.parent
			AND sp.docstatus=1
			AND eca.allocated_amount > 0
	""",
			data.employee_advance,
		)[0][0]
		or 0
	)
	print("claimed_amount", claimed_amount)
	frappe.db.set_value("Employee Advance", data.employee_advance, "claimed_amount", flt(claimed_amount))


def set_balance_in_account_currency(
	gl_dict, account_currency=None, conversion_rate=None, company_currency=None
):
	if (not conversion_rate) and (account_currency != company_currency):
		frappe.throw(
			_("Account: {0} with currency: {1} can not be selected").format(
				gl_dict.account, account_currency
			)
		)

	gl_dict["account_currency"] = (
		company_currency if account_currency == company_currency else account_currency
	)

	# set debit/credit in account currency if not provided
	if flt(gl_dict.debit) and not flt(gl_dict.debit_in_account_currency):
		gl_dict.debit_in_account_currency = (
			gl_dict.debit
			if account_currency == company_currency
			else flt(gl_dict.debit / conversion_rate, 2)
		)

	if flt(gl_dict.credit) and not flt(gl_dict.credit_in_account_currency):
		gl_dict.credit_in_account_currency = (
			gl_dict.credit
			if account_currency == company_currency
			else flt(gl_dict.credit / conversion_rate, 2)
		)
