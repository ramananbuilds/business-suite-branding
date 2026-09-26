"""Restore + durably re-create the 'ERP Settings' sidebar and its tile.

WHAT WENT WRONG (and why this patch exists)
-------------------------------------------
`bench migrate` runs frappe.model.sync.remove_orphan_entities(), which for
app-level entities does:

    for app_entity in ("Workspace Sidebar", "Desktop Icon"):
        all_entities = frappe.get_all(app_entity, filters={"standard": True}, ...)
        for entity in all_entities:
            if not check_if_record_exists("app", app_path, app_entity, entity.name):
                frappe.delete_doc(app_entity, entity.name, force=True)

and check_if_record_exists builds the fixture path from the RECORD NAME:

    scrubbed_name = frappe.scrub(name.lower())
    path = <app_path>/workspace_sidebar/<scrubbed_name>/<scrubbed_name>.json
    return os.path.exists(path)

So renaming a *standard* sidebar orphans it: there is an
erpnext/workspace_sidebar/erpnext_settings/erpnext_settings.json fixture, but
no .../erp_settings/erp_settings.json, and the next migrate deletes the doc --
which cascades to its 19 Workspace Sidebar Item children and drops the tile out
of the launcher (13 tiles instead of 14).

Rename the sidebar only; do NOT rename the Desktop Icon tile's PK, because
delete_duplicate_icons() applies the same fixture-path test to Desktop Icon and
would delete a renamed App row too.

THE FIX
-------
Ship the fixture in the branding app. check_if_record_exists uses
`entity.app` to pick the app path, and the sidebar's `app` field is what decides
which directory is searched. The fixture is written under the BRANDING app, and
the sidebar's app is set to business_suite_branding, so the path resolves inside
a directory that IS version-controlled and DOES ship in the image.

Two things are therefore done here:
  1. write erp_settings/erp_settings.json into
     business_suite_branding/workspace_sidebar/ (version-controlled, ships in
     the image) so the orphan check finds it on every future migrate;
  2. recreate the sidebar + its 19 items + tile if they are missing.
"""
import json
import os

import frappe

APP = "business_suite_branding"
SIDEBAR = "ERP Settings"
# the tile's PK is unchanged from the upstream row; only its label was renamed
TILE_PK = "ERPNext Settings"

# Recovered verbatim from the pre-incident backup
# (white-label-backup-20260926-160525.sql, parent='ERPNext Settings'):
# 19 Workspace Sidebar Item rows and 7 Workspace Shortcut rows. Do NOT
# hand-edit these from memory -- a wrong `link_to` fails LinkValidation and the
# whole sidebar fails to insert.
ITEMS = [
	("Link", "Global Defaults", "Global Defaults", 0),
	("Link", "System Settings", "System Settings", 0),
	("Link", "Accounts Settings", "Accounts Settings", 0),
	("Link", "POS Settings", "POS Settings", 0),
	("Link", "Selling Settings", "Selling Settings", 0),
	("Link", "Buying Settings", "Buying Settings", 0),
	("Link", "Stock Settings", "Stock Settings", 0),
	("Link", "Manufacturing Settings", "Manufacturing Settings", 0),
	("Link", "Projects Settings", "Projects Settings", 0),
	("Link", "CRM Settings", "CRM Settings", 0),
	("Link", "Support Settings", "Support Settings", 0),
	("Section Break", "Other Settings", None, 1),
	("Link", "Subscription Settings", "Subscription Settings", 0),
	("Link", "Item Variant Settings", "Item Variant Settings", 0),
	("Link", "Delivery Settings", "Delivery Settings", 0),
	("Link", "Currency Exchange Settings", "Currency Exchange Settings", 0),
	("Link", "Appointment Booking Settings", "Appointment Booking Settings", 0),
	("Link", "Stock Reposting Settings", "Stock Reposting Settings", 0),
]

# 'Repost Accounting Ledger Settings' was item 19 in the backup but its DocType
# is not installed on this site, so LinkValidation aborts the whole insert. It
# is skipped at runtime rather than hard-coded out, so the item comes back
# automatically if the DocType is ever installed. The intact 'Accounts Setup'
# sidebar still references it, i.e. this is a pre-existing gap in the install,
# not something the rename caused.

SHORTCUTS = [
	("System Settings", "System Settings"),
	("Selling Settings", "Selling Settings"),
	("Buying Settings", "Buying Settings"),
	("Stock Settings", "Stock Settings"),
	("Print Settings", "Print Settings"),
	("Global Defaults", "Global Defaults"),
	("Accounts Settings", "Accounts Settings"),
]


def valid_items():
	"""Drop items whose DocType is not installed on this site.

	Link validation runs on the whole child table, so one bad `link_to` aborts
	the insert and the sidebar never gets created at all. Filtering here keeps a
	single missing DocType from costing the tile entirely.
	"""
	out = []
	for (t, lb, lt, sb) in ITEMS:
		if lt and not frappe.db.exists("DocType", lt):
			frappe.logger().info(
				f"[branding] skipping sidebar item {lb!r}: DocType {lt!r} not installed"
			)
			continue
		out.append((t, lb, lt, sb))
	return out


