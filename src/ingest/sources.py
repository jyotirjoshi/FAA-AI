FAA_FAR_PART25 = "https://drs.faa.gov/browse/FAR/doctypeDetails?Status=Current&Status=Historical&CFR%20Part=Part%2025%20-%20AIRWORTHINESS%20STANDARDS:%20TRANSPORT%20CATEGORY%20AIRPLANES"
FAA_ECFR_PART25 = "https://www.ecfr.gov/current/title-14/chapter-I/subchapter-C/part-25"
FAA_ECFR_TITLE14 = "https://www.ecfr.gov/current/title-14"
FAA_ADVISORY_CIRCULARS = "https://www.faa.gov/regulations_policies/advisory_circulars/"
TC_CAR_525 = "https://tc.canada.ca/en/corporate-services/acts-regulations/list-regulations/canadian-aviation-regulations-sor-96-433/standards/airworthiness-chapter-525-transport-category-aeroplanes-canadian-aviation-regulations-cars"

ECFR_TITLE14_FULL_SOURCE = {
    "id": "faa_ecfr_title14_full",
    "url": FAA_ECFR_TITLE14,
}

DEFAULT_SOURCES = [
    {
        "id": "faa_far_part25",
        "url": FAA_FAR_PART25,
        "allow_prefixes": ["https://drs.faa.gov/"],
        "allow_pdf": True,
        "include_substrings": None,
        "max_pages": 1800,
    },
    {
        "id": "faa_advisory_circulars",
        "url": FAA_ADVISORY_CIRCULARS,
        "allow_prefixes": ["https://www.faa.gov/"],
        "include_substrings": [
            "/regulations_policies/advisory_circulars",
            "/documentLibrary/",
        ],
        "max_pages": 2200,
    },
    {
        "id": "faa_ecfr_part25_fallback",
        "url": FAA_ECFR_PART25,
        "allow_prefixes": ["https://www.ecfr.gov/"],
        "include_substrings": [
            "/part-25",
            "/section-25.",
            "title-14",
        ],
        "max_pages": 1800,
    },
    {
        "id": "tc_car_525",
        "url": TC_CAR_525,
        "allow_prefixes": ["https://tc.canada.ca/"],
        "include_substrings": [
            "airworthiness-chapter-525-transport-category-aeroplanes",
            "canadian-aviation-regulations-sor-96-433",
            "/standards/",
        ],
        "max_pages": 1400,
    },
]
