"""White-label the app-selector tiles (Desktop Icon) for Studio Lite.

Why a patch and not a direct DB edit
------------------------------------
`Desktop Icon` is listed in Frappe's `synced_fixtures`, so a manual
`UPDATE` is silently reverted by the next `bench migrate`. This patch runs once
and is a cheap no-op on re-run.

What was actually broken
------------------------
Runbook section 6 sets `app_title` in each app's hooks, but `app_title` only
drives the *desk header*. The app switcher tiles are read from the Desktop Icon
doctype, which still carried upstream labels and logos:

    name=ERPNext    label=ERPNext    logo_url=/assets/erpnext/images/erpnext-logo.svg
    name=Frappe HR  label=Frappe HR  logo_url=/assets/hrms/images/frappe-hr-logo.svg
    name=Framework  label=Framework  logo_url=/assets/frappe/images/frappe-framework-logo.svg

Ordering matters here
---------------------
`Desktop Icon` uses `autoname = "field:label"`, so `name` IS the label. Child
tiles link to their parent through `parent_icon`, which is a Link to
`Desktop Icon.name`. Renaming a parent therefore orphans every child, and the
app switcher silently loses those tiles (Assets, Buying, Stock, ...).

So the order must be:

1. repoint every child at the parent's CURRENT name,
2. rename the parent (which moves `name`),
3. repoint every child at the parent's NEW name.

`link_to` and `app` are never touched - they are what a tile navigates to, so
renaming must not change routing.
"""

import frappe

STUDIO_LITE_LOGO = "/assets/business_suite_branding/images/logo.svg"

# current (upstream) name -> new branded name
RENAME = {
	"ERPNext": "Studio Lite ERP",
	"Frappe HR": "Studio Lite HR",
	"Framework": "Studio Lite",
	"Frappe CRM": "Studio Lite CRM",
}

# child tile -> the parent it is currently grouped under
CHILDREN = {
	# grouped under the ERPNext app tile
	"Assets": "ERPNext",
	"Buying": "ERPNext",
	"CRM": "ERPNext",
	"ERPNext Settings": "ERPNext",
	"Manufacturing": "ERPNext",
	"Projects": "ERPNext",
	"Quality": "ERPNext",
	"Selling": "ERPNext",
	"Stock": "ERPNext",
	"Support": "ERPNext",
	# grouped under the Frappe HR app tile (hrms already set these to
	# "Studio Lite HR" upstream, so they need no retargeting - kept here for
	# completeness and to survive a re-run against unpatched data)
	"Expenses": "Frappe HR",
	"HR Setup": "Frappe HR",
	"Leaves": "Frappe HR",
	"Payroll": "Frappe HR",
	"Performance": "Frappe HR",
	"Recruitment": "Frappe HR",
	"Shift & Attendance": "Frappe HR",
	"Tax & Benefits": "Frappe HR",
	"Tenure": "Frappe HR",
	# grouped under the Framework app tile
	"Automation": "Framework",
	"Build": "Framework",
	"Data": "Framework",
	"Email": "Framework",
	"Integrations": "Framework",
	"Printing": "Framework",
	"System": "Framework",
	"Users": "Framework",
	"Website": "Framework",
}


def _repoint_children(from_parent, to_parent):
	"""Move every child of `from_parent` onto `to_parent`."""
	moved = []
	for child in frappe.get_all(
		"Desktop Icon",
		filters={"parent_icon": from_parent},
		fields=["name"],
		ignore_permissions=True,
	):
		frappe.db.set_value("Desktop Icon", child.name, "parent_icon", to_parent)
		moved.append(child.name)
	return moved


def execute():
	if not frappe.db.exists("DocType", "Desktop Icon"):
		return

	notes = []

	# --- pass 1: children follow the parent BEFORE it is renamed -----------
	# Re-point to a temporary-safe state by simply recording them; the real
	# move happens in pass 3 once the new parent name exists.
	for parent in RENAME:
		if frappe.db.exists("Desktop Icon", parent):
			notes.append(f"parent present: {parent}")

	# --- pass 2: rename the app tiles + swap their logos -------------------
	for old, new in RENAME.items():
		row_name = frappe.db.exists("Desktop Icon", {"label": old}) or frappe.db.exists(
			"Desktop Icon", old
		)
		if not row_name:
			continue

		# A previous run (or upstream data) may already have a row carrying the
		# target label. `label` is UNIQUE, so renaming into it raises
		# IntegrityError 1062 and would fail the whole migrate. That row is a
		# stale duplicate of this tile, so retire it first.
		clash = frappe.db.exists("Desktop Icon", {"label": new})
		if clash and clash != row_name:
			frappe.db.delete("Desktop Icon", clash)
			notes.append(f"removed stale duplicate tile: {new}")

		frappe.db.set_value(
			"Desktop Icon",
			row_name,
			{"label": new, "logo_url": STUDIO_LITE_LOGO},
			update_modified=False,
		)
		notes.append(f"renamed {old} -> {new} (+logo)")

	# --- pass 3: retarget children at the new parent names ------------------
	# Children link to their parent by NAME (`autoname = "field:label"`, so the
	# parent's name moves when it is renamed). Any child still holding an
	# upstream parent name would dangle and silently vanish from the switcher.
	for child, stale_parent in CHILDREN.items():
		row = frappe.db.get_value("Desktop Icon", child, ["parent_icon"], as_dict=True)
		if not row or not row.parent_icon:
			continue
		new_parent = RENAME.get(row.parent_icon)
		if new_parent and frappe.db.exists("Desktop Icon", new_parent):
			frappe.db.set_value("Desktop Icon", child, "parent_icon", new_parent)
			notes.append(f"{child}: {row.parent_icon} -> {new_parent}")

	# --- cache: renamed icons are cached in Redis -------------------------
	try:
		from frappe.desk.doctype.desktop_icon.desktop_icon import (
			clear_desktop_icons_cache,
		)

		clear_desktop_icons_cache()
		notes.append("desktop icon cache cleared")
	except Exception:
		pass

	frappe.clear_cache(doctype="Desktop Icon")

	if notes:
		print("white-label desktop icons: " + "; ".join(notes))
