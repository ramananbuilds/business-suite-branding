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
