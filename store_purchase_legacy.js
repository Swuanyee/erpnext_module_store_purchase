// Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Store Purchase', {
	refresh: function(frm) {
		frm.fields_dict['store_purchase_detail'].grid.get_field('item_debit_account').get_query = function(doc, cdt, cdn) {
			return {
				filters: [
					['root_type', '=', 'Expense'],
					['company', '=', doc.company],
					['account_currency', '=', 'MMK'],
					['is_group', '=', '0']
				]
			}
		}
		frm.fields_dict['store_purchase_detail'].grid.get_field('supplier_payable_account').get_query = function(doc, cdt, cdn) {
			return {
				filters: [
					['root_type', '=', 'Liability'],
					['company', '=', doc.company],
					['account_currency', '=', 'MMK'],
					['is_group', '=', '0']
				]
			}
		}
		frm.set_value('total_claimed_amount', frm.doc.total_amount - frm.doc.total_advance_amount);
	},
	employee: function(frm) {
		frm.events.get_advances(frm);
	},
	get_advances: function(frm) {
		frappe.model.clear_table(frm.doc, "advances");
		if (frm.doc.employee) {
			return frappe.call({
			method: "erpnext.stock.doctype.store_purchase.store_purchase.get_advances",
				args: {
					employee: frm.doc.employee
				},
				callback: function(r, rt) {

					if(r.message) {
						$.each(r.message, function(i, d) {
							var row = frappe.model.add_child(frm.doc, "Expense Claim Advance", "advances");
							row.employee_advance = d.name;
							row.posting_date = d.posting_date;
							row.advance_account = d.advance_account;
							row.advance_paid = d.paid_amount;
							row.unclaimed_amount = flt(d.paid_amount) - flt(d.claimed_amount);
							row.allocated_amount = 0;
						});
						refresh_field("advances");
					}
				}
			});
		}
	},
	grand_total: function(frm) {
		frm.trigger("update_employee_advance_claimed_amount");
		frm.set_value('balance', frm.doc.grand_total - frm.doc.total_amount);
	},
	update_employee_advance_claimed_amount: function(frm) {
		let amount_to_be_allocated = frm.doc.total_amount;
		$.each(frm.doc.advances || [], function(i, advance){
			if (amount_to_be_allocated >= advance.unclaimed_amount){
				advance.allocated_amount = frm.doc.advances[i].unclaimed_amount;
				amount_to_be_allocated -= advance.allocated_amount;
			} else {
				advance.allocated_amount = amount_to_be_allocated;
				amount_to_be_allocated = 0;
			}
			frm.refresh_field("advances");
		});
	},
	total_amount: function(frm) {
		frm.set_value('total_claimed_amount', frm.doc.total_amount - frm.doc.total_advance_amount);
		frm.set_value('balance', frm.doc.grand_total - frm.doc.total_amount);
	},
	total_advance_amount: function(frm) {
		console.log('total_advance_amount');
		frm.set_value('total_claimed_amount', frm.doc.total_amount - frm.doc.total_advance_amount);
		frm.trigger("update_item_allocated_advance")
	},
	update_item_allocated_advance: function(frm) {
		let amount_to_be_allocated = frm.doc.total_advance_amount;
		console.log('amount_to_be_allocated: ', amount_to_be_allocated);
		$.each(frm.doc.store_purchase_detail || [], function(i, store_purchase_detail){
			if (amount_to_be_allocated >= store_purchase_detail.paid_amount){
				store_purchase_detail.advance_allocated_amount = frm.doc.store_purchase_detail[i].paid_amount;
				amount_to_be_allocated -= store_purchase_detail.advance_allocated_amount;
			} else {
				store_purchase_detail.advance_allocated_amount = amount_to_be_allocated;
				amount_to_be_allocated = 0;
			}
			frm.refresh_field("store_purchase_detail");
			console.log('store_purchase_detail.advance_allocated_amount: ', store_purchase_detail.advance_allocated_amount);
		});
	}
});
//deal with the item table
frappe.ui.form.on("Store Purchase Detail", {
	//get the supplier's payable account
	supplier: function(frm, cdt, cdn) {
		var d = locals[cdt][cdn];
		frappe.call({
			method: "erpnext.stock.doctype.store_purchase.store_purchase.get_supplier_account",
			args: {
				supplier: d.supplier,
				company: frm.doc.company
			},
			callback: function(r) {
				if (r.message) {
					//if field is empty, set the default payable account
					if (!d.supplier_payable_account) {
						frappe.model.set_value(cdt, cdn, "supplier_payable_account", r.message);
					}
				}
			}
		});
	},
	//get the item's default debit account
	item: function(frm, cdt, cdn) {
		//get the item's default payable account
		var d = locals[cdt][cdn];
		frappe.call({
			method: "erpnext.stock.doctype.store_purchase.store_purchase.get_item_account",
			args: {
				item: d.item,
				company: frm.doc.company
			},
			callback: function(r) {
				if (r.message) {
					//if field is empty, set the default payable account
					if (!d.item_debit_account) {
						frappe.model.set_value(cdt, cdn, "item_debit_account", r.message);
					}
				}
			}
		});
	},
	amount: function(frm, cdt, cdn) {
		var d = locals[cdt][cdn];
		//loop through the table and calculate the total amount
		var grand_total = 0;
		$.each(frm.doc.store_purchase_detail || [], function(i, d) {
			grand_total += flt(d.amount);
		})
		frm.set_value("grand_total", grand_total);
	},
	paid_amount: function(frm, cdt, cdn) {
		var d = locals[cdt][cdn];
		//loop through the table and calculate the total amount
		var total_amount = 0;
		$.each(frm.doc.store_purchase_detail || [], function(i, d) {
			total_amount += flt(d.paid_amount);
		})
		frm.set_value("total_amount", total_amount);
	},
	// calculate the total amount
	qty: function(frm, cdt, cdn) {
		var d = locals[cdt][cdn];
		if (d.qty && d.rate) {
			frappe.model.set_value(cdt, cdn, "amount", d.qty * d.rate);
		}
	},
	rate: function(frm, cdt, cdn) {
		var d = locals[cdt][cdn];
		if (d.qty && d.rate) {
			frappe.model.set_value(cdt, cdn, "amount", d.qty * d.rate);
		}
	}
});

