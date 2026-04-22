import os
from telegram import Bot, BotCommand, BotCommandScopeChat
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)

# --- Command Definitions ---

CMD_COMMON_START = [
    BotCommand("start", "Start Mazao AI & Onboarding"),
    BotCommand("language", "Change language"),
    BotCommand("privacy", "Read Privacy Policy"),
    BotCommand("feedback", "Send feedback"),
    BotCommand("help", "Show available commands"),
]

CMD_COMMON_END = [
    BotCommand("settings", "Edit your profile"),
    BotCommand("language", "Change language"),
    BotCommand("stop", "Pause daily alerts"),
    BotCommand("resume", "Resume daily alerts"),
    BotCommand("feedback", "Send feedback"),
    BotCommand("privacy", "Read Privacy Policy"),
]

CMD_INDIVIDUAL_CORE = [
    BotCommand("help", "Show available commands"),
    BotCommand("mystatus", "Your KRA & SHA status"),
    BotCommand("tokens", "Log electricity units"),
    BotCommand("gas", "Log Gas refill"),
    BotCommand("fuliza", "Log Fuliza balance"),
    BotCommand("subscribe", "Add bill reminder"),
]

CMD_BUSINESS_CORE = [
    BotCommand("help", "Show available commands"),
    BotCommand("report", "Generate business report"),
    BotCommand("status", "Business dashboard"),
    BotCommand("till", "Register M-Pesa Till"),
    BotCommand("vat", "VAT liability check"),
    BotCommand("kra", "KRA obligation check"),
    BotCommand("statement", "View parsed statement"),
]

async def update_user_menu(bot: Bot, user_id: int, tenant: dict = None) -> bool:
    """
    P13: Progressive disclosure command menu.
    Determines user scope based on tenant data and sets the command menu for that user chat.
    """
    try:
        admin_id = os.getenv("ADMIN_TELEGRAM_ID")
        is_admin = str(user_id) == str(admin_id)
        
        # Determine scope
        if not tenant or not tenant.get("onboarding_completed"):
            # New or unregistered user
            commands = CMD_COMMON_START
            scope_name = "new_user"
        else:
            user_type = tenant.get("user_type", "individual")
            is_paid = tenant.get("plan") != "free"
            
            if is_admin:
                # Admin scope: all business_paid commands plus /admin
                core = CMD_BUSINESS_CORE
                commands = core + [BotCommand("admin", "Admin Dashboard")] + CMD_COMMON_END
                scope_name = "admin"
            elif user_type == "business":
                core = CMD_BUSINESS_CORE
                upgrade = [BotCommand("upgrade", "Upgrade to paid plan")] if not is_paid else []
                refer = [BotCommand("refer", "Refer a friend")]
                commands = core + upgrade + refer + CMD_COMMON_END
                scope_name = f"business_{'paid' if is_paid else 'free'}"
            else:
                # Individual
                core = CMD_INDIVIDUAL_CORE
                upgrade = [BotCommand("upgrade", "Upgrade to paid plan")] if not is_paid else []
                refer = [BotCommand("refer", "Refer a friend")]
                commands = core + upgrade + refer + CMD_COMMON_END
                scope_name = f"individual_{'paid' if is_paid else 'free'}"

        # Apply menu scope to the specific user chat
        scope = BotCommandScopeChat(chat_id=user_id)
        await bot.set_my_commands(commands, scope=scope)
        
        log.info("menu_scope_updated", user_id=user_id, scope=scope_name, cmd_count=len(commands))
        return True
    except Exception as e:
        log.error("menu_update_failed", user_id=user_id, error=str(e))
        return False
