# GCC Trend Desk

Official-API data engine for the India → GCC ecommerce business. GitHub Actions pull Gulf product
signals from Meta's official APIs and write them into the **Product Discovery Tracker** Google Sheet.

| Workflow | Schedule | Source (official API) | Sheet tab |
| --- | --- | --- | --- |
| Instagram pulse | hourly | Instagram Graph API — hashtag top + recent media | Instagram Pulse |
| Gulf shops | daily | Instagram Graph API — Business Discovery | Gulf Shops, Gulf Shop Posts |
| Meta audience sizes | weekly (Mon) | Meta Marketing API — delivery estimates | Audience Size |
| Check setup | manual | all of the above + sheet access | — |

**Start here: [SETUP.md](SETUP.md)** — the one-time, step-by-step configuration.

What is tracked lives in [`config.yaml`](config.yaml): hashtags per country, Gulf shops, interests.

Other parts of the system (outside this repo):
- Google Apps Script in the tracker: YouTube Data API scan, CSV imports, Dashboard.
- Monday browser scan on the founder's PC: Meta Ad Library, TikTok Creative Center, Amazon, Noon,
  Google Trends, Pinterest — instructions in [`prompts/monday-scan.txt`](prompts/monday-scan.txt).

Run locally: `pip install -r requirements.txt`, set the four secrets as environment variables,
then `python -m trenddesk check` (or `pulse`, `shops`, `audience`; add `--dry-run` to print instead of write).
Tests: `python -m pytest -q` (offline, no accounts needed).
