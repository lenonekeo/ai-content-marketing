# AI Content Marketing App

Fully standalone Python app that automatically generates AI content
and posts to **LinkedIn** and **Facebook** with optional **HeyGen avatar videos**
and **Google VEO 3 AI videos**. No n8n or third-party automation tools required.

## Features

- AI text generation via OpenAI (gpt-4o-mini)
- HeyGen avatar video creation (your personal clone speaks the post)
- Google VEO 3 video generation (AI cinematic visuals)
- Smart routing: HeyGen for personal themes, VEO 3 for visual themes
- Posts text + video to LinkedIn and Facebook
- 7 rotating content themes tailored for AI automation business
- Graceful fallback: if video fails, posts text-only
- Structured JSON logging to `logs/posts.jsonl`
- Email error notifications via SMTP
- Runs on VPS via systemd service

## Project Structure

```
ai-content-marketing/
├── main.py               # Entry point + CLI
├── scheduler.py          # APScheduler cron scheduling
├── config.py             # Environment variable loading
├── requirements.txt
├── .env.example          # Copy to .env and fill in
├── src/
│   ├── themes.py         # 7 content themes with prompts
│   ├── content_generator.py  # OpenAI text + script generation
│   ├── heygen_client.py  # HeyGen avatar video API
│   ├── veo3_client.py    # Google VEO 3 video API
│   ├── video_selector.py # Routes to HeyGen or VEO 3 by theme
│   ├── formatter.py      # Platform-specific formatting + hashtags
│   ├── linkedin_poster.py
│   ├── facebook_poster.py
│   ├── notifier.py       # SMTP error emails
│   └── logger.py         # JSON line logging
├── logs/                 # posts.jsonl, app.log
├── downloads/            # Temp video files (auto-cleaned)
└── deploy/
    └── content-marketing.service  # systemd unit file
```

## Video Strategy

| Theme | Video | Why |
|-------|-------|-----|
| Use Case | HeyGen avatar | Personal delivery |
| Tips | VEO 3 | Workflow visuals |
| Success Story | HeyGen avatar | Personal testimonial |
| AI Trends | VEO 3 | Futuristic visuals |
| Problem/Solution | VEO 3 | Before/after contrast |
| Educational | HeyGen avatar | Explaining on camera |
| Service Highlight | HeyGen avatar | Direct pitch |

## Installation on VPS

### 1. Upload project
```bash
scp -r ai-content-marketing/ user@your-vps:/home/ubuntu/
```

### 2. Install dependencies
```bash
cd /home/ubuntu/ai-content-marketing
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure credentials
```bash
cp .env.example .env
nano .env   # Fill in all your API keys
```

### 4. Test without video first
```bash
python main.py run --text-only
```

### 5. Test with full video pipeline
```bash
python main.py run
```

### 6. Install as systemd service
```bash
# Edit deploy/content-marketing.service if your username is not 'ubuntu'
sudo cp deploy/content-marketing.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable content-marketing
sudo systemctl start content-marketing
```

### 7. Check status
```bash
sudo systemctl status content-marketing
journalctl -u content-marketing -f    # Live logs
python main.py status                  # Last 5 executions
```

## CLI Commands

```bash
python main.py run              # Run once (with video)
python main.py run --text-only  # Run once (text only, for testing)
python main.py start            # Start scheduler (production)
python main.py status           # Show last 5 execution results
```

## API Credentials Needed

| Service | Where to Get |
|---------|-------------|
| OpenAI | platform.openai.com/api-keys |
| HeyGen | app.heygen.com → Settings → API |
| HeyGen Avatar ID | app.heygen.com → Avatars → Your Clone |
| HeyGen Voice ID | app.heygen.com → Voices → Your Voice |
| Google VEO 3 | aistudio.google.com → API Keys |
| LinkedIn Access Token | LinkedIn Developer Portal → OAuth2 |
| LinkedIn Person/Org URN | LinkedIn API → /v2/userinfo |
| Facebook Access Token | developers.facebook.com → Graph API Explorer |
| Facebook Page ID | Your FB Page → About |

## Schedule

Default: **Monday, Wednesday, Friday at 09:00 UTC**

Change in `.env`:
```
POST_HOUR=9
POST_DAYS=mon,wed,fri
```

## Cost Estimate (Monthly)

| Service | Cost |
|---------|------|
| OpenAI | ~$1-3 |
| HeyGen | ~$30-50 (Creator plan) |
| Google VEO 3 | ~$5-15 |
| VPS | ~$5-10 |
| LinkedIn/Facebook | Free |
| **Total** | **~$41-78/month** |

## Troubleshooting

**No posts appearing:** Check `python main.py status` and `logs/app.log`

**HeyGen video failing:** Verify `HEYGEN_AVATAR_ID` and `HEYGEN_VOICE_ID` in `.env`

**VEO 3 failing:** Confirm `GOOGLE_API_KEY` has VEO 3 access (waitlist at time of writing)

**LinkedIn 401:** Token expired, regenerate OAuth2 token (3-month lifetime)

**Facebook 401:** Page access token expired, generate new long-lived token
