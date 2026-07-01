# Lark Codex Automation

Local automation web app for:

- reading prompt messages from Discord or Lark
- running `codex` or `gemini` against your backend project
- optionally auto-committing and auto-pushing git changes
- sending Codex result summaries and daily reports back to Discord or Lark

This README is written in both English and Myanmar.

## 1. What This Project Does

### English

This app watches a message source, isolates new prompt text, sends that prompt to a CLI coding agent, and posts back only the useful result summary.

Current practical setup:

- Prompt inbox: Discord channel
- AI result output: Discord channel
- Daily report output: Discord channel
- Optional morning report: Lark or Discord
- Code execution: `codex` by default
- Fallback: `gemini` when Codex usage limit is reached

### Myanmar

ဒီ app က message source တစ်ခုကို စောင့်ကြည့်ပြီး prompt အသစ်တွေကိုပဲ ခွဲထုတ်ဖတ်မယ်၊ ပြီးရင် CLI coding agent (`codex` / `gemini`) နဲ့ run မယ်၊ နောက်ဆုံး useful result summary ကိုပဲ ပြန်ပို့မယ်။

လက်ရှိ practical setup က:

- Prompt inbox: Discord channel
- AI result output: Discord channel
- Daily report output: Discord channel
- Optional morning report: Lark သို့မဟုတ် Discord
- Default code execution: `codex`
- Codex limit ပြည့်ရင် fallback: `gemini`

## 2. Run

### Command

```bash
python3 automation_web.py
```

Open:

```text
http://127.0.0.1:8787
```

Stop hotkey on macOS:

```text
Control + Option + S
```

### Myanmar

Terminal မှာ `python3 automation_web.py` run လုပ်ပြီး browser မှာ `http://127.0.0.1:8787` ဖွင့်ပါ။  
macOS မှာ run နေရင်း ချက်ချင်းရပ်ချင်ရင် `Control + Option + S` နှိပ်ပါ။

## 3. Important Rule About Keys / Secrets

### English

Do not hardcode secrets into source code.

Use the web UI Config form for:

- `LARK_APP_SECRET`
- `DISCORD_BOT_TOKEN`
- any other token/secret

`automation_config.json` is ignored by git in this project, so your local UI-saved secrets stay local.

### Myanmar

Secret / token / key တွေကို source code ထဲ hardcode မလုပ်ပါနဲ့။

အဲဒီ values တွေကို UI Config form ကနေပဲထည့်ပါ:

- `LARK_APP_SECRET`
- `DISCORD_BOT_TOKEN`
- တခြား secret/token အားလုံး

ဒီ project မှာ `automation_config.json` ကို git ignore လုပ်ထားလို့ UI က save လုပ်ထားတဲ့ secret တွေ local machine ထဲမှာပဲ နေမယ်။

## 4. Required Tools

### English

You need:

- Python 3
- Google Chrome
- Lark desktop app if you use `read_source = ui` or `send_source = ui`
- `codex` CLI if you want Codex runs
- optional `gemini` CLI if you want fallback

### Myanmar

လိုအပ်တာတွေက:

- Python 3
- Google Chrome
- `read_source = ui` သို့မဟုတ် `send_source = ui` သုံးမယ်ဆို Lark desktop app
- Codex run မယ်ဆို `codex` CLI
- fallback အတွက် optional `gemini` CLI

## 5. Configuration Fields

### English

Main fields in the UI:

- `project_path`: backend repository path that Codex/Gemini will edit
- `report_chat_id`: morning destination for Lark mode
- `codex_result_chat_id`: result channel/chat ID
- `evening_report_chat_id`: daily report channel/chat ID
- `read_source`: `discord`, `ui`, `api`, or `api_dm`
- `send_source`: `discord` or `ui`
- `provider`: `codex` or `gemini`
- `gemini_path`: path/command for Gemini CLI
- `codex_path`: path/command for Codex CLI
- `discord_prompt_channel_id`: prompt inbox channel
- `discord_bot_token`: Discord bot token
- `auto_push`: commit/push after successful AI run
- `dry_run`: preview only, no real post / no real Codex / no git push

### Myanmar

UI ထဲက အဓိက field တွေ:

