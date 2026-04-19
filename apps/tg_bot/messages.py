"""
messages.py — Every message the bot sends, in one place.

Keeping strings here means:
  - Easy to translate to Swahili
  - Easy to A/B test copy
  - Handlers stay clean (logic only, no inline strings)
"""

# ── Onboarding ────────────────────────────────────────────────────────────────

WELCOME = """\
👋 *Habari! Welcome to Mazao AI*

I'm your automatic business bookkeeper.

Every morning I'll send you:
📊 Your M-Pesa income & expenses
📋 Your VAT liability estimate
⏰ KRA deadline reminders

*14-day free trial. No card needed.*

To get started, what's your business name?\
"""

ASK_MPESA_TILL = """\
✅ Great, *{business_name}*!

Now I need your *M-Pesa Till or Paybill number* so I can pull your transactions automatically.

Send it now (numbers only, e.g. `123456`)\
"""

ASK_KRA_PIN = """\
Got it — Till *{till_number}* ✅

Last one: what's your *KRA PIN*?
(e.g. `A012345678B`)

This lets me calculate your exact VAT and PAYE liability.\
"""

SETUP_COMPLETE = """\
🎉 *You're all set, {name}!*

Here's what happens next:
• Tomorrow at *7:00 AM* you'll receive your first daily report
• I'll track your KRA deadlines automatically
• Reply */report* anytime to generate one now

*Your 14-day free trial starts today.*
After that: KES 2,500/month — cancel anytime.

Type /help to see all commands.\
"""

# ── Main menu & help ──────────────────────────────────────────────────────────

HELP = """\
*Mazao AI — Commands*

/report   — Generate today's business report
/vat      — See your current VAT estimate
/kra      — Next KRA deadlines & amounts
/status   — Your account & subscription status
/mystatus — Individual KRA/SHA status
/language — Change language / Badilisha lugha
/stop     — Pause daily reports
/resume   — Resume daily reports
/help     — Show this menu

💬 You can also just message me any question about your business finances.\
"""

NOT_REGISTERED = """\
👋 You haven't set up your account yet.

Type /start to begin your free 14-day trial.\
"""

# ── Reports ───────────────────────────────────────────────────────────────────

REPORT_GENERATING = """\
⏳ Generating your report...

Pulling your M-Pesa transactions and crunching the numbers. Takes about 30 seconds.\
"""

REPORT_NO_DATA = """\
📭 *No transactions found*

I couldn't find any M-Pesa transactions for your Till *{till}* in the last 30 days.

Make sure your Till number is correct — type /status to check, or message me to update it.\
"""

# ── VAT ───────────────────────────────────────────────────────────────────────

VAT_SUMMARY = """\
📋 *VAT Estimate — {period}*

💰 Taxable sales:      KES {taxable_sales}
🏪 Supplier purchases: KES {supplier_spend}
➕ Output VAT (16%):   KES {output_vat}
➖ Input VAT (16%):    KES {input_vat}
━━━━━━━━━━━━━━━━━━━
📌 *Net VAT payable:   KES {net_vat}*

Due date: *{due_date}*
Days remaining: *{days_left}*

Reply /kra to see all upcoming obligations.\
"""

VAT_REFUND = """\
📋 *VAT Estimate — {period}*

Good news — you're in a *refund position*!
KRA owes you approximately *KES {refund}*

File your return before *{due_date}* to claim it.
Reply /help if you need the step-by-step iTax guide.\
"""

# ── KRA obligations ───────────────────────────────────────────────────────────

KRA_OBLIGATIONS_HEADER = "*⏰ Upcoming KRA Obligations*\n\n"

KRA_OBLIGATION_ROW = """\
{icon} *{obligation_type}* — Due {due_date}
   Est. amount: KES {amount:,.0f}
   Days left: {days_left}{overdue_flag}

"""

KRA_OBLIGATIONS_FOOTER = """\
_Reply /vat for detailed VAT breakdown_
_Reply /help for iTax filing guide_\
"""

KRA_NO_OBLIGATIONS = """\
✅ *No urgent KRA obligations*

All your filings appear to be up to date.
I'll alert you 7 days before each deadline.\
"""

# ── Deadline alerts (sent proactively by scheduler) ──────────────────────────

DEADLINE_7_DAYS = """\
⏰ *KRA Reminder — {obligation_type} due in 7 days*

📅 Due date: {due_date}
💰 Estimated amount: KES {amount:,.0f}
⚠️ Penalty if late: KES {penalty:,.0f}/month

Reply /vat to get your pre-filled summary ready.\
"""

