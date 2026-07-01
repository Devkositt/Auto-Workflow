import os
import time
import subprocess
import pyautogui
import pyperclip
from datetime import datetime

# 📁 CONFIGURATION
PROJECT_PATH = "/Users/mac/Desktop/waansaung/delivery-app-backend"  # 🎯 ဆရာကြီးရဲ့ လမ်းကြောင်းအမှန် ပြောင်းလဲပြီး
WAANSAUNG_CHAT_ID = "oc_9163bbd749c0fb104770e12f6f46ca94"

# Target Chat IDs အားလုံး
TARGET_CHATS = [
    "oc_faff39e61d6f6f61117e5c7c47e350b9",
    "oc_feea11a61c042d4938dc2bfbc368ecaa",
    "oc_72fd177739021fa79490191476ec52f3",
    "oc_f8b87db17911b7e088a0115bd803396b",
    "oc_80e57dbda4baa5f9470e6517cef84ac4",
    "oc_f194d9459b56af6cef4e1074bfb10faa",
    "oc_845f65876a01f56fabf931edd6424d1a"
]

def check_for_new_messages_and_run():
    print("[+] Real-time Listener Active... Waiting for 08:10 AM to start scanning...")
    
    while True:
        try:
            now = datetime.now()
            current_time_str = now.strftime("%H:%M")
            
            start_time = now.replace(hour=8, minute=10, second=0, microsecond=0)
            end_time = now.replace(hour=16, minute=30, second=0, microsecond=0)
            
            if now >= start_time and now < end_time:
                print(f"\n[+] Active Scanning Cycle Started at {now.strftime('%I:%M:%S %p')}...")
                os.system("open -a Lark 2>/dev/null || open -a LarkSuite 2>/dev/null")
                time.sleep(2)
                
                combined_text = ""
                
                for idx, chat_id in enumerate(TARGET_CHATS, 1):
                    print(f"[{idx}/{len(TARGET_CHATS)}] Reading Chat ID: {chat_id}")
                    chat_content = read_chat_via_url(chat_id)
                    combined_text += f"\n--- CHAT ID: {chat_id} ---\n{chat_content}"
                    time.sleep(1)
                
                # 🎯 ဤနေရာတွင် Mention နာမည်အမှန် ပြောင်းထားပါသည်
                keywords = ["backend", "api", "query", "fix", "bug", "@williams kositt"]
                if any(word in combined_text.lower() for word in keywords):
                    print("[🚀] Backend Mention (@Williams Kositt) Detected! Triggering VS Code Codex...")
                    execute_codex_and_push(combined_text)
                else:
                    print("[-] No new backend updates required in this cycle.")
                    
                print("[+] Sleeping for 5 minutes before next active scan...")
                time.sleep(300)
                
            # 🏁 ညနေ ၄:၃၀ သို့မဟုတ် ၄:၃၀ ကျော်လျှင် Scan ရပ်ပြီး Report အော်တို တင်မည်
            elif now.hour == 16 and now.minute >= 30:
                print(f"[!] 16:30 PM or later reached ({current_time_str}). Executing Daily Report...")
                generate_and_post_report()
                print("[+] Report Posted. System going to standby until tomorrow 08:10 AM...")
                time.sleep(40000) # နောက်တစ်နေ့ ရုံးချိန်အထိ အိပ်ခိုင်းထားခြင်း
                
            else:
                print(f"[-] Outside working hours ({current_time_str}). Standby Mode...", end="\r")
                time.sleep(60)
                
        except Exception as e:
            print(f"[X] Error in main loop: {e}")
            time.sleep(10)