def write_fixture() -> str:
	"""Write the workspace_sidebar/erp_settings.json fixture into the app.

	remove_orphan_entities() -> check_if_record_exists("app", app_path, ...) and:

	    def build_path(entity_name):
	        if type == "app":
	            return os.path.join(path, scrubbed_entity_type, f"{entity_name}.json")
	        return os.path.join(path, scrubbed_entity_type, entity_name,
	                            f"{entity_name}.json")

	Note the asymmetry: for type="app" the path is FLAT --
	non-app form nests it as .../erp_settings/erp_settings.json. The nested
	layout is what erpnext's own sidebars use, which is why it looks right; it
	is also why the orphan check kept finding nothing and deleting the sidebar on
	every migrate.
	"""
	doc = {
		"doctype": "Workspace Sidebar",
		"name": SIDEBAR,
		"title": SIDEBAR,
		"app": APP,
		"standard": 1,
		"items": [
			{"type": t, "label": lb, "link_to": lt, "is_section_break": sb}
			for (t, lb, lt, sb) in valid_items()
		],
	}
	dirpath = os.path.join(frappe.get_app_path(APP), "workspace_sidebar")
	os.makedirs(dirpath, exist_ok=True)
	path = os.path.join(dirpath, "erp_settings.json")
	with open(path, "w") as f:
		json.dump(doc, f, indent=1, sort_keys=True)
	return path


def recreate_sidebar() -> None:
	doc = frappe.new_doc("Workspace Sidebar")
	doc.name = SIDEBAR
	doc.title = SIDEBAR
	doc.app = APP
	doc.standard = 1
	# child rows must be real documents, not plain dicts: _set_defaults() is
	# called on each one during insert and expects a Document
	doc.items = []
	for (t, lb, lt, sb) in valid_items():
		doc.append(
			"items",
			{"type": t, "label": lb, "link_to": lt, "is_section_break": sb},
		)
	doc.insert(ignore_if_duplicate=True)

	for label, link_to in SHORTCUTS:
		if frappe.db.exists("Workspace Shortcut", {"parent": SIDEBAR, "label": label}):
			continue
		sc = frappe.new_doc("Workspace Shortcut")
		sc.parent = SIDEBAR
		sc.parenttype = "Workspace Sidebar"
		sc.parentfield = "shortcuts"
		sc.label = label
		sc.link_to = link_to
		sc.type = "DocType"
		sc.insert(ignore_if_duplicate=True)


def execute():
	notes = []

	path = write_fixture()
	notes.append(f"fixture written: {path}")
	notes.append(
		"  orphan check will now resolve "
		f"{os.path.basename(os.path.dirname(path))}/{os.path.basename(path)}"
	)

	if frappe.db.exists("Workspace Sidebar", SIDEBAR):
		notes.append(f"sidebar {SIDEBAR!r} already present")
	else:
		recreate_sidebar()
		notes.append(
			f"sidebar {SIDEBAR!r} recreated: "
			f"{frappe.db.count('Workspace Sidebar Item', {'parent': SIDEBAR})} items, "
			f"{frappe.db.count('Workspace Shortcut', {'parent': SIDEBAR})} shortcuts"
		)

	# the tile label must equal the sidebar name or the boot filter drops it
	row = frappe.db.get_value("Desktop Icon", TILE_PK, ["label"], as_dict=True)
	if row:
		if row.label != SIDEBAR:
			frappe.db.set_value(
				"Desktop Icon", TILE_PK, "label", SIDEBAR, update_modified=False
			)
			notes.append(f"tile label {row.label!r} -> {SIDEBAR!r}")
		else:
			notes.append(f"tile label already {SIDEBAR!r}")
	else:
		notes.append(f"WARNING: Desktop Icon {TILE_PK!r} is missing")

	frappe.db.commit()

	# get_desktop_icons() short-circuits on a PER-USER cache and never re-reads
	# the table:
	#
	#     user_icons = frappe.cache.hget("desktop_icons", user)
	#     if not user_icons:
	#         ...query...
	#
	# So a restored tile stays invisible to an already-logged-in user until
	# that key is dropped, and the value is a Python list, not JSON, so it has
	# to be removed with hdel rather than parsed.
	cleared = 0
	for u in frappe.get_all("User", pluck="name"):
		if frappe.cache.hdel("desktop_icons", u):
			cleared += 1
	frappe.cache.hdel("bootinfo", "Administrator")
	frappe.cache.delete_value("app_hooks")
	notes.append(f"cleared desktop_icons cache for {cleared} user(s)")

	for n in notes:
		frappe.logger().info(f"[branding] {n}")
