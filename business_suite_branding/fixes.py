"""Launcher repairs that run after every migrate.

`bench migrate` re-imports upstream fixtures, so anything fixed by a one-shot
patch comes back on the next deploy. Both failures below are of that kind,
which is why they live on the `after_migrate` hook rather than in patches.txt
alone.

1. A sidebar row linking to a DocType this site does not have.
   erpnext ships `Repost Accounting Ledger Settings` in the `Accounts` and
   `Setup` shells, but that DocType is not installed here, so the row routes
   to a form that cannot resolve.

   The rows live in `Sidebar Item` — the table the 16.53 launcher actually
   reads. `Workspace Sidebar Item` is the pre-16.53 system and is dead on this
   site (0 rows carrying the target), so a prune written against it is a
   silent no-op.

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
	"""Drop `Sidebar Item` rows whose DocType is not installed.

	`Sidebar Item` is the child table of the `Sidebar` doctype, which is what
	the 16.53 launcher reads. The pre-16.53 `Workspace Sidebar Item` table is
	not consulted by it, so pruning there removes nothing.

	Only rows that name a target are touched: section breaks legitimately carry
	no `link_to`, and deleting those would empty out every shell's headings.
	"""
	removed = 0
	for target in DEAD_LINK_TARGETS:
		if frappe.db.exists("DocType", target):
			continue
		rows = frappe.get_all(
			"Sidebar Item",
			filters={"link_type": "DocType", "link_to": target},
			pluck="name",
		)
		if not rows:
			continue
		frappe.db.delete("Sidebar Item", {"link_type": "DocType", "link_to": target})
		removed += len(rows)
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
	"""Drop the per-user launcher caches.

	`get_desktop_icons()` short-circuits on `frappe.cache.hget("desktop_icons",
	user)` and never re-reads the table, and `module_sidebars` rides the same
	per-user `bootinfo` hash — so a repaired grid stays invisible to anyone
	already logged in until both keys are gone. The desktop_icons value is a
	Python list rather than JSON, so it has to be removed with hdel rather than
	parsed.
	"""
	cleared = 0
	for user in frappe.get_all("User", pluck="name"):
		hit = frappe.cache.hdel("desktop_icons", user)
		frappe.cache.hdel("bootinfo", user)
		cleared += 1 if hit else 0
	frappe.clear_cache()
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