def read_chat_via_url(chat_id):
    url = f"lark://app/client/chat/ch_open?chatId={chat_id}"
    subprocess.run(["open", url])
    time.sleep(3.5)

    screen_width, screen_height = pyautogui.size()
    pyautogui.rightClick(screen_width // 2, screen_height - 200)
    time.sleep(0.6)
    pyautogui.press('down')
    time.sleep(0.2)
    pyautogui.press('down')
    time.sleep(0.2)
    pyautogui.press('enter')
    time.sleep(0.8)
    return pyperclip.paste()

# 🎯 Real-time အလုပ်လုပ်မည့် Codex Logic ကို shell=True ဖြင့် ပြင်ဆင်ပြီး
def execute_codex_and_push(tasks_text):
    os.chdir(PROJECT_PATH)
    
    # Codex အတွက် သန့်သန့်ရှင်းရှင်း prompt ထုတ်ပေးခြင်း
    escaped_tasks = tasks_text.replace('"', '\\"')
    codex_cmd = f'codex "Review these Lark messages and implement or fix any backend APIs or logic requested: {escaped_tasks}"'
    
    print("[+] Codex Agent is processing requirements and coding...")
    subprocess.run(codex_cmd, shell=True)
    time.sleep(5)
    
    # GitHub Push
    print("[+] Pushing updates to GitHub...")
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", "auto(backend): auto-implemented from real-time lark trigger"])
    subprocess.run(["git", "push", "origin", "main"])
    print("[✓] Code successfully pushed to production git origin!")

# 🎯 စောစောက အောင်မြင်သွားသော Report Generation Logic အမှန် (Modified Version)
def generate_and_post_report():
    # ၁။ VS Code Open & Focus
    subprocess.run(["osascript", "-e", 'tell application "Visual Studio Code" to activate'])
    time.sleep(2.0)
    
    # Input Box ကို Clear လုပ်ပြီး Prompt အသစ်ထည့်ခြင်း
    pyautogui.click(x=320, y=800)
    time.sleep(0.5)
    pyautogui.hotkey('command', 'a')
    pyautogui.press('backspace')
    time.sleep(0.5)
    
    custom_prompt = """generate report for today work like this
Today Tasks
- example task
dont add sugguestion , give me complete version"""
    
    pyperclip.copy(custom_prompt)
    pyautogui.hotkey('command', 'v')
    time.sleep(0.8)
    pyautogui.press('enter')
    pyautogui.press('return')
    time.sleep(2.0)
    
    # ၂။ ၅ မိနစ် တိတိ ငြိမ်ပြီး စောင့်ဆိုင်းခြင်း
    print("[*] Waiting exactly 5 minutes (300 seconds) for complete output...")
    time.sleep(300.0)
        
    # ၃။ နေရာကွက်တိ (75, 690) ကနေ ကော်ပီကူးခြင်း
    print("[✓] Time up. Copying from verified coordinates (75, 690)...")
    pyautogui.moveTo(75, 690, duration=0.5)
    pyautogui.click()
    time.sleep(1.5)
    
    # ၄။ Lark App Launch & Paste
    print("[*] Moving to Lark Suite to deliver report...")
    subprocess.run(["osascript", "-e", 'tell application "Lark" to activate'])
    subprocess.run(["osascript", "-e", 'tell application "LarkSuite" to activate'])
    time.sleep(2.5)
    
    # Pinned Group ကို နှိပ်ခြင်း
    pyautogui.moveTo(220, 85, duration=0.5)
    pyautogui.click()
    time.sleep(2.5)
    
    # Message Box ထဲ Focus ယူခြင်း
    pyautogui.click(x=700, y=850)
    time.sleep(0.3)
    pyautogui.click(x=700, y=850)
    time.sleep(1.5)
    
    # ၅။ Command + V ဖြင့် Paste ချခြင်း (အမှားမပါစေရန် Safety)
    pyautogui.keyDown('command')
    time.sleep(0.2)
    pyautogui.press('v')
    time.sleep(0.2)
    pyautogui.keyUp('command')
    time.sleep(1.0)
    
    # ၆။ နောက်ဆုံး Enter ခေါက်၍ Message ပို့ခြင်း
    print("[✓] Sending report to Lark...")
    pyautogui.press('enter')
    
    print("[✓] Automation Flow Complete: Clean report delivered to Lark successfully!")
    
    pyautogui.hotkey('command', 'v')
    time.sleep(0.8)
    pyautogui.press('enter')
    print("[✓] Today's Work Report successfully posted to waansaung group!")

if __name__ == "__main__":
    check_for_new_messages_and_run()