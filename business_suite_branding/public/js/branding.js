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
		document.title = BRANDING.product;

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

	run();

	window.addEventListener("load", run);

	const observer = new MutationObserver(run);

	observer.observe(document.documentElement, {
		childList: true,
		subtree: true,
	});
})();