DEADLINE_2_DAYS = """\
🚨 *URGENT — {obligation_type} due in 2 days!*

📅 Due date: {due_date}
💰 Amount to pay: KES {amount:,.0f}
💸 Penalty from {due_date}: KES {penalty:,.0f}/month

Don't wait — reply /vat now for your numbers.\
"""

DEADLINE_OVERDUE = """\
❗ *{obligation_type} is OVERDUE*

Filing now stops the penalty clock.
Current penalty: KES {penalty:,.0f}/month

Reply /help for the iTax step-by-step guide.\
"""

# ── Subscription ──────────────────────────────────────────────────────────────

TRIAL_WARNING = """\
⏳ *Your free trial ends in {days} days*

After that, Mazao AI is KES 2,500/month.

To continue, send KES 2,500 to Till *{till}*
with reference *MAZAO-{telegram_id}*

Questions? Just message me.\
"""

SUBSCRIPTION_CONFIRMED = """\
✅ *Payment received — thank you!*

Your Mazao AI subscription is active for another month.
Next charge: {next_date}

Type /help for all commands.\
"""

SUBSCRIPTION_LAPSED = """\
⚠️ *Your subscription has lapsed*

Your daily reports are paused.

To reactivate, send KES 2,500 to Till *{till}*
with reference *MAZAO-{telegram_id}*

Your data is safe — reports resume within minutes of payment.\
"""

# ── Status ────────────────────────────────────────────────────────────────────

STATUS = """\
*📊 Your Mazao AI Account*

Business: {business_name}
M-Pesa Till: {till_number}
KRA PIN: {kra_pin}
Plan: {plan}
Status: {status}
Language: {language}
{trial_line}
Last report: {last_report}

To update any details, message me directly.\
"""

# ── Errors ────────────────────────────────────────────────────────────────────

PIPELINE_ERROR = """\
😔 Something went wrong generating your report.

I've logged the error and will retry automatically tonight.
If this keeps happening, message me and I'll sort it manually.\
"""

UNKNOWN_MESSAGE = """\
I'm not sure what you mean by that.

Type /help to see all commands, or ask me a question about your business finances.\
"""

# ── Sprint 2: Individual & Statement Parsing ────────────────────────────────

USER_TYPE_SELECT = "👋 *First, tell us who you are:*\n\nAre you managing a business, or do you want to track your individual KRA & SHA status?"

INDIVIDUAL_ASK_NAME = "👤 Welcome! To get started, what is your *full name*?"

INDIVIDUAL_ASK_KRA = "✅ Great, *{name}*! Now, what is your *KRA PIN*? (e.g. `A012345678B`)"

INDIVIDUAL_ASK_EMPLOYMENT = "💼 What is your current *employment status*?\n\nThis helps me track the correct tax and SHA obligations for you."

INDIVIDUAL_ASK_SHA = "🏥 Do you have an *SHA (Social Health Authority) number*?\n\nIf you have one, send it now. Otherwise, type /skip to provide it later."

INDIVIDUAL_SETUP_COMPLETE = "🎉 *You're all set, {name}!*\n\nI'll track your personal KRA deadlines and SHA reminders.\n\nType /help anytime to see your commands."

MYSTATUS_HEADER = "👤 *Personal Status — {name}*\nStatus: {status}\n\n*Upcoming Obligations:*\n"

MYSTATUS_OBLIGATION_ROW = "{icon} *{name}* — Due {due_date}\n   {description}\n   Days left: {days_left}\n\n"

MYSTATUS_BUSINESS_REDIRECT = "ℹ️ This command is for individual users.\n\nUse /status for your business dashboard."

ASK_LANGUAGE = "🌐 *Language Preference / Mapendekezo ya Lugha*\n\nWhich language do you prefer for your reports?\nUnapendelea lugha gani kwa ripoti zako?"

LANGUAGE_SET_EN = "✅ Language set to *English*. You will receive your reports in English."

LANGUAGE_SET_SW = "✅ Lugha imewekwa kuwa *Kiswahili*. Utapokea ripoti zako kwa Kiswahili."

# ── Individual Deadline Alerts ───────────────────────────────────────────────

