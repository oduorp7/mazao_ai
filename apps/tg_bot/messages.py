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

To get started, what's your business name?

_By using Mazao AI you agree to our privacy policy. Type /privacy to read it._
"""

ONBOARDING_SUCCESS_BUSINESS = """
🎉 *You're all set, {name}!* {founding_badge}

Welcome to the future of Kenyan bookkeeping.

*Trial Status:*
Your 14-day free trial starts now.
*Trial ends:* {trial_ends_at}

*3 Things to Do Next:*
1. *Analyze:* Upload your M-Pesa statement (/report)
2. *Monitor:* Set your Till number (/till)
3. *Comply:* Check your compliance calendar (/status)

Type /help to see all commands.
"""

ONBOARDING_SUCCESS_INDIVIDUAL = """
🎉 *You're all set, {name}!* {founding_badge}

I'll track your personal KRA deadlines and SHA reminders.

*Trial Status:*
Your 14-day free trial starts now.
*Trial ends:* {trial_ends_at}

Type /help anytime to see your commands.
"""

ONBOARDING_SUCCESS_BUSINESS_SW = """
🎉 *Umekamilisha usajili, {name}!* {founding_badge}

Karibu kwenye mfumo wa kisasa wa vitabu vya biashara Kenya.

*Hali ya Jaribio (Trial):*
Jaribio lako la siku 14 linaanza sasa.
*Mwisho wa jaribio:* {trial_ends_at}

*Mambo 3 ya Kufanya Sasa:*
1. *Uchambuzi:* Pakia ripoti yako ya M-Pesa (/report)
2. *Ufuatiliaji:* Weka namba yako ya Till (/till)
3. *Uzingatiaji:* Angalia kalenda yako ya ushuru (/status)

Andika /help kuona maagizo yote.
"""

ONBOARDING_SUCCESS_INDIVIDUAL_SW = """
🎉 *Umekamilisha usajili, {name}!* {founding_badge}

Nitafuatilia tarehe zako za mwisho za KRA na kumbusho za SHA.

*Hali ya Jaribio (Trial):*
Jaribio lako la siku 14 linaanza sasa.
*Mwisho wa jaribio:* {trial_ends_at}

Andika /help wakati wowote kuona maagizo yako.
"""

ASK_MPESA_TILL = """\
✅ Great!

Now I need your *M-Pesa Till or Paybill number* so I can pull your transactions automatically.

Send it now (numbers only, e.g. `123456`)\
"""

SETUP_COMPLETE = """\
🎉 *You're all set!* 

Here's what happens next:
• Tomorrow at *7:00 AM* you'll receive your first daily report
• I'll track your deadlines automatically
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
/kra      — Next deadlines & amounts
/status   — Your account & subscription status
/settings — ⚙️ Edit your profile
/mystatus — Individual status
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
Plan: {plan}
Status: {status}
Language: {language}
{trial_line}
Last report: {last_report}

To update any details: /settings\
"""

# ── /settings (HF-T4) ──────────────────────────────────────────────────────────

SETTINGS_MENU = """\
⚙️ *Account Settings*

Select what you'd like to update:
"""

SETTINGS_EDIT_NAME_PROMPT = "🏢 *Edit Business Name*\nPlease enter your new business name:"
SETTINGS_EDIT_PHONE_PROMPT = "📱 *Edit Phone Number*\nPlease enter your new M-Pesa phone number:"
SETTINGS_EDIT_TILL_PROMPT = "📡 *Edit Till Number*\nPlease enter your new M-Pesa Till or Paybill number:"
SETTINGS_EDIT_VAT_PROMPT = "💰 *VAT Status*\nAre you registered for VAT?"
SETTINGS_EDIT_EMPLOYEES_PROMPT = "👥 *Employees*\nDo you have any employees?"

SETTINGS_UPDATED = "✅ *{field} updated!*\nNew value: {new_value}"
SETTINGS_INVALID_INPUT = "❌ *Invalid {field}*\nPlease try again with a valid value."

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

*Option 1 (Recommended):* Paste the full KPLC token SMS:
```
Mtr:0277100839863
Token:0967-8847-2772-1258-0314
Date:20260422 12:47
Units:28.3
Amt:1000.00
TknAmt:525.26
OtherCharges:474.74
```

*Option 2 (Quick):* Enter units and date:
`25.5 22/04/2026`
Optional with amount: `25.5 22/04/2026 1000`

_Full SMS paste gives you tariff tier detection and accurate cost breakdown._
"""

