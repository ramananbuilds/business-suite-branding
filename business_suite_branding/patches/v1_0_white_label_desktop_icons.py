"""
Studio Lite white-label: app-selector (Desktop Icon) titles and logos.

SCOPE
-----
Per the agreed design, ONLY the HR and CRM application tiles are rebranded.
Everything else keeps its upstream label and its default module icon, so the
launcher still reads as a product rather than as identical black wordmarks.

    Frappe HR      ->  Studio Lite HR      (green person icon retained)
    Frappe CRM     ->  Studio Lite CRM     (Studio Lite wordmark)
    Framework      ->  Framework           (unchanged)
    ERPNext        ->  ERPNext             (unchanged, stays hidden)

THE BUG THIS PATCH PREVENTS
---------------------------
`Desktop Icon.parent_icon` is a Link to `Desktop Icon`.`name`, but the desk
frontend keys its lookup map by `label`:

    desktop.js
        icon_map[icon.label] = icon;                            // keyed by LABEL
        if (icon.parent_icon && icon_map[icon.parent_icon])       // looked up by NAME
            icon_map[icon.parent_icon].child_icons.push(icon);
        if (!icon.parent_icon || !icon_map[icon.parent_icon])
            this.apps_icons.push(icon);                          // no match -> top level

A child therefore renders as a NESTED child only while its parent's `name` and
`label` are identical. `Desktop Icon` sets `autoname = "field:label"`, so they
start out equal. Renaming a parent's `label` alone breaks the match: every
child falls through to `apps_icons` and the grid collapses into a flat wall of
top-level tiles.

Renaming a parent is thus never safe on its own. This patch renames the parent
AND retargets every child's `parent_icon` in the same pass, then asserts the
invariant.

Note the ERPNext parent is intentionally left `hidden = 1`. That is the
upstream state and it is what produces the agreed layout: Assets, Buying,
Manufacturing, Projects, Quality, Selling and Stock render as top-level tiles
because their parent is hidden and therefore absent from `icon_map`.

NEVER DELETE A ROW
------------------
`label` is UNIQUE. An earlier revision deleted the row holding a target label
to free the column, which removed the working CRM launcher tile (row count
47 -> 46). If a label is already taken, brand its owner in place instead.
"""

import frappe

# row NAME -> desired label. `name` is never changed, so children that already
# point at the name keep working.
RENAME = {
	"Frappe HR": "Studio Lite HR",
	"Framework": "Framework",
	"ERPNext": "ERPNext",
}

STUDIO_LITE_LOGO = "/assets/business_suite_branding/images/logo.svg"

# Only the CRM tile carries the wordmark; the others keep their default icons.
APP_TILE_LOGOS = {
	"Framework": None,
	"ERPNext": None,
	"Frappe HR": None,
	"Studio Lite CRM": STUDIO_LITE_LOGO,
}

# Rows that must stay hidden to reproduce the agreed flat layout.
KEEP_HIDDEN = ["ERPNext"]