- `project_path`: Codex/Gemini ကဝင်ပြင်မယ့် backend repo path
- `report_chat_id`: Lark mode နံနက်ပိုင်း destination
- `codex_result_chat_id`: result ပြန်ပို့မယ့် channel/chat ID
- `evening_report_chat_id`: daily report ပို့မယ့် channel/chat ID
- `read_source`: `discord`, `ui`, `api`, `api_dm`
- `send_source`: `discord` သို့မဟုတ် `ui`
- `provider`: `codex` သို့မဟုတ် `gemini`
- `gemini_path`: Gemini CLI path/command
- `codex_path`: Codex CLI path/command
- `discord_prompt_channel_id`: prompt ဝင်လာမယ့် Discord channel
- `discord_bot_token`: Discord bot token
- `auto_push`: AI run အောင်မြင်ရင် git commit/push လုပ်မလား
- `dry_run`: preview only mode

## 6. Recommended Real-World Setup

### English

Recommended setup for your current workflow:

1. `read_source = discord`
2. `send_source = discord`
3. `provider = codex`
4. `auto_switch_to_gemini_on_codex_limit = true`
5. `discord_prompt_channel_id = your prompts channel`
6. `codex_result_chat_id = your ai-result channel`
7. `evening_report_chat_id = your daily-report channel`
8. `project_path = your backend repo path`
9. turn `dry_run` off only after testing
10. turn `auto_push` on only after Codex result quality is acceptable

### Myanmar

မင်း workflow အတွက်အကောင်းဆုံး setup က:

1. `read_source = discord`
2. `send_source = discord`
3. `provider = codex`
4. `auto_switch_to_gemini_on_codex_limit = true`
5. `discord_prompt_channel_id = prompts channel ID`
6. `codex_result_chat_id = ai-result channel ID`
7. `evening_report_chat_id = daily-report channel ID`
8. `project_path = backend repo path`
9. စမ်းပြီးမှ `dry_run` ပိတ်
10. result quality သေချာပြီးမှ `auto_push` ဖွင့်

## 7. How Discord Prompt Reading Works

### English

When `read_source = discord`, the app:

1. reads the configured prompt channel
2. remembers the last processed Discord message ID
3. only processes newer user messages
4. ignores bot-authored messages
5. treats the prompt channel as a dedicated inbox, so keyword filtering is bypassed

### Myanmar

`read_source = discord` ဖြစ်ရင် app က:

1. သတ်မှတ်ထားတဲ့ prompt channel ကိုဖတ်မယ်
2. နောက်ဆုံးဖတ်ပြီးသား Discord message ID ကိုမှတ်ထားမယ်
3. အဲဒီထက်အသစ်ဖြစ်တဲ့ user message တွေပဲ process လုပ်မယ်
4. bot message တွေကို skip လုပ်မယ်
5. ဒီ channel ကို dedicated prompt inbox လို့သတ်မှတ်ထားတာမို့ keyword filtering ကို bypass လုပ်မယ်

## 8. How Discord Images Work

### English

Discord private CDN images often cannot be inspected reliably from plain public URLs alone.

This app now does the safer flow:

1. reads Discord message attachments
2. uses the Discord bot token to download image attachments locally
3. stores them under:

```text
.automation_cache/discord_attachments/
```

4. injects both the original image URL and the local cached image path into the AI prompt

This is more reliable than giving Codex only a Discord CDN URL.

### Myanmar

Discord private CDN image URL ကို plain URL တစ်ခုတည်းပေးရုံနဲ့ အမြဲတမ်း inspect လုပ်လို့မရဘူး။

အခု app က ဒီ safer flow ကိုသုံးတယ်:

1. Discord message attachment တွေကိုဖတ်မယ်
2. Discord bot token နဲ့ image file ကို local machine ထဲ download လုပ်မယ်
3. ဒီ folder အောက်မှာ cache သိမ်းမယ်

```text
.automation_cache/discord_attachments/
```

4. AI prompt ထဲကို original image URL နဲ့ local cached image path နှစ်ခုလုံးထည့်ပေးမယ်

ဒီနည်းက Discord CDN URL တစ်ခုတည်းပေးတာထက်ပိုတည်ငြိမ်တယ်။

## 9. Auto Push Behavior

