import os
import time
import subprocess
import pyautogui
import pyperclip

def run_lark_automation():
    print("[+] Waking up MacBook Air display...")
    subprocess.run(["caffeinate", "-u", "-t", "5"])
    time.sleep(2)

    print("[+] Jumping directly to 'waansaung' group via Chat ID...")
    # Lark ၏ Direct Chat URL Scheme ကို သုံးခြင်း
    chat_id = "oc_9163bbd749c0fb104770e12f6f46ca94"
    lark_url = f"lark://app/client/chat/ch_open?chatId={chat_id}"
    
    # URL ဖြင့် Lark ကို ဖွင့်ပြီး သတ်မှတ်ထားသော Group ထဲ တန်းခုန်ဝင်ခြင်း
    subprocess.run(["open", lark_url])
    time.sleep(5)  # Group Chat Screen ပွင့်လာပြီး Text Area focus မိစေရန် စောင့်ခြင်း

    print("[+] Copying 'Ready to work' to clipboard...")
    pyperclip.copy("Ready to work")
    time.sleep(0.5)
    
    print("[+] Pasting text into Lark Chatbox...")
    # စာသားကို Paste ချခြင်း
    pyautogui.hotkey('command', 'v')
    time.sleep(1.8)  # စာသား သေချာဝင်သွားအောင် ခေတ္တစောင့်ခြင်း
    
    print("[+] Sending message...")
    # # 🚀 အော်တို စာပို့ရန်အတွက် Enter ကို ပြန်ဖွင့်ပေးလိုက်ခြင်း
    pyautogui.press('enter')
    print("[✓] Attendance successfully sent directly to 'waansaung' group!")

if __name__ == "__main__":
    run_lark_automation()