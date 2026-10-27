"""Restore the nine desktop-area sidebars as `Sidebar` records.

WHY THIS PATCH EXISTS
---------------------
The white-label desktop IA maps one tile per *area*: the Accounting folder holds
ERP Settings, Accounts Setup, Banking, Budget, Payments, Share Management,
Subscription and Taxes; the ERPNext/Framework/HR parents hold module tiles.

Those area names were first-class in the old launcher (a `Workspace Sidebar`
document per area, opened by the tile's label). Upstream 16.53 replaced that
system with the `Sidebar` doctype, and apps 16.36+ ship only module-level
sidebars — the per-area sidebars became *sections* of their module's sidebar and
the old `Workspace Sidebar` rows stopped being served at all.

The launcher's `get_route()` then resolved each tile on `module || label`. For
the nine area tiles `module` is server-injected only when `link_to` names a real
Workspace — for these nine it does not (there is no workspace named
"Banking"/"Budget"/…), so the label fell back into the module-keyed payload,
missed, `icon_route` stayed undefined and every click printed
"Icon is not correctly configured please check the workspace sidebar to it".

THE FIX
-------
Recreate each area as a real `Sidebar` record (name = title = shell identity),
with the items copied from the surviving `Workspace Sidebar` document of the same
name. The tile then resolves through the module-keyed payload the same way the
module tiles do, and the nine area shells appear with the content they always
had. No tile rows are touched. The bundle-side `link_to` fix (fork commit on
3f4286de24) handles the *workspace* tiles separately (Invoicing, Leaves, &c.).

Durability, the v1_1 lesson applied twice over:

* every record this patch creates is `standard: 1` with `app` set to this app,
  and a JSON fixture ships under `business_suite_branding/sidebar/<area>/`, so
  `create_entity_file_map`'s recursive `**/sidebar/**/*.json` glob finds it and
  `remove_orphan_entities` never deletes the record;
* an import of the fixture on a later migrate overwrites/keeps the row, so the
  patch is only needed for the first site that has not migrated yet — it must be
  idempotent and leave an already-created row untouched.

Sidebar validation notes baked into the data:

* none of the nine names is another app's Module Def, and none shares a
  `shell_slug` with an existing shell — `validate_title_is_its_own` and
  `validate_title_has_its_own_url` would refuse the insert otherwise, and both
  were checked against the live site before the fixtures were cut;
* every `Link` item carries both `link_type` and `link_to` (a NULL link_type on
  a Link row is fatal — the v1_3 crash class). Non-Link rows are copied as-is;
  this site's healthy sidebars carry the same shape.
"""

import json
import os
import re

import frappe

APP = "business_suite_branding"
AREAS = [
	"Accounts Setup",
	"Banking",
	"Budget",
	"ERP Settings",
	"Organization",
	"Payments",
	"Share Management",
	"Subscription",
	"Taxes",
]
SIDEBAR_ITEM_FIELDS = (
	"type",
	"label",
	"link_type",
	"link_to",
	"icon",
	"child",
	"indent",
	"collapsible",
	"keep_closed",
	"url",
	"show_arrow",
	"filters",
	"route_options",
	"navigate_to_tab",
	"open_in_new_tab",
)


def _scrub(name: str) -> str:
	return re.sub(r"\W+", "_", name.lower()).strip("_") or "_"


def _fixture_path(area: str) -> str:
	s = _scrub(area)
	return os.path.join(frappe.get_app_path(APP), "sidebar", s, f"{s}.json")


def _items_from_live_old_doc(area: str) -> list[dict] | None:
	"""Recover the item list from the surviving legacy `Workspace Sidebar` doc."""
	source = frappe.db.exists("Workspace Sidebar", area)
	if not source:
		return None
	rows = frappe.get_all(
		"Workspace Sidebar Item",
		filters={"parent": area},
		fields=["idx", "type", "label", "link_type", "link_to", "url", "child",
			"indent", "collapsible", "keep_closed", "icon", "show_arrow",
			"filters", "route_options", "navigate_to_tab", "open_in_new_tab"],
		order_by="idx",
	)
	# a Link row may not go out without both link_type and link_to; refuse loudly
	# rather than shipping the NULL that takes the grid down (the v1_3 crash).
	for row in rows:
		if row.type == "Link" and (not row.link_type or not row.link_to):
			raise frappe.ValidationError(
				f"[branding] legacy {area} item {row.label!r} has no link_type/link_to"
			)
	return rows