### English

If `auto_push = true` and the AI run succeeds, the app:

1. checks the target repo branch
2. commits working tree changes if needed
3. pushes local commits to the current branch upstream

It does not force-push and does not switch branches automatically.

### Myanmar

`auto_push = true` ဖြစ်ပြီး AI run အောင်မြင်ရင် app က:

1. target repo ရဲ့ current branch ကိုစစ်မယ်
2. change ရှိရင် commit လုပ်မယ်
3. local commit တွေကို current branch upstream ဆီ push လုပ်မယ်

Force push မလုပ်ဘူး။ Branch အလိုအလျောက်မပြောင်းဘူး။

## 10. Morning / Evening Reports

### English

- Morning report posts the configured `morning_message`
- Evening report asks Codex to generate a structured summary
- Evening report posts only the report text, not the raw terminal log
- Result summaries and daily reports go to different destinations if configured that way

### Myanmar

- Morning report က `morning_message` ကိုပို့မယ်
- Evening report က Codex ကို structured summary ထုတ်ခိုင်းမယ်
- Evening report မှာ raw terminal log မပို့ဘဲ report text ပဲပို့မယ်
- Result summary နဲ့ daily report ကို destination ခွဲထားလို့ရတယ်

## 11. Sleep / Lock Screen

### English

- `discord` read/send mode can continue while the screen is locked, as long as the machine stays awake and network is still active
- `ui` read/send mode depends on desktop UI automation, so it is not reliable under lock/sleep

### Myanmar

- `discord` read/send mode က screen lock ဖြစ်နေရင်တောင် machine မအိပ်ဘဲ network ရှိနေရင် ဆက်အလုပ်လုပ်နိုင်တယ်
- `ui` mode က desktop UI automation အပေါ်မူတည်လို့ lock/sleep အောက်မှာ မတည်ငြိမ်ဘူး

## 12. Safe First Test

### English

First test:

1. start server
2. open UI
3. fill all config in UI
4. keep `dry_run = true`
5. send a prompt into the Discord prompt channel
6. confirm the app shows:
   - matched/trigger text
   - built prompt
   - CLI output
7. then disable `dry_run`

### Myanmar

ပထမဆုံး test လုပ်မယ်ဆို:

1. server run
2. UI ဖွင့်
3. config အားလုံး UI ထဲဖြည့်
4. `dry_run = true` ထား
5. Discord prompt channel ထဲ prompt တစ်ခု ပို့
6. app UI ထဲမှာ ဒီ ၃ ခုမြင်ရမယ်
   - trigger text
   - built prompt
   - CLI output
7. အားလုံးမှန်ရင် `dry_run` ပိတ်

## 13. Troubleshooting

### English

`Discord message read failed / Missing Access`

- bot is not in the server, or
- bot cannot view that channel

`Codex CLI not found`

- fix `codex_path`, or install Codex CLI

`Gemini CLI not found`

- fix `gemini_path`, or install Gemini CLI

`Gemini location unsupported / quota exceeded`

- fallback was attempted, but Gemini account/region is not usable

### Myanmar

`Discord message read failed / Missing Access`

- bot က server ထဲမဝင်သေးတာ
- ဒါမှမဟုတ် channel permission မရသေးတာ

`Codex CLI not found`

- `codex_path` မှားနေတာ
- ဒါမှမဟုတ် Codex CLI install မလုပ်ရသေးတာ

`Gemini CLI not found`

- `gemini_path` မှားနေတာ
- ဒါမှမဟုတ် Gemini CLI install မလုပ်ရသေးတာ

`Gemini location unsupported / quota exceeded`

- Codex fallback လုပ်တုန်း Gemini account/region က မသုံးလို့ရတာ

## 14. Git / Repo Note

### English

This folder may be used as a local tool folder and may not itself be a git repository.

The actual edited repository is the `project_path` you choose in the UI.

### Myanmar

ဒီ folder က local tool folder အနေနဲ့သုံးထားလို့ git repo မဟုတ်ချင်မဟုတ်နိုင်တယ်။

တကယ် AI ကဝင်ပြင်မယ့် repo က UI ထဲ `project_path` နဲ့သတ်မှတ်ထားတဲ့ repo ပဲ။