def execute():
	notes: list[str] = []

	# --- pass 1: parent labels ---------------------------------------------
	for name, new_label in RENAME.items():
		row = frappe.db.get_value(
			"Desktop Icon", name, ["name", "label", "icon_type"], as_dict=True
		)
		if not row:
			notes.append(f"skip rename: no Desktop Icon named {name!r}")
			continue
		if row.label == new_label:
			continue

		# `label` is UNIQUE -- renaming into an occupied label raises
		# IntegrityError 1062 and fails the entire migrate.
		#
		# Never delete the squatter. Here a hidden Link-type row named
		# "Frappe CRM" held the label "Studio Lite CRM" while the real CRM
		# launcher tile was a separate App-type row ALSO named
		# "Studio Lite CRM". Deleting the holder dropped the working tile.
		clash = frappe.db.exists("Desktop Icon", {"label": new_label})
		if clash and clash != row.name:
			clash_row = frappe.db.get_value(
				"Desktop Icon", clash, ["name", "icon_type", "hidden"], as_dict=True
			)
			if clash_row.icon_type != "App" and clash_row.hidden:
				# Hidden, non-App row squatting on the label: move it onto its
				# own name and keep BOTH rows.
				frappe.db.set_value(
					"Desktop Icon", clash, "label", clash_row.name, update_modified=False
				)
				notes.append(f"freed label {new_label!r} from hidden {clash_row.name!r}")
			else:
				# A visible or App-type row owns this label: it IS the tile we
				# want, so brand it in place and skip the rename.
				frappe.db.set_value(
					"Desktop Icon",
					clash,
					{"logo_url": APP_TILE_LOGOS.get(clash, STUDIO_LITE_LOGO)},
					update_modified=False,
				)
				notes.append(f"{new_label!r}: branded existing row {clash!r} in place")
				continue

		frappe.db.set_value(
			"Desktop Icon", row.name, "label", new_label, update_modified=False
		)
		notes.append(f"label {row.label!r} -> {new_label!r} (name {row.name!r} unchanged)")

	# --- pass 2: retarget every child at the label its parent renders under ---
	# The frontend resolves a child as `icon_map[child.parent_icon]` with the
	# map keyed by LABEL, so `parent_icon` must equal the parent's label.
	#
	# This is also the REPAIR path. `parent_icon` is nominally a Link to
	# `Desktop Icon`.`name`, but because the frontend matches on LABEL, an
	# earlier rename of a parent left every child pointing at a label that no
	# longer exists -- the whole group then renders flat as top-level tiles.
	# So children are matched on BOTH the parent's current name and any stale
	# label recorded in PREVIOUS_LABELS, not just the name.
	STALE_PARENT_LABELS = {
		# parent name -> labels its children may still be pointing at
		"Framework": ("Studio Lite",),
		"Frappe HR": ("Studio Lite HR", "Frappe HR"),
		"ERPNext": ("Studio Lite ERP", "ERPNext"),
	}
	for name in RENAME:
		row = frappe.db.get_value("Desktop Icon", name, ["name", "label"], as_dict=True)
		if not row:
			continue
		stale = STALE_PARENT_LABELS.get(name, ())
		# point every child that references the parent (by name or by a stale
		# label) at the label the parent actually renders under
		refs = tuple(dict.fromkeys((row.name, row.label, *stale)))
		placeholders = ", ".join(["%s"] * len(refs))
		frappe.db.sql(
			f"UPDATE `tabDesktop Icon` SET parent_icon = %s WHERE parent_icon IN ({placeholders})",
			(row.label, *refs),
		)
		notes.append(f"retargeted children of {name!r} to parent_icon={row.label!r}")

	# --- pass 3: logos ------------------------------------------------------
	for name, logo in APP_TILE_LOGOS.items():
		if not frappe.db.exists("Desktop Icon", name):
			continue
		frappe.db.set_value("Desktop Icon", name, "logo_url", logo, update_modified=False)
	notes.append("app tile logos set")

	# --- pass 4: preserve the agreed hidden state ---------------------------
	for name in KEEP_HIDDEN:
		row = frappe.db.get_value("Desktop Icon", name, ["hidden", "label"], as_dict=True)
		if not row:
			continue
		if row.hidden != 1:
			frappe.db.set_value("Desktop Icon", name, "hidden", 1, update_modified=False)
			notes.append(f"re-hid {name!r} so its children render top-level")

	# --- pass 5: assert the rendering invariant -----------------------------
	# Any child whose parent_icon matches no visible label will render flat.
	# Report it loudly rather than letting the grid silently collapse again.
	all_icons = frappe.db.sql(
		"select name, label, parent_icon, hidden from `tabDesktop Icon`", as_dict=True
	)
	visible_labels = {i["label"] for i in all_icons if i["hidden"] != 1}
	orphans = [
		i["label"]
		for i in all_icons
		if i["hidden"] != 1 and i["parent_icon"] and i["parent_icon"] not in visible_labels
	]
	notes.append(
		f"invariant check: {len(orphans)} tiles render top-level by design"
		if not orphans
		else f"WARNING: {len(orphans)} tiles would render flat: {sorted(orphans)}"
	)

	try:
		from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache

		clear_desktop_icons_cache()
	except Exception:
		pass
	frappe.clear_cache(doctype="Desktop Icon")

	for note in notes:
		print(f"white-label desktop icons: {note}")
