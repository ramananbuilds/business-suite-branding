"""Repair dead launcher links on sites that are already migrated.

The durable home for this logic is the `after_migrate` hook (see fixes.py):
`bench migrate` re-imports the upstream fixtures that create these rows, so a
one-shot patch cannot hold the line by itself. This patch exists so an
existing site is repaired when this version is installed, instead of waiting
for the next migrate to fire the hook.
"""
from business_suite_branding.fixes import after_migrate


def execute():
	after_migrate()
