(() => {
	"use strict";

	const BRANDING = {
		product: "Studio Lite",

		apps: {
			frappe: {
				title: "Studio Lite",
				logo: "/assets/business_suite_branding/images/logo.svg",
			},

			erpnext: {
				title: "Studio Lite ERP",
				logo: "/assets/business_suite_branding/images/logo.svg",
			},

			crm: {
				title: "Studio Lite CRM",
				logo: "/assets/business_suite_branding/images/logo.svg",
			},

			hrms: {
				title: "Studio Lite HR",
				logo: "/assets/business_suite_branding/images/logo.svg",
			},
		},
	};

	function applyBranding() {
		// Guard: assigning document.title replaces the <title> text node, which is a
		// childList mutation. Without this check the observer below re-triggers
		// itself forever and locks the browser main thread (blank page).
		if (document.title !== BRANDING.product) {
			document.title = BRANDING.product;
		}

		if (!window.frappe?.boot) {
			return;
		}

		const appData = frappe.boot.app_data;

		if (Array.isArray(appData)) {
			for (const app of appData) {
				const brand = BRANDING.apps[app.app_name];

				if (!brand) {
					continue;
				}

				app.app_title = brand.title;
				app.app_logo_url = brand.logo;
			}
		}
	}

	function updateLogo() {
		const logo = document.querySelector(".header-logo img");

		if (logo) {
			logo.src = BRANDING.apps.frappe.logo;
			logo.alt = BRANDING.product;
		}
	}

	function run() {
		applyBranding();
		updateLogo();
	}

	// Coalesce observer bursts into a single run per animation frame so the
	// observer can never synchronously re-enter run() as a reaction to its own
	// DOM write.
	let scheduled = false;

	function scheduleRun() {
		if (scheduled) {
			return;
		}

		scheduled = true;

		requestAnimationFrame(() => {
			scheduled = false;
			run();
		});
	}

	run();

	window.addEventListener("load", run);

	const observer = new MutationObserver(scheduleRun);

	observer.observe(document.documentElement, {
		childList: true,
		subtree: true,
	});
})();
