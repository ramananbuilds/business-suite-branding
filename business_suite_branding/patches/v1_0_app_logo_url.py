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

THE ?v2 QUERY STRING IS LOAD-BEARING, NOT COSMETIC
--------------------------------------------------
The asset is served with `Cache-Control: max-age=14400` and Cloudflare honours
it (`cf-cache-status: HIT`, `Age: 6606` observed). Frappe serves the navbar
logo by URL, with no build hash, so replacing logo.svg in place leaves every
cached copy pointing at the OLD 160x48 text wordmark for four hours. The
version query is what makes a logo change take effect immediately. Bump the
number in VERSION whenever the asset changes; do not strip it.
"""
import os
import re

import frappe

ASSET_PATH = "business_suite_branding/images/logo.svg"
ASSET_URL = f"/assets/{ASSET_PATH}"

# Bump when the asset's contents change, so Cloudflare and the browser both
# fetch the new file instead of a 4-hour-old cached copy of the previous one.
VERSION = 3
VERSIONED_URL = f"{ASSET_URL}?v{VERSION}"

def _patch_app_logo_url(src: str) -> tuple[str, int]:
	"""Point app_logo_url at the versioned URL, wherever it is declared."""
	pattern = r'app_logo_url\s*=\s*"' + re.escape(ASSET_URL) + r'(?:\?v\d+)?"'
	want = f'app_logo_url = "{VERSIONED_URL}"'
	return re.sub(pattern, want, src), len(re.findall(pattern, src))


def _patch_add_to_apps_screen(src: str) -> tuple[str, int]:
	"""Version the `logo` inside add_to_apps_screen, which is what actually wins.

	frappe/boot.py builds the app switcher like this:

	    app_info = frappe.get_hooks("add_to_apps_screen", app_name=app_name)[0]
	    app_logo_url = app_info.get("logo") or frappe.get_hooks(
	        "app_logo_url", app_name=app_name
	    )

	So `app_logo_url` is only a fallback: whenever add_to_apps_screen carries a
	logo, that value is what app_data reports and what the switcher renders.
	frappe/hooks.py was already versioned, which is why the Desk navbar and the
	frappe entry in the switcher were right while erpnext, hrms and crm stayed
	stale.
	"""
	pattern = r'("logo"\s*:\s*")' + re.escape(ASSET_URL) + r'((?:\?v\d+)?")'
	return re.sub(pattern, r"\g<1>" + VERSIONED_URL + r"\g<2>", src), len(
		re.findall(pattern, src)
	)


# every place the asset URL can be declared across the installed apps
HOOK_PATCHERS = (
	("app_logo_url", _patch_app_logo_url),
	("add_to_apps_screen", _patch_add_to_apps_screen),
)


def _app_hooks_py(app: str) -> str | None:
	"""Absolute path to <app>/hooks.py inside the bench, if the app is installed."""
	if app not in frappe.get_installed_apps():
		return None
	bench = frappe.utils.get_bench_path()
	path = os.path.join(bench, "apps", app, app, "hooks.py")
	return path if os.path.isfile(path) else None


def execute():
	notes = []

	# 1. re-assert the versioned asset URL wherever any installed app declares it
	for app in frappe.get_installed_apps():
		path = _app_hooks_py(app)
		if not path:
			continue

		with open(path) as f:
			src = f.read()

		if ASSET_URL not in src:
			continue

		new = src
		hits = 0
		for _label, patcher in HOOK_PATCHERS:
			new, n = patcher(new)
			hits += n

		if new == src:
			notes.append(f"{app}: logo URLs already {VERSIONED_URL}")
		else:
			with open(path, "w") as f:
				f.write(new)
			notes.append(f"{app}: {hits} logo URL(s) re-asserted -> {VERSIONED_URL}")

	# 1b. make sure no app is left advertising the unversioned asset, by any
	#     means -- a hook we do not know about would silently keep the old logo
	stale = []
	for app in frappe.get_installed_apps():
		path = _app_hooks_py(app)
		if not path:
			continue
		with open(path) as f:
			body = f.read()
		for m in re.finditer(re.escape(ASSET_URL) + r'(?:\?v(\d+))?', body):
			if not m.group(1):
				line = body[: m.start()].count("\n") + 1
				stale.append(f"{app}/hooks.py:{line}")
	if stale:
		notes.append(f"WARNING unversioned asset URL still present at: {', '.join(stale)}")

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