INDIVIDUAL_ANNUAL_RETURN_ALERT = """\
⏰ *KRA Reminder — Annual Income Tax Return*
📅 Due date: {due_date}
⏳ Days left: {days_left}
⚠️ Penalty: {penalty}

Declaration of income for the previous year is mandatory.\
"""

INDIVIDUAL_NIL_RETURN_ALERT = """\
⏰ *KRA Reminder — Nil Return*
📅 Due date: {due_date}
⏳ Days left: {days_left}
⚠️ Penalty: {penalty}

Mandatory zero-income declaration to avoid penalties.\
"""

INDIVIDUAL_SHA_ALERT = """\
🏥 *SHA Reminder — Health Contribution*
📅 Due date: {due_date}
⏳ Days left: {days_left}
⚠️ Penalty: {penalty}

2.75% of gross salary. Remind employer to verify if employed.\
"""

INDIVIDUAL_NSSF_ALERT = """\
🏦 *NSSF Reminder — Pension Contribution*
📅 Due date: {due_date}
⏳ Days left: {days_left}
⚠️ Penalty: {penalty}

Tier 1 and Tier 2 contributions are due to avoid compounded interest.\
"""

UNSUPPORTED_FILE_FORMAT = "⚠️ *Unsupported File Format*\n\nPlease send a .csv (from M-Pesa app) or forward your M-Pesa SMS text. PDFs are also supported if they contain text."

STATEMENT_RECEIVED_PARSING = "📥 *Statement received!*\n\nI'm parsing your transactions now. Please wait..."

STATEMENT_PARSE_FAILED = "❌ *Parsing Failed*\n\nI couldn't find any valid transactions in that file. Please ensure it is a standard M-Pesa CSV or PDF."

STATEMENT_PARSE_SUCCESS = "✅ *Parsing Successful!*\n\nLoaded *{count}* transactions. Generating your business report now..."

STATEMENT_REQUIRED = """\
📂 *No transactions found.*

Send me your M-Pesa statement to get started.

*How to get it:*
MySafaricom app → M-Pesa → Statement → Export CSV

Then send the file here."""

# ── Phase 4: Utility Prediction ──────────────────────────────────────────────

TOKEN_ENTRY_PROMPT = """
⚡ *Electricity Token Entry*
Please enter the number of units purchased and the date (DD/MM/YYYY).

Example: `25.5 20/04/2026`
"""

TOKEN_DEPLETION_ALERT = """
⚠️ *Electricity Token Alert*
Your tokens are running low!

📉 *Estimated remaining:* {units_remaining:,.1f} units
🗓️ *Estimated depletion:* {depletion_date}
⏳ *Days left:* {days_remaining} days

Top up soon to avoid a blackout!
"""

FULIZA_SMS_PROMPT = """
💸 *Fuliza SMS Tracker*
Please forward your Safaricom Fuliza balance SMS here.

Example: `Your Fuliza balance is KES 450.00. Please pay by 25/04/2026...`
"""

FULIZA_PARSED_CONFIRMATION = """
✅ *Fuliza SMS Parsed*
I've recorded your outstanding loan:

💰 *Balance:* KES {balance:,.2f}
📅 *Due Date:* {due_date}
⏳ *Time left:* {days_until_due} days

Note: Fuliza attracts a 1.0% daily administrative fee.
"""



# ── Phase 5: Subscriptions & Status ──────────────────────────────────────────

SUBSCRIBE_NAME_PROMPT = "💳 *New Subscription*\n\nWhat is the name of this subscription? (e.g., DStv, Netflix, Zuku WiFi)"
SUBSCRIBE_AMOUNT_PROMPT = "💰 *Monthly Amount*\n\nHow much is the monthly payment in KES?"
SUBSCRIBE_DAY_PROMPT = "🗓️ *Renewal Day*\n\nWhat day of the month does it renew? (Enter a number between 1 and 28)"
SUBSCRIBE_CONFIRMED = "✅ *Subscription Saved!*\n\nService: {name}\nAmount: KES {amount:,.2f}\nNext Reminder: {next_date}"

SUBSCRIPTION_REMINDER_ALERT = (
    "🔔 *Bill Reminder*\n\n"
    "Your subscription for *{name}* (KES {amount:,.2f}) is due in {days_until_due} days on *{renewal_date}*."
)

SUBSCRIPTIONS_LIST_HEADER = "📋 *Your Subscriptions*\n\n"
SUBSCRIPTIONS_EMPTY = "📂 You have no active subscriptions. Use /subscribe to add one."