frappe.ui.form.on("Expense Claim Advance", {
	employee_advance: function(frm, cdt, cdn) {
		var child = locals[cdt][cdn];
		if(!frm.doc.employee){
			frappe.msgprint(__('Select an employee to get the employee advance.'));
			frm.doc.advances = [];
			refresh_field("advances");
		}
		else {
			return frappe.call({
			method: "erpnext.stock.doctype.store_purchase.store_purchase.get_advances",
				args: {
					employee: frm.doc.employee,
					advance_id: child.employee_advance
				},
				callback: function(r, rt) {
					if(r.message) {
						child.employee_advance = r.message[0].name;
						child.posting_date = r.message[0].posting_date;
						child.advance_account = r.message[0].advance_account;
						child.advance_paid = r.message[0].paid_amount;
						child.unclaimed_amount = flt(r.message[0].paid_amount) - flt(r.message[0].claimed_amount);
						child.allocated_amount = flt(r.message[0].paid_amount) - flt(r.message[0].claimed_amount);
						frm.trigger('calculate_grand_total');
						refresh_field("advances");
					}
				}
			});
		}
	},
	allocated_amount: function(frm, cdt, cdn) {
		var d = locals[cdt][cdn];
		//loop through the table and calculate the total amount
		var total_advance_amount = 0;
		$.each(frm.doc.advances || [], function(i, d) {
			total_advance_amount += flt(d.allocated_amount);
		})
		frm.set_value("total_advance_amount", total_advance_amount);
	}
});
/*
cur_frm.cscript.calculate_grand_total = function(doc) {
	doc.grand_total = 0
	doc.store_purchase_detail.forEach(function(d) {
		doc.grand_total += flt(d.amount);
	});
	frappe.model.set_value('grand_total', doc.grand_total);
};

cur_frm.cscript.calculate_grand_total_amount = function(doc, cdt, cdn) {
	cur_frm.cscript.calculate_grand_total(doc, cdt, cdn);
}

cur_frm.cscript.calculate_total_amount = function(doc, cdt, cdn) {
	console.log('calculate_total_amount')
	doc.total_amount = 0
	$.each(((doc.store_purchase_detail || []), function(i, d) {
		doc.total_amount += flt(d.paid_amount);
		console.log(doc.total_amount)
	}));
}
*/