TOKEN_RECORDED_SUCCESS = """
⚡ *Token Recorded!*

Units: {units}
Est. Daily Rate: {daily_rate} units
🗓️ *Depletion Date:* {depletion_date}
⏳ *Days left:* {days_remaining}
{breakdown}
"""

TOKEN_COST_BREAKDOWN = """
💡 *Cost Breakdown (from your token):*
Actual electricity: KES {elec_amount:,.2f} ({elec_pct:.0f}%)
Taxes & levies: KES {tax_amount:,.2f} ({tax_pct:.0f}%)
Rate: KES {rate_per_unit:.2f}/unit
Tariff: {tariff_tier}
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

PAYMENT_CONFIRMED = """
✅ *Payment Received — Thank you!*

Your Mazao AI subscription is now active on the *{plan_name}* plan.
Amount: KES {amount:,.2f}

Type /help to see all commands.
"""

RENEWAL_REMINDER = """
🔔 *Subscription Renewal Reminder*

Your Mazao AI *{plan_name}* subscription will expire in *{days_remaining} days*.
To keep your daily reports and live feed active, please renew now.

[Click here to renew / upgrade]({upgrade_link})
"""

SUBSCRIPTION_EXPIRED = """
⚠️ *Subscription Expired*

Your Mazao AI subscription has expired. Your daily reports and live feed have been paused.
Please renew now to resume service.

[Click here to renew / upgrade]({upgrade_link})
"""

PRIVACY_POLICY_TEXT = """
🛡️ *Mazao AI Privacy Policy*

*1. Data We Collect:*
We collect your Telegram ID, business name, user type, M-Pesa Till (optional), tax obligations (VAT/PAYE), and employment status to provide our services.

*2. Why We Collect It:*
This data is used solely to generate your business reports, track tax deadlines, and manage your account.

*3. Retention Period:*
Your data is stored for the duration of your active subscription + 90 days after cancellation/expiry to allow for easy reactivation.

*4. Deletion Rights:*
You have the right to be forgotten. Type /stop to pause reports. To permanently delete all data, contact our support.

*5. Contact:*
For any data requests or privacy concerns, email us at: *privacy@mazao.ai*
"""

FOUNDING_BADGE = "⭐ *Founding Member*"

TILL_REGISTRATION_PROMPT = "🛡️ *M-Pesa Till Registration*\n\nPlease enter your M-Pesa Till or Paybill number (5-7 digits) to enable real-time payment alerts."

TILL_CONFIRMED = "✅ *Till Registered: {till_number}*\n\nMazao AI is now listening for payments to this number. You will receive an alert the moment a customer pays."

TILL_INVALID = "❌ *Invalid Till Number*\nPlease enter 5-7 digits only (e.g. 123456)."

NOT_ONBOARDED = "👋 *Wait! Let's get to know you first.*\n\nPlease type /start to complete your profile before using this command. It only takes 30 seconds!"

TOKEN_INVALID_VALUE = "❌ *Invalid Units*\nPlease enter a numeric value for electricity units (e.g. `25.5`)."

FULIZA_PARSE_FAILED = "❌ *Could not parse Fuliza SMS*\nPlease ensure you forwarded the correct M-Pesa Fuliza message containing the amount and due date."

FEEDBACK_PROMPT = "📝 *Send us your feedback*\n\nPlease type your feedback or report an issue below. Your message will be sent directly to our engineering team."

FEEDBACK_RECEIVED = "✅ *Feedback Received*\n\nThank you for helping us improve Mazao AI! Our team will review your message."

FEEDBACK_FORWARD = "📩 *New Feedback from {name} ({user_type}):*\n\n{message}"

REFERRAL_INFO = """
🎁 *Mazao AI Referral Program*

