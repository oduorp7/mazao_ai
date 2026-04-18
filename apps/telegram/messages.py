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

/report  — Generate today's business report
/vat     — See your current VAT estimate
/kra     — Next KRA deadlines & amounts
/status  — Your account & subscription status
/stop    — Pause daily reports
/resume  — Resume daily reports
/help    — Show this menu

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
