# Setup guide: make GCC Trend Desk ready to use

You do these steps once. They need your own logins, so nobody else can do them for you.
Allow about 60–90 minutes, plus Meta's review time if step 6 asks for it.

At the end, GitHub runs three jobs on its own servers (your PC can be off) and writes into the
**Product Discovery Tracker** Google Sheet:

| Job | When | Tab it fills |
| --- | --- | --- |
| Instagram pulse | Every hour | Instagram Pulse |
| Gulf shops | Daily, 09:11 IST | Gulf Shops, Gulf Shop Posts |
| Meta audience sizes | Monday, 09:53 IST | Audience Size |

**Golden rule:** tokens and keys go only into GitHub → Settings → Secrets. Never paste them in
chat, email, the sheet, or any file in this repository.

---

## Step 1 — Instagram business account (10 min)

1. In the Instagram app: **Profile → ☰ → Settings and privacy → Account type and tools → Switch to professional account → Business**.
   Use the shop's Instagram account (a new one is fine).
2. Create a **Facebook Page** for the business if you do not have one (facebook.com/pages/create).
3. Link them: on the Facebook Page, **Settings → Linked accounts → Instagram → Connect account**.

## Step 2 — Meta business portfolio and ad account (10 min)

1. Go to **business.facebook.com** and create a business portfolio (e.g. "Urbanleaf Ecommerce") if you have none.
2. **Settings → Accounts → Pages → Add** → your Page. **Instagram accounts → Add** → your Instagram account.
3. **Settings → Accounts → Ad accounts → Add → Create a new ad account.** Currency AED or INR, time zone Asia/Dubai.
   No payment method and no ad spend are needed for audience estimates.
4. Note the **ad account ID** (the digits after `act_`). This becomes the secret `META_AD_ACCOUNT_ID`.

## Step 3 — Meta developer app (10 min)

1. Go to **developers.facebook.com → My Apps → Create app**.
2. Use case: **Other** → app type **Business** → connect it to the business portfolio from step 2.
3. In the app dashboard, **Add product**: **Instagram** (choose *API setup with Facebook login*) and **Marketing API**.
4. Leave the app in **Development** mode for now.

## Step 4 — A token that does not expire (10 min)

A *system user* token keeps working without you logging in every 60 days.

1. **business.facebook.com → Settings → Users → System users → Add** → name `trend-desk`, role **Admin**.
2. **Assign assets** to it: your Page, your Instagram account, your ad account (view performance) and your app.
3. Click **Generate new token** → choose your app → expiry **Never** → tick these permissions:
   `instagram_basic`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement`,
   `business_management`, `ads_read`.
4. Copy the token **straight into GitHub** (step 7). Do not save it anywhere else.

## Step 5 — Your Instagram business account ID (5 min)

1. Open **developers.facebook.com/tools/explorer**, pick your app, paste the token into *Access token*.
2. Run: `me/accounts?fields=name,instagram_business_account`
3. The number under `instagram_business_account → id` is the secret `IG_USER_ID`.

## Step 6 — Hashtag search permission (may need Meta review)

Hashtag search uses Meta's **Instagram Public Content Access** feature. Business Discovery
(the Gulf shop tracking) and audience sizes do not need it.

1. In your app: **App Review → Permissions and Features → Instagram Public Content Access → Request**.
2. If Meta asks for **business verification**, use Urbanleaf Infrastructure Pvt. Ltd.'s documents
   (incorporation certificate or GST registration, plus a matching phone/email/website).
3. Describe the use honestly: *"We read public posts on Gulf shopping hashtags to see which consumer
   products are trending in the UAE and Saudi Arabia, for our own product research. Data stays in
   our internal Google Sheet."*
4. Until it is approved, the hourly Instagram pulse logs a permission error and writes nothing; the
   other two jobs still work. Run **Check setup** (step 9) to see which state you are in.

## Step 7 — Google service account so GitHub can write to the sheet (15 min)

1. Go to **console.cloud.google.com**, signed in as info.urbanleaf@gmail.com → **Select a project → New project** → name `trend-desk`.
2. **APIs & Services → Library → Google Sheets API → Enable.**
3. **APIs & Services → Credentials → Create credentials → Service account** → name `trend-desk` → Done.
4. Open the service account → **Keys → Add key → Create new key → JSON**. A file downloads.
5. Copy the service account's email (looks like `trend-desk@trend-desk-12345.iam.gserviceaccount.com`).
6. Open the **Product Discovery Tracker** sheet → **Share** → paste that email → **Editor** → untick *Notify* → Share.

## Step 8 — Add the four secrets to GitHub (5 min)

In this repository: **Settings → Secrets and variables → Actions → New repository secret**, four times:

| Secret name | Value |
| --- | --- |
| `IG_ACCESS_TOKEN` | the token from step 4 |
| `IG_USER_ID` | the number from step 5 |
| `META_AD_ACCOUNT_ID` | the ad account digits from step 2 |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | open the JSON file from step 7 in Notepad, copy **all** of it, paste |

Then delete the downloaded JSON file from your computer.

## Step 9 — Check, then switch on (5 min)

1. **Actions** tab → if asked, click **I understand my workflows, go ahead and enable them**.
2. **Check setup → Run workflow.** Open the run: every line should say `OK`.
   A `FAIL` line names the step to revisit.
3. Run **Instagram pulse**, **Gulf shops** and **Meta audience sizes** once each with **Run workflow**.
4. Open the sheet: the new tabs appear, and Candidates cells Q6–Q8 show the last run times.

From then on the jobs run on their own. GitHub emails info.urbanleaf@gmail.com if a run fails.

---

## Day to day

- **Change hashtags, shops or interests:** edit `config.yaml` on GitHub (pencil icon → Commit). Keep hashtags at 28 or fewer.
- **Add Gulf shops to track:** under `instagram → shops`, one line each: `- {username: shopname, country: UAE}`.
- **Free limits:** a private repo gets 2,000 free Actions minutes a month; these jobs use roughly 800.
- **If the token is ever exposed:** Business settings → System users → `trend-desk` → revoke, generate a new one, update the secret.

## What this does not do

- No scraping, no logins on your behalf, no third-party data sellers: only Meta's official APIs.
- Meta ad library, TikTok, Amazon, Noon, Google Trends and Pinterest stay with the Monday scan
  (`prompts/monday-scan.txt`), because no official API gives their Gulf data.