Share the love and save money!
1. Share your unique link:
`{referral_link}`

2. When a friend subscribes, you get **20% OFF** your next month!

Your Referral Code: `{code}`
"""

REFERRAL_SUCCESS_REFERRER = "🎉 *Referral Success!*\nYour friend *{name}* just subscribed! You've earned a **20% discount** on your next renewal."

ADMIN_DAILY_DIGEST = """
📊 *Mazao AI Daily Briefing*

🗓 *Last 24 Hours:*
👤 New Tenants: {new_tenants}
💰 Confirmed Revenue: KES {revenue:,.0f} ({payments_count} txns)

🚀 *Active Pipeline:*
⏳ Active Trials: {active_trials}
🎯 Expiring (3 days): {expiring_trials}

📝 *Feedback:*
💬 New Messages: {feedback_count}

_Keep building!_
"""

TILL_BUSINESS_ONLY = "ℹ️ Real-time Till monitoring is only available for Business accounts. Type /start to update your profile if needed."

PROVIDER_REGISTRATION_SUCCESS = "🚀 *Payment Bridge Active*\nReal-time feed via {provider} is connected."

PROVIDER_REGISTRATION_FAILED = "⚠️ *Payment Bridge offline*\nCould not register callback with {provider}. Manual uploads (/statement) still work."

LIVE_DATA_LABEL = "📡 *Live Feed (Intasend)*: {count} txns, last: {last_txn_time}"

# ── Phase 7: Billing & Monetisation ──────────────────────────────────────────

UPGRADE_PROMPT = """
🚀 *Upgrade Mazao AI*

Choose a plan to continue after your trial or to unlock premium features:

🔹 *Mtu Wenyewe* (KES {mtu_price}/mo)
• Daily business reports
• Automated VAT summaries
• Utility tracking (Tokens/Fuliza)

🔸 *Biashara* (KES {biashara_price}/mo)
• *Everything in Mtu Wenyewe*
• Advanced AI Business Insights
• Daily automated income tracking

Select a plan below:
"""

STK_PUSH_SENT = """
📲 *STK Push Sent*

I've sent a payment request for *KES {amount}* to your M-Pesa number *{phone}*.

1. Enter your M-Pesa PIN on your phone.
2. Wait a few seconds for confirmation.

Plan: *{plan_name}*
"""

PAYMENT_CONFIRMED = """
🎉 *Payment Confirmed!*

Thank you! Your *{plan_name}* subscription is now active.
Amount received: KES {amount}

All features are now unlocked. Type /help to see what you can do.
"""

PAYMENT_FAILED = """
❌ *Payment Failed*

Something went wrong with the payment request. Please try again or check your M-Pesa balance.

Support: {upgrade_link}
"""

UPGRADE_REQUIRED = """
🔒 *Feature Locked*

The *{feature_name}* feature requires an active subscription.

Your trial has expired. Upgrade now to keep managing your business with AI:
{upgrade_link}
"""

TRIAL_REMINDER = """
💡 *Quick Tip*: You have *{days_remaining} days* left in your free trial. Upgrade anytime with /upgrade.
"""

TRIAL_EXPIRY_WARNING = """
⚠️ *Trial Expiry Warning*

Your Mazao AI free trial ends in *{days_remaining} days*. 

Upgrade to a paid plan today to ensure your daily reports and compliance alerts are never interrupted.
Type /upgrade to see options.
"""

TRIAL_EXPIRED = """
🛑 *Trial Expired*

Your free trial has ended and your automated reports are now paused.

Don't lose your business momentum! Upgrade to a paid plan now to resume full service.
Type /upgrade to get started.
"""
