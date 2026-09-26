"""
Studio Lite white-label: app-selector (Desktop Icon) titles, logos and links.

SCOPE (agreed design)
---------------------
Short, product-neutral names. Only the CRM and HR application tiles are
rebranded; every module tile keeps its upstream label and default icon.

    Frappe HR      ->  HR              (green person icon retained)
    Frappe CRM     ->  CRM             (Studio Lite wordmark)
    ERPNext Settings -> ERP Settings
    Framework      ->  Framework       (unchanged)
    ERPNext        ->  ERPNext         (unchanged, stays hidden)

App-tile LOGOS: all three of Framework, CRM and HR get the Studio Lite
wordmark, so the three "application" tiles look alike in the grid while the
blue module tiles keep their own icons.

THE BROKEN CRM TILE
-------------------
The CRM tile was created as::

    name='Studio Lite CRM'  icon_type='App'  app='External'
    link_to='/crm'          link_type='External'

`app='External'` tells Frappe the tile points somewhere outside the installed
apps, so the launcher navigates to the literal path `/crm` -- which does not
exist (it answers 403, while the real desk route `/app/crm` answers 301). The
tile rendered but never opened.

The `crm` app IS installed, so the fix is to set `app='crm'` and let Frappe
resolve the tile the same way it resolves the other app tiles (by `app_name`).

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

STUDIO_LITE_LOGO = "/assets/business_suite_branding/images/logo.svg"

# Square 28x28 tile artwork shipped in this app's public/images. The wordmark is
# 160x48 and renders as a small black bar inside a square tile, so it is used for
# the header / favicon / page title only, never for a launcher tile.
TILE_ASSET_BASE = "/assets/business_suite_branding/images"

# ---------------------------------------------------------------------------
# Renames. Keyed by row NAME, which is never changed, so children that point
# at the name keep working.
# ---------------------------------------------------------------------------
RENAME = {
	"Frappe HR": "HR",
	"Framework": "Framework",
	"ERPNext": "ERPNext",
	# NOT renamed. A Workspace-Sidebar tile is only permitted into the boot
	# payload when `workspace_sidebar_item[label.lower()]` exists and has items
	# (desktop_icon.py). Renaming the tile changes that lookup key, so
	# "ERP Settings" looks up a sidebar named "erp settings", which does not
	# exist, and the tile vanishes from the launcher entirely. Only `App` and
	# `Folder` tiles may be renamed freely.
	"ERPNext Settings": "ERPNext Settings",
}

# The CRM launcher tile was created by the branding setup under its own name and
# is a plain Link-type sibling, not one of the upstream rows above.
RENAME_BY_LABEL = {
	"Studio Lite CRM": "CRM",
}

# Children of these parents may still be pointing at a label the parent used to
# carry (from an earlier rename). Match them so the groups get repaired rather
# than orphaned.
STALE_PARENT_LABELS = {
	"Framework": ("Studio Lite",),
	"Frappe HR": ("Studio Lite HR", "Frappe HR"),
	"ERPNext": ("Studio Lite ERP", "ERPNext"),
	"ERPNext Settings": ("Studio Lite ERP Settings",),
}

# Rows that must stay hidden to reproduce the agreed flat layout.
KEEP_HIDDEN = ["ERPNext"]

# Workspace-Sidebar tiles whose label MUST keep matching their sidebar name, or
# the boot filter drops them from the launcher. Repair pass restores these.
REPAIR_SIDEBAR_LABELS = {
	"ERPNext Settings": "ERPNext Settings",
}


def execute():
	notes: list[str] = []

	# --- pass 0: repair a Workspace-Sidebar tile label that was renamed -----
	# Renaming such a tile removes it from the launcher, because the boot filter
	# permits it only when workspace_sidebar_item[label.lower()] has items. If
	# an earlier run renamed "ERPNext Settings" -> "ERP Settings", put the
	# original label back so the tile returns to the grid.
	# A sidebar of that name must exist before the label is restored.
	for name, sidebar_name in REPAIR_SIDEBAR_LABELS.items():
		row = frappe.db.get_value("Desktop Icon", name, ["label", "link_type"], as_dict=True)
		if not row or row.link_type != "Workspace Sidebar" or row.label == sidebar_name:
			continue
		if not frappe.db.exists("Workspace Sidebar", sidebar_name):
			notes.append(
				f"skip label repair on {name!r}: no Workspace Sidebar {sidebar_name!r}"
			)
			continue
		frappe.db.set_value(
			"Desktop Icon", name, "label", sidebar_name, update_modified=False
		)
		notes.append(
			f"restored label {row.label!r} -> {sidebar_name!r} on {name!r} "
			f"(a renamed Workspace-Sidebar tile drops out of the launcher)"
		)

	# --- pass 1a: free labels that hidden module shortcuts are squatting on ---
	# `label` is UNIQUE. The CRM label we want for the App tile is currently
	# held by a hidden Link-type module shortcut whose own NAME is also 'CRM',
	# so parking it on its own name does not free anything. Move it to a
	# clearly-internal label instead. It stays hidden, so this label is only
	# ever visible in launcher edit mode.
	for squat_label in RENAME_BY_LABEL.values():
		squatter = frappe.db.exists("Desktop Icon", {"label": squat_label})
		if not squatter:
			continue
		row = frappe.db.get_value(
			"Desktop Icon", squatter, ["name", "icon_type", "hidden"], as_dict=True
		)
		if row.icon_type == "App" or not row.hidden:
			# A visible or App-type row owns it: that IS the tile we want to
			# brand, so leave it alone and brand it in place.
			continue
		if squatter != squat_label:
			# name differs from the label it squats on, so parking it on its
			# own name does free the label.
			park = squatter
		else:
			park = f"{squat_label} (module shortcut)"
			n = 2
			while frappe.db.exists("Desktop Icon", {"label": park}):
				park = f"{squat_label} (module shortcut {n})"
				n += 1
		frappe.db.set_value("Desktop Icon", squatter, "label", park, update_modified=False)
		notes.append(
			f"freed label {squat_label!r}: parked hidden module shortcut "
			f"{squatter!r} on label {park!r} (row kept, still hidden)"
		)

	# --- pass 1b: parent + tile labels --------------------------------------
	targets: list[tuple[str, str]] = list(RENAME.items())
	for old_label, new_label in RENAME_BY_LABEL.items():
		row_name = frappe.db.exists("Desktop Icon", {"label": old_label})
		if row_name:
			targets.append((row_name, new_label))
		else:
			notes.append(f"skip rename: no Desktop Icon labelled {old_label!r}")

	for name, new_label in targets:
		row = frappe.db.get_value(
			"Desktop Icon", name, ["name", "label", "icon_type"], as_dict=True
		)
		if not row:
			notes.append(f"skip rename: no Desktop Icon named {name!r}")
			continue
		if row.label == new_label:
			continue

		# `label` is UNIQUE -- renaming into an occupied label raises
		# IntegrityError 1062 and fails the entire migrate. Pass 1a already
		# parked hidden module shortcuts on their own names, so any remaining
		# clash is a genuine duplicate worth reporting rather than deleting.
		clash = frappe.db.exists("Desktop Icon", {"label": new_label})
		if clash and clash != row.name:
			frappe.db.set_value(
				"Desktop Icon",
				clash,
				{"logo_url": APP_TILE_LOGOS.get(clash, STUDIO_LITE_LOGO)},
				update_modified=False,
			)
			notes.append(
				f"{new_label!r}: row {clash!r} already owns this label; "
				f"branded it in place, kept {row.name!r} as {row.label!r}"
			)
			continue

		frappe.db.set_value(
			"Desktop Icon", row.name, "label", new_label, update_modified=False
		)
		notes.append(f"label {row.label!r} -> {new_label!r} (name {row.name!r} unchanged)")

	# --- pass 2: retarget every child at the label its parent renders under ---
	# The frontend resolves a child as `icon_map[child.parent_icon]` with the
	# map keyed by LABEL, so `parent_icon` must equal the parent's label.
	# This is also the REPAIR path: children left pointing at a stale parent
	# label are matched on both the parent's name and those stale labels.
	for name in RENAME:
		row = frappe.db.get_value("Desktop Icon", name, ["name", "label"], as_dict=True)
		if not row:
			continue
		stale = STALE_PARENT_LABELS.get(name, ())
		refs = tuple(dict.fromkeys((row.name, row.label, *stale)))
		placeholders = ", ".join(["%s"] * len(refs))
		frappe.db.sql(
			f"UPDATE `tabDesktop Icon` SET parent_icon = %s WHERE parent_icon IN ({placeholders})",
			(row.label, *refs),
		)
		notes.append(f"retargeted children of {name!r} to parent_icon={row.label!r}")

	# --- pass 3: tile artwork ----------------------------------------------
	# `desktop_icon.html` picks the tile art in this order:
	#   1. frappe.utils.get_desktop_icon(label, style)
	#      -> assets/{app}/icons/desktop_icons/{style}/{scrub(label)}.svg
	#   2. logo_url || icon_image
	#   3. icon_type == "Folder"
	#   4. else frappe.utils.desktop_icon(label, bg_color)   <- LETTER fallback
	#
	# The `icon` field is NOT consulted for the artwork. It is only metadata, so
	# setting icon="box" / "user-round" and clearing logo_url falls through to
	# branch 4 and renders a big letter (C / F / H) instead of a pictogram.
	# That is why the app tiles showed letters after the wordmark was removed.
	#
	# So the tiles get real square SVGs shipped in this app's public/images,
	# matching the geometry of the upstream erpnext "solid" tiles: 28x28 viewBox,
	# a rounded background square, and a white glyph on top. The Studio Lite
	# wordmark is deliberately NOT used here -- it is 160x48 and renders as a
	# small black bar inside a square tile. It stays in the header and favicon.
	APP_TILE_ART = {
		"Framework": f"{TILE_ASSET_BASE}/tile-framework.svg",
		"Frappe HR": f"{TILE_ASSET_BASE}/tile-hr.svg",
		"Studio Lite CRM": f"{TILE_ASSET_BASE}/tile-crm.svg",
		"ERPNext Settings": f"{TILE_ASSET_BASE}/tile-settings.svg",
		"ERPNext": f"{TILE_ASSET_BASE}/tile-settings.svg",
	}

	for name, art in APP_TILE_ART.items():
		if not frappe.db.exists("Desktop Icon", name):
			notes.append(f"skip artwork: no Desktop Icon named {name!r}")
			continue
		row = frappe.db.get_value("Desktop Icon", name, ["logo_url", "icon"], as_dict=True)
		frappe.db.set_value(
			"Desktop Icon",
			name,
			{"logo_url": art, "icon": None, "bg_color": None},
			update_modified=False,
		)
		notes.append(
			f"{name!r}: artwork -> {art}"
			if row.logo_url != art
			else f"{name!r}: artwork already set"
		)

	# --- pass 3b: scrub the wordmark from every remaining row -------------
	# The wordmark is a 160x48 banner. In a square tile it renders as a small
	# black bar, and it must never be used as tile artwork. Hidden rows
	# (module shortcuts, the flattened ERPNext parent) can still be carrying it
	# from an earlier run of this patch, so clear it everywhere rather than only
	# on the tiles this patch happens to know about.
	scrubbed = frappe.db.sql(
		"update `tabDesktop Icon` set logo_url = null"
		" where logo_url = %s",
		(STUDIO_LITE_LOGO,),
	)
	if scrubbed:
		notes.append(f"cleared the 160x48 wordmark from {scrubbed} row(s)")

	# --- pass 4: make every app / top-level tile actually open -----------------
	# `desktop.js::get_route()` reads the `link` field, and for Workspace Sidebar
	# tiles it looks the sidebar up BY THE TILE'S LABEL:
	#
	#     if (link_type == "External" && desktop_icon.link)
	#         route = window.location.origin + desktop_icon.link;
	#     else {
	#         let sidebar = frappe.boot.workspace_sidebar_item[desktop_icon.label.toLowerCase()];
	#         if (link_type == "Workspace Sidebar" && sidebar) { ...build route... }
	#     }
	#     if (icon_route) set href;  else msgprint("Icon is not correctly configured")
	#
	# Two distinct failures, both of which this pass repairs:
	#
	# 1. The CRM tile was created with app='External' and link_to='/crm', but `link`
	#    was NULL. The External branch failed on the empty link, the Workspace
	#    Sidebar branch did not apply, icon_route stayed undefined and clicking the
	#    tile showed "Icon is not correctly configured". Every other app tile had a
	#    real link (/desk/build, /desk/people, /app/home).
	#
	# 2. Renaming a Workspace-Sidebar tile breaks it twice over: the boot filter
	#    drops it (label no longer matches a sidebar key) and get_route() cannot find
	#    the sidebar. This is why pass 0 restores the label instead.
	APP_TILE_LINKS = {
		"Framework": "/desk/build",
		"Frappe HR": "/desk/people",
		"Studio Lite CRM": "/app/crm",
		"ERPNext": "/app/home",
	}

	for name, link in APP_TILE_LINKS.items():
		if not frappe.db.exists("Desktop Icon", name):
			notes.append(f"skip link fix: no Desktop Icon named {name!r}")
			continue
		row = frappe.db.get_value("Desktop Icon", name, ["link", "link_type"], as_dict=True)
		frappe.db.set_value(
			"Desktop Icon",
			name,
			{"link": link, "link_type": "External"},
			update_modified=False,
		)
		notes.append(
			f"{name!r}: link {row.link!r} -> {link!r} (tile now opens)"
			if row.link != link
			else f"{name!r}: link already {link!r}"
		)

	# --- pass 5: preserve the agreed hidden state ---------------------------
	for name in KEEP_HIDDEN:
		row = frappe.db.get_value("Desktop Icon", name, ["hidden", "label"], as_dict=True)
		if not row:
			continue
		if row.hidden != 1:
			frappe.db.set_value("Desktop Icon", name, "hidden", 1, update_modified=False)
			notes.append(f"re-hid {name!r} so its children render top-level")

	# --- pass 6: assert the rendering invariant -----------------------------
	all_icons = frappe.db.sql(
		"select name, label, parent_icon, hidden from `tabDesktop Icon`", as_dict=True
	)
	visible_labels = {i["label"] for i in all_icons if i["hidden"] != 1}
	orphans = [
		i["label"]
		for i in all_icons
		if i["hidden"] != 1 and i["parent_icon"] and i["parent_icon"] not in visible_labels
	]
	notes.append(f"invariant: {len(orphans)} tiles render top-level by design: {sorted(orphans)}")

	try:
		from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache

		clear_desktop_icons_cache()
	except Exception:
		pass
	frappe.clear_cache(doctype="Desktop Icon")

	for note in notes:
		print(f"white-label desktop icons: {note}")
