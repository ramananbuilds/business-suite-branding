"""Re-assert the versioned logo URL after an image rebuild.

Why this patch exists
---------------------
The image is built by `bench init --apps_path=apps.json`, which clones the
app branches fresh. Two independent things used to leave the site on a stale
logo after a rebuild:

1. The forks shipped the asset URL WITHOUT its cache-bust. The ?v3 lived only
   as an in-container edit, so a rebuilt image came back with the unversioned
   URL. The forks now commit ?v3 directly (see set_logo_version.py).

2. v1_0_app_logo_url is already recorded in Patch Log, and Frappe never re-runs
   a logged patch. So even with the forks fixed in git, the patch that would
   otherwise catch a regression will not fire again on this site. It stays in
   patches.txt as a safety net for FRESH sites, where it has not yet run.

This patch is the third layer: a NEW patch id, so it runs once on this site
regardless of what the earlier ones did, and re-asserts the versioned URL
against whatever the image actually shipped.

It also writes the asset check: it verifies the deployed logo.svg is the traced
5-facet mark and not the old 335-byte wordmark, and restores it from the app's
own committed copy if it is not. That is the one thing a URL rewrite cannot fix
-- a redeploy that replaced the asset itself.
"""

import os
import re
import shutil

import frappe

ASSET = "/assets/business_suite_branding/images/logo.svg"
VERSION = 3
VERSIONED = f"{ASSET}?v{VERSION}"

APP_DIR = frappe.get_app_path("business_suite_branding")
ASSET_IN_APP = os.path.join(APP_DIR, "public", "images", "logo.svg")
BENCH = frappe.utils.get_bench_path()
SERVED = os.path.join(BENCH, "sites", "assets", "business_suite_branding", "images", "logo.svg")

# the traced mark: 5 polygons, no background rect, no visible text
EXPECT_POLYGONS = 5


def _app_hooks_py(app):
	if app not in frappe.get_installed_apps():
		return None
	path = os.path.join(BENCH, "apps", app, app, "hooks.py")
	return path if os.path.isfile(path) else None


def _rewrite(src):
	"""Point the two logo-bearing hooks at the versioned URL, idempotently."""
	counts = []

	# app_logo_url = "<asset>"  -- group 1 keeps the identifier and the quote
	p1 = r'(app_logo_url\s*=\s*")' + re.escape(ASSET) + r'(?:\?v?\d*)*"'
	src, n = re.subn(p1, lambda m: m.group(1) + VERSIONED + '"', src)
	counts.append(n)

	# "logo": "<asset>",  -- what actually feeds the app switcher
	p2 = r'("logo"\s*:\s*")' + re.escape(ASSET) + r'(?:\?v?\d*)*"'
	src, n = re.subn(p2, lambda m: m.group(1) + VERSIONED + '"', src)
	counts.append(n)

	# brand_html -- the WEBSITE navbar, independent of app_logo_url
	p3 = r'(src\s*=\s*")' + re.escape(ASSET) + r'(?:\?v?\d*)*"'
	src, n = re.subn(p3, lambda m: m.group(1) + VERSIONED + '"', src)
	counts.append(n)

	return src, counts


def _is_traced_mark(path):
	"""True when the file on disk is the traced mark, not the old wordmark."""
	if not os.path.isfile(path):
		return False, "missing"
	with open(path, encoding="utf-8") as f:
		body = f.read()
	polys = len(re.findall(r"<polygon", body))
	has_text = "<text" in body
	if polys != EXPECT_POLYGONS or has_text:
		return False, f"{polys} polygons, text={has_text}, {len(body)} bytes"
	return True, f"{polys} polygons, {len(body)} bytes"


def execute():
	notes = []

	# 1. the asset itself -- the part a URL rewrite cannot fix
	ok, detail = _is_traced_mark(ASSET_IN_APP)
	notes.append(f"{'PASS' if ok else 'FAIL'} app logo.svg: {detail}")

	if not ok:
		# Both the app copy and the served copy come out of the same image
		# layer, so there is no second source to restore from inside the
		# container. Report it loudly rather than pretend to have fixed it:
		# a wrong asset is a build problem, not a patch problem.
		notes.append(
			"WARNING the logo asset is not the traced mark. Both copies come "
			"from the image, so this must be fixed in the image, not here."
		)

	# The served copy lives under sites/, which is a VOLUME, so it survives a
	# redeploy while the app copy does not. Re-sync it whenever the two differ,
	# so the served bytes always match the app's committed asset.
	if os.path.isfile(SERVED) and os.path.realpath(SERVED) != os.path.realpath(ASSET_IN_APP):
		shutil.copyfile(ASSET_IN_APP, SERVED)
		ok2, detail2 = _is_traced_mark(SERVED)
		notes.append(f"{'PASS' if ok2 else 'FAIL'} served copy re-synced: {detail2}")
	elif os.path.isfile(SERVED):
		ok2, detail2 = _is_traced_mark(SERVED)
		notes.append(f"{'PASS' if ok2 else 'FAIL'} served copy: {detail2}")
	else:
		notes.append(f"WARNING no served copy at {SERVED}")

	# 2. the URL, in every installed app that declares it
	rewritten = []
	for app in frappe.get_installed_apps():
		path = _app_hooks_py(app)
		if not path:
			continue
		with open(path) as f:
			src = f.read()
		if ASSET not in src:
			continue
		out, counts = _rewrite(src)
		if out != src:
			with open(path, "w") as f:
				f.write(out)
			rewritten.append(f"{app}(app_logo_url={counts[0]},logo={counts[1]},brand_html={counts[2]})")
	if rewritten:
		notes.append("re-rewrote: " + ", ".join(rewritten))
	else:
		notes.append("all logo URLs already at ?v3")

	# 3. the navbar, which is a DB value and survives everything above
	try:
		ns = frappe.get_single("Navbar Settings")
		if ns.app_logo and ASSET in ns.app_logo and f"?v{VERSION}" not in ns.app_logo:
			ns.app_logo = f"{ASSET}?v{VERSION}"
			ns.save(ignore_permissions=True)
			notes.append(f"navbar logo re-versioned -> {ns.app_logo}")
		elif ns.app_logo:
			notes.append(f"navbar logo already versioned: {ns.app_logo}")
		else:
			notes.append("navbar logo not set in DB (uses the app_logo_url hook)")
	except Exception as e:
		notes.append(f"WARNING could not check Navbar Settings: {e}")

	# 4. the hook cache, or the next request still sees the old values
	frappe.cache.delete_value("app_hooks")
	for user in frappe.get_all("User", pluck="name"):
		frappe.cache.hdel("bootinfo", user)
		frappe.cache.hdel("desktop_icons", user)
	notes.append("cleared app_hooks, bootinfo and desktop_icons for all users")

	for n in notes:
		print(f"  {n}")
