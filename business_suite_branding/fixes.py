"""Launcher repairs that run after every migrate.

`bench migrate` re-imports upstream fixtures, so anything fixed by a one-shot
patch comes back on the next deploy. Both failures below are of that kind,
which is why they live on the `after_migrate` hook rather than in patches.txt
alone.

1. A sidebar row linking to a DocType this site does not have.
   erpnext ships `Repost Accounting Ledger Settings` in the `Accounts Setup`
   and `ERPNext Settings` shells, but that DocType is not installed here, so
   the row routes to a form that cannot resolve.

2. A tile linking to a shell the desk no longer has.
   The HR tile carried `/desk/people` forward from the pre-16 desk. There is
   no `People` shell in v16, so the link is stale.
"""
import frappe

# Upstream links a DocType we never installed.
DEAD_LINK_TARGETS = ("Repost Accounting Ledger Settings",)

# External tile links that name a shell the desk no longer has.
LEGACY_TILE_LINKS = {"/desk/people": "/desk/hr-setup"}


def prune_dead_sidebar_links() -> int:
	"""Drop sidebar rows whose DocType is not installed.

	Only rows that name a target are touched: section breaks legitimately carry
	no `link_to`, and deleting those would empty out every shell's headings.
	"""
	removed = 0
	for target in DEAD_LINK_TARGETS:
		if frappe.db.exists("DocType", target):
			continue
		rows = frappe.get_all(
			"Workspace Sidebar Item",
			filters={"link_type": "DocType", "link_to": target},
			pluck="name",
		)
		for row in rows:
			frappe.db.delete("Workspace Sidebar Item", {"name": row})
			removed += 1
	return removed


def repair_tile_links() -> int:
	"""Repoint External tiles at shells that exist."""
	fixed = 0
	for old, new in LEGACY_TILE_LINKS.items():
		icons = frappe.get_all(
			"Desktop Icon",
			filters={"link_type": "External", "link": old},
			pluck="name",
		)
		for icon in icons:
			frappe.db.set_value("Desktop Icon", icon, "link", new, update_modified=False)
			fixed += 1
	return fixed


def clear_launcher_cache() -> int:
	"""Drop the per-user desktop icon caches.

	get_desktop_icons() short-circuits on `frappe.cache.hget("desktop_icons", user)`
	and never re-reads the table, so a repaired grid stays invisible to anyone
	already logged in until the key is gone. The value is a Python list rather
	than JSON, so it has to be removed with hdel rather than parsed.
	"""
	cleared = 0
	for user in frappe.get_all("User", pluck="name"):
		if frappe.cache.hdel("desktop_icons", user):
			cleared += 1
	frappe.cache.hdel("bootinfo", "Administrator")
	frappe.cache.delete_value("app_hooks")
	return cleared


def after_migrate():
	removed = prune_dead_sidebar_links()
	fixed = repair_tile_links()
	cleared = clear_launcher_cache()
	frappe.db.commit()
	frappe.logger().info(
		f"[branding] launcher repair: {removed} dead link(s) pruned, "
		f"{fixed} tile link(s) repointed, {cleared} user cache(s) cleared"
	)
