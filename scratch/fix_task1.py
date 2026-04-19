
import sys

def update_handlers():
    path = 'apps/tg_bot/handlers.py'
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Update BOT_COMMANDS
    new_lines = []
    for line in lines:
        if 'BotCommand("mystatus"' in line and 'language' not in line:
            new_lines.append(line)
            new_lines.append('    BotCommand("language", "Change language / Badilisha lugha"),\n')
        else:
            new_lines.append(line)
    
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Updated handlers.py BOT_COMMANDS")

def update_bot():
    path = 'apps/tg_bot/bot.py'
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if 'app.add_handler(CommandHandler("mystatus"' in line and '"language"' not in line:
            new_lines.append(line)
            new_lines.append('    app.add_handler(CommandHandler("language", cmd_language))\n')
        else:
            new_lines.append(line)
            
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Updated bot.py handlers")

if __name__ == "__main__":
    update_handlers()
    update_bot()
