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

# ---------------------------------------------------------------------------
# Renames. Keyed by row NAME, which is never changed, so children that point
# at the name keep working.
# ---------------------------------------------------------------------------
RENAME = {
	"Frappe HR": "HR",
	"Framework": "Framework",
	"ERPNext": "ERPNext",
	"ERPNext Settings": "ERP Settings",
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

# The three "application" tiles all get the wordmark.
APP_TILE_LOGOS = {
	"Framework": STUDIO_LITE_LOGO,
	"Frappe HR": STUDIO_LITE_LOGO,
	"Studio Lite CRM": STUDIO_LITE_LOGO,
	"ERPNext": None,
}

# The CRM tile must resolve through the installed `crm` app, not the literal
# path /crm which 403s. `app` is an Autocomplete (Installed Applications), so
# it is written as a plain value and never resolved as a Link.
APP_TILE_APPS = {
	"Studio Lite CRM": "crm",
}

# Rows that must stay hidden to reproduce the agreed flat layout.
KEEP_HIDDEN = ["ERPNext"]


def execute():
	notes: list[str] = []

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

	# --- pass 3: logos ------------------------------------------------------
	for name, logo in APP_TILE_LOGOS.items():
		if not frappe.db.exists("Desktop Icon", name):
			notes.append(f"skip logo: no Desktop Icon named {name!r}")
			continue
		frappe.db.set_value("Desktop Icon", name, "logo_url", logo, update_modified=False)
	notes.append("app tile logos set")

	# --- pass 4: make the app tiles actually open ------------------------------
	# `desktop.js::get_route()` reads the `link` field, not `link_to`:
	#
	#     if (link_type == "External" && desktop_icon.link)
	#         route = window.location.origin + desktop_icon.link;
	#     else ... link_type == "Workspace Sidebar" ...
	#     if (icon_route) set href;  else msgprint("Icon is not correctly configured")
	#
	# The CRM tile was created with app='External' and link_to='/crm', but `link`
	# was left NULL. link_type is 'External', so the first branch fails on the empty
	# `link`, the Workspace Sidebar branch does not apply, `icon_route` stays
	# undefined and clicking the tile shows "Icon is not correctly configured".
	# The other app tiles all carry a `link` (/desk/build, /desk/people, /app/home).
	#
	# Point `link` at the real desk route for each app tile. /desk/people is the
	# workspace route HRMS registers; /app/crm is the CRM workspace.
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
