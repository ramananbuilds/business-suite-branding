"""Drop the dead 'Other Settings' sidebar item.

Why
---
v1_1 filtered sidebar items through LinkValidation so that a link pointing at
a DocType which is not installed would be skipped rather than created. That
dropped 'Other Settings', whose DocType no longer exists in this ERPNext --
it is not a settings page at all, it was a section header in the standard
sidebar. The filter correctly refused to create the LINK, but the item itself
was left in place with link_type=None.

That NULL is the launcher crash: desktop.js get_route() falls through every
branch for a null link_type, hands None to generate_route(), and calls
.toLowerCase() on it. The exception aborts DesktopPage.make part-way through,
so every tile after that point silently disappears from the grid.

My earlier "no NULL link_type site-wide" check was wrong -- it scanned the
Workspace Sidebar Item rows for a link_type COLUMN, not the child rows of the
sidebar, so it passed while the bad row was still there. This fix removes the
row, and the check is corrected to look at the children.

The item is deleted rather than given a link_type because there is nothing to
point it at: no DocType named 'Other Settings' exists, so any link_type value
would be a lie and the tile would fail LinkValidation on the next save.
"""

import json
import os

import frappe

APP_DIR = frappe.get_app_path("business_suite_branding")
FIXTURE = os.path.join(APP_DIR, "workspace_sidebar", "erp_settings.json")
SIDEBAR = "ERP Settings"
DEAD_LABELS = {"Other Settings"}


def _drop_from_fixture():
	if not os.path.isfile(FIXTURE):
		print("  WARNING no fixture at %s" % FIXTURE)
		return
	with open(FIXTURE, encoding="utf-8") as f:
		data = json.load(f)

	items = data.get("items") or []
	before = len(items)
	kept = [i for i in items if i.get("label") not in DEAD_LABELS]
	removed = before - len(kept)
	if not removed:
		print("  fixture: already clean (%d items)" % len(kept))
		return

	data["items"] = kept
	with open(FIXTURE, "w", encoding="utf-8") as f:
		json.dump(data, f, indent=1, ensure_ascii=False)
		f.write("\n")
	print("  fixture: removed %d dead item(s), %d -> %d" % (removed, before, len(kept)))


def _drop_from_db():
	if not frappe.db.exists("Workspace Sidebar", SIDEBAR):
		print("  no sidebar named %r" % SIDEBAR)
		return
	sb = frappe.get_doc("Workspace Sidebar", SIDEBAR)

	kill = [r.name for r in sb.items if r.label in DEAD_LABELS]
	if not kill:
		print("  live sidebar: already clean (%d items)" % len(sb.items))
		return

	# remove by child-row name; the label is not unique enough to trust here
	for name in kill:
		sb.remove(name)
	sb.save()
	print("  live sidebar: removed %d row(s) %s" % (len(kill), ", ".join(kill)))


def _verify():
	sb = frappe.get_doc("Workspace Sidebar", SIDEBAR)
	bad = [(i.label, i.link_type) for i in sb.items if not i.link_type]
	nulls = [(i.label, i.link_to) for i in sb.items if not i.link_to]
	print("  live sidebar: %d items, %d with NULL link_type" % (len(sb.items), len(bad)))
	for label, lt in bad:
		print("    !! %s -> %r" % (label, lt))
	for label, lto in nulls:
		print("    !! %s has no link_to" % label)
	if not bad and not nulls:
		print("  PASS every item has a link_type and a link_to")
	return not bad and not nulls


def execute():
	print("=== removing dead sidebar items ===")
	_drop_from_db()
	_drop_from_fixture()
	ok = _verify()

	frappe.db.commit()

	# the launcher is cached per user, so clear it or the grid still renders
	# the item that is no longer in the sidebar
	for user in frappe.get_all("User", pluck="name"):
		frappe.cache.hdel("desktop_icons", user)
	print("  cleared desktop_icons for all users")

	if not ok:
		raise frappe.ValidationError("sidebar still has items without link_type")
