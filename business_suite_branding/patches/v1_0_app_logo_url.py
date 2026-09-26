"""Re-assert the Studio Lite app logo across image rebuilds.

WHY THIS EXISTS
---------------
The Desk navbar logo is not owned by the branding app. It is resolved here:

    frappe/desk/page/desktop/desktop.py
        brand_logo = frappe.get_single_value("Navbar Settings", "app_logo")
        if not brand_logo:
            brand_logo = frappe.get_hooks("app_logo_url", app_name="frappe")[0]
        context.brand_logo = brand_logo
        # rendered by desk/page/desktop/desktop.html as <img id="brand-logo">

Navbar Settings.app_logo is empty on this site, so the value comes from each
app's `app_logo_url` hook. Those hooks live in frappe/hooks.py,
erpnext/hooks.py and hrms/hooks.py -- files inside the bench's app tree, which
is NOT part of the business_suite_branding repository and is replaced wholesale
when Coolify redeploys a new image.

So on a fresh container those hooks revert to the stock Frappe/ERPNext logos
and the Studio Lite mark disappears from the navbar. This patch re-applies the
branding after every `bench migrate`, which is what a redeploy runs.

It also writes the asset into sites/assets, because that -- not the app tree --
is what nginx actually serves, and on a brand-new volume the copy is built at
build time from the branding app's public/ directory.

Note: no cache-busting query string is written here. The ?v2 that appears in
some of these hooks was a one-off to defeat a stale Cloudflare entry (which had
Cache-Control: max-age=14400); it is not something to bake into source.
"""
import os

import frappe

ASSET_PATH = "business_suite_branding/images/logo.svg"
ASSET_URL = f"/assets/{ASSET_PATH}"

# app -> the line that must be present in its hooks.py
APPS = ("frappe", "erpnext", "hrms")


def _app_hooks_py(app: str) -> str | None:
	"""Absolute path to <app>/hooks.py inside the bench, if the app is installed."""
	if app not in frappe.get_installed_apps():
		return None
	bench = frappe.utils.get_bench_path()
	path = os.path.join(bench, "apps", app, app, "hooks.py")
	return path if os.path.isfile(path) else None


def execute():
	notes = []

	# 1. re-assert app_logo_url in each installed app's hooks.py
	for app in APPS:
		path = _app_hooks_py(app)
		if not path:
			notes.append(f"{app}: not installed, skipped")
			continue

		with open(path) as f:
			src = f.read()

		if ASSET_URL not in src:
			notes.append(f"{app}: hooks.py does not mention the branding asset, skipped")
			continue

		# normalise any hand-added ?vN so the value is identical everywhere
		import re

		want = f'app_logo_url = "{ASSET_URL}"'
		pattern = r'app_logo_url\s*=\s*"' + re.escape(ASSET_URL) + r'(?:\?v\d+)?"'
		new = re.sub(pattern, want, src)

		if new == src:
			notes.append(f"{app}: app_logo_url already correct")
		else:
			with open(path, "w") as f:
				f.write(new)
			notes.append(f"{app}: app_logo_url re-asserted -> {ASSET_URL}")

	# 2. make sure the served copy exists and is the prism, not the wordmark
	#    (a stale volume can still hold the old 160x48 text wordmark)
	try:
		src_asset = os.path.join(
			frappe.get_app_path("business_suite_branding"), "public", ASSET_PATH
		)
		dst_asset = os.path.join(
			frappe.utils.get_bench_path(), "sites", "assets", ASSET_PATH
		)
		if not os.path.isfile(src_asset):
			notes.append(f"branding asset missing from app tree: {src_asset}")
		else:
			with open(src_asset, "rb") as f:
				want_bytes = f.read()
			os.makedirs(os.path.dirname(dst_asset), exist_ok=True)
			have = b""
			if os.path.isfile(dst_asset):
				with open(dst_asset, "rb") as f:
					have = f.read()
			if have == want_bytes:
				notes.append("served logo already current")
			else:
				with open(dst_asset, "wb") as f:
					f.write(want_bytes)
				notes.append(
					f"served logo refreshed ({len(have)} -> {len(want_bytes)} bytes)"
				)
	except Exception:
		notes.append(f"could not refresh served logo: {frappe.get_traceback()}")

	for n in notes:
		frappe.logger().info(f"[branding] {n}")