BUSINESS_STATUS_DASHBOARD = (
    "🏢 *{business_name}* — Status Dashboard\n"
    "Plan: {plan_tier}\n"
    "━━━━━━━━━━━━━━━━━━━\n\n"
    "⚖️ *Tax Compliance*\n"
    "• VAT (due 20th): {vat_days} days\n"
    "• PAYE (due 9th): {paye_days} days\n"
    "• Annual Return (30 Jun): {annual_days} days\n\n"
    "📂 *Latest Statement Summary*\n"
    "{statement_summary}\n\n"
    "💳 *Subscriptions*\n"
    "• Active: {sub_count}\n"
    "• Next Renewal: {next_sub_date} ({sub_days} days)\n\n"
    "⏳ *Platform Status*: {platform_status}"
)

BUSINESS_STATUS_REDIRECT = "ℹ️ Please use /mystatus for your personal individual dashboard."
INDIVIDUAL_STATUS_REDIRECT = "ℹ️ Please use /status for your business dashboard."


# ── Phase 6: Payments & Africa's Talking Bridge ──────────────────────────────

PAYMENT_RECEIVED = "💸 *Payment Received!*\n\n💰 *Amount:* KES {amount:,.2f}\n👤 *From:* {name} ({msisdn})\n🔢 *Ref:* {trans_id}\n\n_Your profit report has been updated._"

TILL_REGISTRATION_PROMPT = "🛡️ *M-Pesa Till Registration*\n\nPlease enter your M-Pesa Till or Paybill number (5-7 digits) to enable real-time payment alerts."

TILL_CONFIRMED = "✅ *Till Registered: {till_number}*\n\nMazao AI is now listening for payments to this number. You will receive an alert the moment a customer pays."

TILL_INVALID = "❌ *Invalid Till Number*\nPlease enter 5-7 digits only (e.g. 123456)."

TILL_BUSINESS_ONLY = "ℹ️ Real-time Till monitoring is only available for Business accounts. Type /start to update your profile if needed."

PROVIDER_REGISTRATION_SUCCESS = "🚀 *Payment Bridge Active*\nReal-time feed via {provider} is connected."

PROVIDER_REGISTRATION_FAILED = "⚠️ *Payment Bridge offline*\nCould not register callback with {provider}. Manual uploads (/statement) still work."

LIVE_DATA_LABEL = "📡 *Live data via {provider}* ({count} txns, last: {last_txn_time})"


# ── Phase 7: M-Pesa STK Push Billing ─────────────────────────────────────────

UPGRADE_PROMPT = "💎 *Upgrade to Mazao AI Premium*\n\nChoose the plan that fits your business:\n\n1. *Mtu Wenyewe* (KES {mtu_price}/month)\n   ✅ Profit/Loss Reports\n   ✅ Utility Tracking\n\n2. *Biashara* (KES {biashara_price}/month)\n   ✅ Everything in Mtu Wenyewe\n   ✅ Daily AI Insights\n   ✅ Tax Compliance Dashboard"

STK_PUSH_SENT = "📲 *STK Push Sent*\nA prompt has been sent to *{phone}* for *KES {amount}*. Please enter your M-Pesa PIN to complete payment.\n\n_This request will expire in 60 seconds._"

PAYMENT_CONFIRMED = "🎉 *Payment Confirmed!*\n\nYour account is now active on the *{plan_name}* plan (KES {amount}).\n\nThank you for choosing Mazao AI! 🚀"

PAYMENT_FAILED = "❌ *Payment Failed*\nWe couldn't process your M-Pesa payment. This could be due to a timeout or insufficient funds.\n\nTry again: /upgrade"

UPGRADE_REQUIRED = "🔒 *Premium Feature*\n\nGenerating *{feature_name}* is only available on paid plans. Since your trial has expired, please upgrade to continue."

TRIAL_REMINDER = "⏳ *Trial Active*: {days_remaining} days left."

TRIAL_EXPIRY_WARNING = "⚠️ *Trial Ending Soon*\n\nYour free trial of Mazao AI Premium expires in *{days_remaining} days*. Upgrade now to keep your business insights flowing: /upgrade"

TRIAL_EXPIRED = "🔴 *Trial Expired*\n\nYour Mazao AI Premium trial has ended. Your compliance reminders will stay active, but /report and /status now require a subscription.\n\nUpgrade here: /upgrade"

