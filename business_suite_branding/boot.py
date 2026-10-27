"""Boot extensions for the Studio Lite desk."""

import frappe

# hrms declares both `add_to_apps_screen.route` and `app_home` as "/desk/people".
# That page has not existed since v16 replaced the old launcher: there is no
# Workspace, Sidebar or Desk Page named People, so the HR app icon lands on
# "Page people not found". Repoint it at the HR shell, which is the module home
# the icon was always meant to open.
REPAIRED_APP_ROUTES = {"hrms": "/desk/hr"}


def extend_bootinfo(bootinfo):
	bootinfo["studio_lite_branding"] = {
		"product_name": "Studio Lite",
		"apps": {
			"frappe": {
				"title": "Studio Lite",
				"logo": "/assets/business_suite_branding/images/logo.svg",
			},
			"erpnext": {
				"title": "Studio Lite ERP",
				"logo": "/assets/business_suite_branding/images/logo.svg",
			},
			"crm": {
				"title": "Studio Lite CRM",
				"logo": "/assets/business_suite_branding/images/logo.svg",
			},
			"hrms": {
				"title": "Studio Lite HR",
				"logo": "/assets/business_suite_branding/images/logo.svg",
			},
		},
	}

	_repair_app_routes(bootinfo)


def _repair_app_routes(bootinfo) -> int:
	"""Rewrite app landing routes that name a page this desk does not serve.

	The route is read from the app's own hooks, so it cannot be fixed in the
	database and it comes back on every upstream upgrade. Rewriting it in the
	boot payload is the only place the branding app outranks the app that
	declares it.
	"""
	repaired = 0
	for app in bootinfo.get("app_data") or []:
		route = REPAIRED_APP_ROUTES.get(app.get("app_name"))
		if not route or app.get("app_route") == route:
			continue
		if _route_exists(route):
			app["app_route"] = route
			repaired += 1
	return repaired


def _route_exists(route: str) -> bool:
	"""/desk/<slug> resolves against a Workspace or a Sidebar carrying that slug."""
	if not route.startswith("/desk/"):
		return True
	slug = route[len("/desk/") :].strip("/")
	if not slug:
		return True
	for doctype in ("Workspace", "Sidebar"):
		if not frappe.db.exists("DocType", doctype):
			continue
		for name in frappe.get_all(doctype, pluck="name"):
			if name.lower().replace(" ", "-") == slug:
				return True
	return False
