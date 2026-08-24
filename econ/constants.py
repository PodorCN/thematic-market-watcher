"""Constants for global economic calendar monitor."""

# fxstreet API (used by ecocal) — free, no key, returns CSV/JSON
FXSTREET_API_URL = "https://calendar-api.fxstreet.com/en/api/v1/eventDates"
FXSTREET_BASE_URL = "https://www.fxstreet.com/"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Global coverage — same set ecocal uses, mapped to currency/code
# Keep ISO codes for filtering; fxstreet uses country codes like US, UK, EMU, DE, CN, JP, etc.
COUNTRY_MAP = {
    "US": "USD",
    "UK": "GBP",
    "EMU": "EUR",  # Eurozone
    "DE": "EUR",
    "FR": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "CN": "CNY",
    "JP": "JPY",
    "CA": "CAD",
    "AU": "AUD",
    "NZ": "NZD",
    "CH": "CHF",
    "UA": "UAH",
}

DEFAULT_COUNTRIES = list(COUNTRY_MAP.keys())

# Impact / volatility mapping (fxstreet uses NONE/LOW/MEDIUM/HIGH; ForexFactory uses Low/Medium/High)
IMPACT_LEVELS = ["LOW", "MEDIUM", "HIGH"]
VOLATILITIES = ["NONE", "LOW", "MEDIUM", "HIGH"]

# fxstreet category GUIDs — copied from ecocal/Calendar.py (covers all major releases)
# These 12 categories span CPI, GDP, employment, PMI, central banks, trade, etc.
FXSTREET_CATEGORIES = [
    "8896AA26-A50C-4F8B-AA11-8B3FCCDA1DFD",
    "FA6570F6-E494-4563-A363-00D0F2ABEC37",
    "C94405B5-5F85-4397-AB11-002A481C4B92",
    "E229C890-80FC-40F3-B6F4-B658F3A02635",
    "24127F3B-EDCE-4DC4-AFDF-0B3BD8A964BE",
    "DD332FD3-6996-41BE-8C41-33F277074FA7",
    "7DFAEF86-C3FE-4E76-9421-8958CC2F9A0D",
    "1E06A304-FAC6-440C-9CED-9225A6277A55",
    "33303F5E-1E3C-4016-AB2D-AC87E98F57CA",
    "9C4A731A-D993-4D55-89F3-DC707CC1D596",
    "91DA97BD-D94A-4CE8-A02B-B96EE2944E4C",
    "E9E957EC-2927-4A77-AE0C-F5E4B5807C16",
]

# ForexFactory fallback URLs
FOREXFACTORY_BASE = "https://www.forexfactory.com/calendar"

# Display helpers
IMPACT_COLOR = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟡", "NONE": "⚪"}
CURRENCY_EMOJI = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "CNY": "🇨🇳", "CAD": "🇨🇦", "AUD": "🇦🇺", "NZD": "🇳🇿",
    "CHF": "🇨🇭", "UAH": "🇺🇦",
}