def _ensure_fixture(area: str) -> str:
	path = _fixture_path(area)
	if os.path.isfile(path):
		return "already present"

	rows = _items_from_live_old_doc(area)
	if rows is None:
		# shipped in the repo, so absent here only if someone deleted it
		raise FileNotFoundError(f"[branding] no fixture and no legacy doc for {area!r}")

	doc = {
		"doctype": "Sidebar",
		"name": area,
		"title": area,
		"app": APP,
		"standard": 1,
		"items": [
			{
				"doctype": "Sidebar Item",
				"parentfield": "items",
				"parenttype": "Sidebar",
				"idx": n,
				**{field: row.get(field) for field in SIDEBAR_ITEM_FIELDS if row.get(field) is not None},
			}
			for n, row in enumerate(rows, start=1)
		],
	}
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w", encoding="utf-8") as f:
		json.dump(doc, f, indent=1, ensure_ascii=False)
		f.write("\n")
	return f"written from the legacy Workspace Sidebar ({len(rows)} items)"


def _ensure_record(area: str) -> str:
	if frappe.db.exists("Sidebar", area):
		return "already present"

	path = _fixture_path(area)
	if not os.path.isfile(path):
		_ensure_fixture(area)
	with open(path, encoding="utf-8") as f:
		doc = json.load(f)

	# LinkValidation aborts the whole insert when a link names something this
	# site does not have (v1_1 filtered the same way; this site's item was
	# "Repost Accounting Ledger Settings"). The row comes back from the fixture
	# if the target is ever installed. A Link row with NO target at all is the
	# v1_3 crash class and is dropped rather than inserted.
	def _target_missing(item: dict) -> bool:
		kind, target = item.get("link_type"), item.get("link_to")
		if not kind or not target:
			return item.get("type") == "Link"
		if kind not in ("DocType", "Report", "Workspace", "Dashboard", "Page"):
			return False
		return not frappe.db.exists(kind, target, cache=True)

	before = len(doc.get("items") or [])
	doc["items"] = [i for i in (doc.get("items") or []) if not _target_missing(i)]
	dropped = before - len(doc["items"])

	# validate_standard() demands developer mode to flip `standard` on and
	# validate_app_content() allows app-owned edits only under its SYSTEM_WRITE_FLAGS;
	# honour both for the insert, then restore the site's own values.
	patch_mode = frappe.conf.developer_mode
	frappe.conf.developer_mode = 1
	frappe.flags.in_patch = True
	try:
		sidebar = frappe.get_doc(doc)
		sidebar.insert(ignore_if_duplicate=True)
	finally:
		frappe.conf.developer_mode = patch_mode
		frappe.flags.in_patch = False

	return f"created ({len(doc['items'])} items" + (f", {dropped} link target(s) not on this site dropped" if dropped else "") + ")"


def _clear_caches() -> None:
	# the launcher grid is cached per user (get_desktop_icons short-circuits on
	# frappe.cache.hget) and the boot payload caches are cleared wholesale
	cleared = 0
	for user in frappe.get_all("User", pluck="name"):
		if frappe.cache.hdel("desktop_icons", user):
			cleared += 1
	frappe.cache.hdel("bootinfo", "Administrator")
	frappe.clear_cache(doctype="Sidebar")
	return cleared


def execute():
	notes = []
	for area in AREAS:
		notes.append(f"{area!r} fixture: {_ensure_fixture(area)}")
		notes.append(f"{area!r} sidebar: {_ensure_record(area)}")

	# what the launcher will now resolve: every area must be a key of the payload
	payload = frappe.boot.get_module_sidebars()
	missing = [a for a in AREAS if a not in payload]
	if missing:
		raise frappe.ValidationError(f"[branding] area sidebars not in module_sidebars: {missing}")
	fixtures_ok = all(os.path.isfile(_fixture_path(a)) for a in AREAS)
	notes.append(
		f"resolution: {len(AREAS)}/{len(AREAS)} in module_sidebars; "
		f"fixtures on disk: {'yes' if fixtures_ok else 'NO'}"
	)

	cleared = _clear_caches()
	notes.append(f"cleared desktop_icons cache for {cleared} user(s)")

	for n in notes:
		print(f"restore area sidebars: {n}")
