"""
MakOne SaaS Control Plane
=========================
Runs on the VPS at port 80/443 on the root domain (e.g. makone-bi.com).

Routes:
  GET  /                  Landing page + pricing
  GET  /onboarding        Company info form (after Stripe checkout)
  POST /onboarding        Save company info → trigger provisioning
  GET  /success           Post-checkout success page
  POST /stripe/webhook    Stripe events (checkout.session.completed, etc.)
  GET  /admin             Admin dashboard (all customers)
  POST /admin/suspend     Suspend a customer
  POST /admin/resume      Resume a customer
  POST /admin/deprovision Deprovision + delete a customer
  POST /admin/rebuild     Rebuild Docker image + rolling restart
"""

import hashlib
import hmac
import logging
import os
import secrets
import threading
import time

from flask import Flask, request, redirect, render_template_string, session, abort

import customer_store
import provisioner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", secrets.token_hex(32))

# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------
STRIPE_SECRET_KEY       = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET   = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_STARTER    = os.environ.get("STRIPE_PRICE_STARTER", "")
STRIPE_PRICE_PRO        = os.environ.get("STRIPE_PRICE_PRO", "")
STRIPE_PRICE_AGENCY     = os.environ.get("STRIPE_PRICE_AGENCY", "")
OPENAI_API_KEY          = os.environ.get("OPENAI_API_KEY", "")
ADMIN_PASSWORD          = os.environ.get("ADMIN_PASSWORD", "changeme")
BASE_DOMAIN             = os.environ.get("BASE_DOMAIN", "makone-bi.com")
CERTBOT_EMAIL           = os.environ.get("CERTBOT_EMAIL", "")

PLANS = {
    "starter": {"name": "Starter", "price": "$49", "price_id": STRIPE_PRICE_STARTER,
                "features": ["3 posts/week", "LinkedIn + Facebook", "AI text + images", "Email support"]},
    "pro":     {"name": "Pro",     "price": "$99", "price_id": STRIPE_PRICE_PRO,
                "features": ["Daily posting", "All platforms", "HeyGen AI avatars", "Remotion videos", "Priority support"]},
    "agency":  {"name": "Agency",  "price": "$249", "price_id": STRIPE_PRICE_AGENCY,
                "features": ["Unlimited posts", "5 client workspaces", "White-label", "Dedicated support", "Custom AI training"]},
}

# ---------------------------------------------------------------------------
# Shared HTML helpers
# ---------------------------------------------------------------------------

_BASE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0f172a; color: #e2e8f0; min-height: 100vh; }
a { color: #38bdf8; text-decoration: none; }
.container { max-width: 1100px; margin: 0 auto; padding: 0 24px; }
nav { display: flex; align-items: center; justify-content: space-between;
      padding: 20px 24px; border-bottom: 1px solid #1e293b; }
.nav-brand { font-size: 22px; font-weight: 800; color: #f8fafc; }
.nav-brand span { color: #38bdf8; }
.btn { display: inline-block; padding: 10px 24px; border-radius: 8px;
       font-weight: 600; font-size: 15px; cursor: pointer; border: none;
       transition: all .15s; text-align: center; }
.btn-primary { background: #38bdf8; color: #0f172a; }
.btn-primary:hover { background: #7dd3fc; }
.btn-danger { background: #ef4444; color: #fff; }
.btn-ghost { background: transparent; border: 1px solid #334155; color: #94a3b8; }
.btn-ghost:hover { border-color: #38bdf8; color: #38bdf8; }
.card { background: #1e293b; border-radius: 16px; padding: 32px; border: 1px solid #334155; }
.field { margin-bottom: 18px; }
.field label { display: block; font-size: 13px; font-weight: 600;
               color: #94a3b8; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .5px; }
.field input, .field select, .field textarea {
    width: 100%; padding: 10px 14px; border-radius: 8px;
    border: 1px solid #334155; background: #0f172a; color: #e2e8f0; font-size: 15px; }
.field input:focus, .field select:focus, .field textarea:focus {
    outline: none; border-color: #38bdf8; }
.alert { padding: 12px 18px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; }
.alert-error { background: rgba(239,68,68,.12); color: #fca5a5; border: 1px solid rgba(239,68,68,.3); }
.alert-success { background: rgba(34,197,94,.1); color: #86efac; border: 1px solid rgba(34,197,94,.25); }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
@media (max-width: 768px) { .grid-3 { grid-template-columns: 1fr; } }
"""

def _nav_html(active="/"):
    return f"""
<nav>
  <div class="nav-brand" style="max-width:1100px;width:100%;margin:0 auto;display:flex;align-items:center;justify-content:space-between;padding:0">
    <a href="/" style="font-size:22px;font-weight:800;color:#f8fafc;text-decoration:none">Mak<span style="color:#38bdf8">One</span></a>
    <div style="display:flex;gap:12px;align-items:center">
      <a href="/#pricing" style="color:#94a3b8;font-size:14px">Pricing</a>
      <a href="https://{BASE_DOMAIN}/login" style="color:#94a3b8;font-size:14px">Sign In</a>
      <a href="/#pricing" class="btn btn-primary" style="padding:8px 18px;font-size:14px">Get Started</a>
    </div>
  </div>
</nav>"""

# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

@app.route("/")
def landing():
    plan_cards = ""
    for key, p in PLANS.items():
        is_pro = key == "pro"
        features_html = "".join(f'<li style="padding:6px 0;border-bottom:1px solid #1e293b;font-size:14px">✓ &nbsp;{f}</li>' for f in p["features"])
        highlight = "border:2px solid #38bdf8;" if is_pro else ""
        popular = '<div style="background:#38bdf8;color:#0f172a;font-size:11px;font-weight:700;padding:4px 12px;border-radius:20px;margin-bottom:16px;display:inline-block">MOST POPULAR</div><br>' if is_pro else ""
        plan_cards += f"""
        <div class="card" style="{highlight}text-align:center;position:relative">
          {popular}
          <div style="font-size:18px;font-weight:700;margin-bottom:8px">{p["name"]}</div>
          <div style="font-size:42px;font-weight:800;color:#38bdf8;margin-bottom:4px">{p["price"]}</div>
          <div style="color:#64748b;font-size:13px;margin-bottom:24px">/month</div>
          <ul style="list-style:none;text-align:left;margin-bottom:28px">{features_html}</ul>
          <a href="/checkout?plan={key}" class="btn btn-primary" style="width:100%;display:block">
            Start {p["name"]} →
          </a>
        </div>"""

    return render_template_string(f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MakOne — AI Social Media on Autopilot</title>
<style>{_BASE_CSS}
.hero {{ padding: 100px 24px 80px; text-align: center; }}
.hero h1 {{ font-size: clamp(36px,6vw,72px); font-weight: 900; line-height: 1.1;
            margin-bottom: 24px; }}
.hero h1 span {{ color: #38bdf8; }}
.hero p {{ font-size: 20px; color: #94a3b8; max-width: 600px; margin: 0 auto 40px; }}
.features {{ padding: 80px 24px; background: #0a1628; }}
.feature-grid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(260px,1fr));
                 gap: 24px; max-width: 1100px; margin: 0 auto; }}
.feature-card {{ background: #1e293b; border-radius: 12px; padding: 28px;
                 border: 1px solid #334155; }}
.pricing {{ padding: 80px 24px; }}
.pricing h2 {{ text-align:center; font-size: 36px; margin-bottom: 12px; }}
.pricing p {{ text-align:center; color: #64748b; margin-bottom: 48px; }}
footer {{ padding: 40px 24px; text-align:center; color: #475569; font-size:13px;
          border-top: 1px solid #1e293b; }}
</style>
</head><body>
{_nav_html()}
<div class="hero">
  <h1>Your social media,<br><span>run by AI.</span></h1>
  <p>MakOne generates, approves, and posts AI content to LinkedIn, Facebook, Instagram &amp; YouTube — fully automated.</p>
  <a href="#pricing" class="btn btn-primary" style="font-size:18px;padding:16px 40px">Start Free Trial →</a>
  &nbsp;&nbsp;
  <a href="#features" class="btn btn-ghost" style="font-size:18px;padding:16px 40px">See how it works</a>
</div>

<div class="features" id="features">
  <div style="text-align:center;margin-bottom:48px">
    <h2 style="font-size:36px;margin-bottom:12px">Everything you need to dominate social</h2>
    <p style="color:#64748b">From content generation to publishing — fully hands-off.</p>
  </div>
  <div class="feature-grid">
    <div class="feature-card">
      <div style="font-size:32px;margin-bottom:12px">✍️</div>
      <h3 style="margin-bottom:8px">AI Content Generation</h3>
      <p style="color:#64748b;font-size:14px">GPT-4o writes engaging posts tailored to your brand voice, industry, and audience.</p>
    </div>
    <div class="feature-card">
      <div style="font-size:32px;margin-bottom:12px">🎬</div>
      <h3 style="margin-bottom:8px">AI Video &amp; Avatars</h3>
      <p style="color:#64748b;font-size:14px">HeyGen AI avatars deliver your scripts. Remotion renders branded video compositions automatically.</p>
    </div>
    <div class="feature-card">
      <div style="font-size:32px;margin-bottom:12px">🖼️</div>
      <h3 style="margin-bottom:8px">AI Image Generation</h3>
      <p style="color:#64748b;font-size:14px">Google Imagen 3 and VEO 3 create stunning visuals and video clips matched to your post.</p>
    </div>
    <div class="feature-card">
      <div style="font-size:32px;margin-bottom:12px">📅</div>
      <h3 style="margin-bottom:8px">Smart Scheduling</h3>
      <p style="color:#64748b;font-size:14px">Set your posting days and times. The scheduler handles the rest — every week, on autopilot.</p>
    </div>
    <div class="feature-card">
      <div style="font-size:32px;margin-bottom:12px">✅</div>
      <h3 style="margin-bottom:8px">Approval Workflow</h3>
      <p style="color:#64748b;font-size:14px">Review and approve posts before they go live. Or go fully hands-off — your choice.</p>
    </div>
    <div class="feature-card">
      <div style="font-size:32px;margin-bottom:12px">📊</div>
      <h3 style="margin-bottom:8px">Multi-Platform Publishing</h3>
      <p style="color:#64748b;font-size:14px">Publish simultaneously to LinkedIn, Facebook, Instagram, and YouTube from one dashboard.</p>
    </div>
  </div>
</div>

<div class="pricing" id="pricing">
  <h2>Simple, transparent pricing</h2>
  <p>Start free for 14 days. No credit card required. Cancel anytime.</p>
  <div class="grid-3">{plan_cards}</div>
  <p style="text-align:center;margin-top:24px;color:#475569;font-size:13px">
    All plans include a 14-day free trial. Questions? <a href="mailto:hello@{BASE_DOMAIN}">hello@{BASE_DOMAIN}</a>
  </p>
</div>

<footer>
  &copy; 2025 MakOne AI &nbsp;·&nbsp; <a href="/privacy">Privacy</a> &nbsp;·&nbsp; <a href="/terms">Terms</a>
</footer>
</body></html>""")


# ---------------------------------------------------------------------------
# Stripe Checkout redirect
# ---------------------------------------------------------------------------

@app.route("/checkout")
def checkout():
    plan = request.args.get("plan", "pro")
    if plan not in PLANS:
        plan = "pro"

    if not STRIPE_SECRET_KEY:
        # Dev mode: skip Stripe, go straight to onboarding
        return redirect(f"/onboarding?plan={plan}&session_id=dev_{secrets.token_urlsafe(8)}")

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        price_id = PLANS[plan]["price_id"]
        if not price_id:
            return f"Plan '{plan}' price ID not configured in STRIPE_PRICE_{plan.upper()}", 500

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            subscription_data={"trial_period_days": 14},
            success_url=f"https://{BASE_DOMAIN}/onboarding?plan={plan}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"https://{BASE_DOMAIN}/#pricing",
            metadata={"plan": plan},
        )
        return redirect(checkout_session.url)
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        return render_template_string(f"""<!DOCTYPE html><html><head><title>Error</title>
<style>{_BASE_CSS}</style></head><body>{_nav_html()}
<div class="container" style="padding:80px 24px">
  <div class="alert alert-error">Payment setup error: {e}<br>
    <a href="/#pricing">← Go back</a></div>
</div></body></html>""")


# ---------------------------------------------------------------------------
# Onboarding form
# ---------------------------------------------------------------------------

@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    plan = request.args.get("plan", "pro")
    session_id = request.args.get("session_id", "")
    error = ""

    if request.method == "POST":
        plan        = request.form.get("plan", "pro")
        session_id  = request.form.get("session_id", "")
        email       = request.form.get("email", "").strip().lower()
        company     = request.form.get("company", "").strip()
        website     = request.form.get("website", "").strip()
        industry    = request.form.get("industry", "").strip()
        slug        = request.form.get("slug", "").strip().lower()
        first_name  = request.form.get("first_name", "").strip()
        platforms   = request.form.getlist("platforms")

        # Validation
        if not email or not company or not first_name:
            error = "Please fill in all required fields."
        elif slug and customer_store.slug_taken(slug):
            error = f"The workspace name '{slug}' is already taken. Choose another."
        else:
            # Create customer record
            customer = customer_store.create(
                email=email,
                company=company,
                plan=plan,
                slug=slug,
                stripe_session_id=session_id,
            )
            customer_store.update(customer["id"],
                website=website,
                industry=industry,
                first_name=first_name,
                platforms=",".join(platforms),
            )

            # Generate a random initial admin password
            admin_password = secrets.token_urlsafe(12)
            customer_store.update(customer["id"], initial_password=admin_password)

            # Provision in background (takes ~30s)
            def _do_provision():
                ok = provisioner.provision(customer, admin_password, OPENAI_API_KEY)
                if ok:
                    customer_store.set_status(customer["id"], "active")
                    logger.info(f"Customer '{customer['slug']}' provisioned successfully")
                else:
                    customer_store.set_status(customer["id"], "error")
                    logger.error(f"Provisioning failed for '{customer['slug']}'")

            threading.Thread(target=_do_provision, daemon=True).start()

            return redirect(f"/success?slug={customer['slug']}&email={email}&password={admin_password}")

    plan_name = PLANS.get(plan, PLANS["pro"])["name"]

    return render_template_string(f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Set Up Your MakOne Workspace</title>
<style>{_BASE_CSS}
.onboarding {{ max-width: 640px; margin: 60px auto; padding: 0 24px; }}
.step-badge {{ background: rgba(56,189,248,.12); color: #38bdf8;
               font-size: 12px; font-weight: 700; padding: 4px 12px;
               border-radius: 20px; margin-bottom: 16px; display: inline-block; }}
.cb-group {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; }}
.cb-label {{ display: flex; align-items: center; gap: 8px; cursor: pointer;
             background: #0f172a; border: 1px solid #334155; border-radius: 8px;
             padding: 8px 14px; font-size: 14px; transition: all .15s; }}
.cb-label:hover {{ border-color: #38bdf8; }}
.cb-label input {{ width: auto; accent-color: #38bdf8; }}
.slug-preview {{ font-size: 13px; color: #38bdf8; margin-top: 6px; }}
</style>
</head><body>
{_nav_html()}
<div class="onboarding">
  <div class="step-badge">✓ {plan_name} Plan Selected</div>
  <h1 style="font-size:32px;font-weight:800;margin-bottom:8px">Set up your workspace</h1>
  <p style="color:#64748b;margin-bottom:32px">
    Tell us about your business so we can personalise your AI content from day one.
  </p>

  {'<div class="alert alert-error">' + error + '</div>' if error else ''}

  <form method="POST" action="/onboarding">
    <input type="hidden" name="plan" value="{plan}">
    <input type="hidden" name="session_id" value="{session_id}">

    <div class="card">
      <div class="field">
        <label>Your Name *</label>
        <input type="text" name="first_name" placeholder="Jane Smith" required>
      </div>
      <div class="field">
        <label>Business Email *</label>
        <input type="email" name="email" placeholder="jane@company.com" required>
      </div>
      <div class="field">
        <label>Company / Brand Name *</label>
        <input type="text" name="company" id="company-input" placeholder="Acme Corp" required
               oninput="updateSlug(this.value)">
      </div>
      <div class="field">
        <label>Website</label>
        <input type="url" name="website" placeholder="https://yourcompany.com">
      </div>
      <div class="field">
        <label>Industry</label>
        <select name="industry">
          <option value="">Select your industry</option>
          <option>AI &amp; Technology</option>
          <option>Marketing &amp; Advertising</option>
          <option>E-commerce &amp; Retail</option>
          <option>Professional Services</option>
          <option>Real Estate</option>
          <option>Healthcare &amp; Wellness</option>
          <option>Finance &amp; Accounting</option>
          <option>Education &amp; Coaching</option>
          <option>Construction &amp; Trades</option>
          <option>Hospitality &amp; Food</option>
          <option>Other</option>
        </select>
      </div>
    </div>

    <div class="card" style="margin-top:20px">
      <div class="field">
        <label>Workspace Name (your URL) *</label>
        <input type="text" name="slug" id="slug-input"
               pattern="[a-z0-9\-]{{2,30}}" placeholder="acmecorp"
               title="Lowercase letters, numbers, hyphens only" required>
        <div class="slug-preview" id="slug-preview">
          Your dashboard: <strong id="slug-domain">acmecorp.{BASE_DOMAIN}</strong>
        </div>
      </div>

      <div class="field">
        <label>Platforms you want to post to</label>
        <div class="cb-group">
          <label class="cb-label"><input type="checkbox" name="platforms" value="linkedin" checked> LinkedIn</label>
          <label class="cb-label"><input type="checkbox" name="platforms" value="facebook"> Facebook</label>
          <label class="cb-label"><input type="checkbox" name="platforms" value="instagram"> Instagram</label>
          <label class="cb-label"><input type="checkbox" name="platforms" value="youtube"> YouTube</label>
        </div>
      </div>
    </div>

    <button type="submit" class="btn btn-primary"
            style="width:100%;margin-top:24px;padding:16px;font-size:16px">
      Create My Workspace →
    </button>
    <p style="text-align:center;color:#475569;font-size:12px;margin-top:12px">
      By continuing you agree to our <a href="/terms">Terms of Service</a> and <a href="/privacy">Privacy Policy</a>.
    </p>
  </form>
</div>
<script>
function slugify(str) {{
  return str.toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 30);
}}
function updateSlug(val) {{
  const slug = slugify(val);
  document.getElementById('slug-input').value = slug;
  document.getElementById('slug-domain').textContent = slug + '.{BASE_DOMAIN}';
}}
document.getElementById('slug-input').addEventListener('input', function() {{
  document.getElementById('slug-domain').textContent = this.value + '.{BASE_DOMAIN}';
}});
</script>
</body></html>""")


# ---------------------------------------------------------------------------
# Success page
# ---------------------------------------------------------------------------

@app.route("/success")
def success():
    slug     = request.args.get("slug", "")
    email    = request.args.get("email", "")
    password = request.args.get("password", "")
    domain   = f"{slug}.{BASE_DOMAIN}"

    return render_template_string(f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Welcome to MakOne!</title>
<style>{_BASE_CSS}</style>
</head><body>
{_nav_html()}
<div style="max-width:600px;margin:80px auto;padding:0 24px;text-align:center">
  <div style="font-size:64px;margin-bottom:24px">🎉</div>
  <h1 style="font-size:36px;margin-bottom:16px">Your workspace is being created!</h1>
  <p style="color:#94a3b8;margin-bottom:40px;font-size:18px">
    It takes about 60 seconds. Here are your login details — save them now.
  </p>

  <div class="card" style="text-align:left;margin-bottom:32px">
    <div style="margin-bottom:16px">
      <div style="font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;margin-bottom:4px">Your Dashboard URL</div>
      <a href="https://{domain}" target="_blank" style="font-size:18px;font-weight:700;color:#38bdf8">
        https://{domain}
      </a>
    </div>
    <div style="margin-bottom:16px">
      <div style="font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;margin-bottom:4px">Username</div>
      <div style="font-size:16px;font-family:monospace">admin</div>
    </div>
    <div>
      <div style="font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;margin-bottom:4px">Temporary Password</div>
      <div style="font-size:16px;font-family:monospace;background:#0f172a;padding:8px 12px;border-radius:6px;color:#38bdf8">{password}</div>
    </div>
  </div>

  <div class="card" style="text-align:left;margin-bottom:32px">
    <div style="font-weight:700;margin-bottom:12px">Next steps after logging in:</div>
    <ol style="padding-left:20px;color:#94a3b8;font-size:14px;line-height:2">
      <li>Change your password in <strong>Setup → Login &amp; Access</strong></li>
      <li>Add your company details in <strong>Content Influence</strong></li>
      <li>Connect your social platforms in <strong>Setup</strong></li>
      <li>Generate your first post in <strong>Create</strong></li>
    </ol>
  </div>

  <a href="https://{domain}" class="btn btn-primary" style="font-size:16px;padding:14px 40px">
    Go to My Dashboard →
  </a>
  <p style="margin-top:20px;color:#475569;font-size:13px">
    Login details also sent to {email}
  </p>
</div>
</body></html>""")


# ---------------------------------------------------------------------------
# Stripe webhook
# ---------------------------------------------------------------------------

@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload   = request.get_data()
    sig       = request.headers.get("Stripe-Signature", "")

    if STRIPE_WEBHOOK_SECRET:
        try:
            import stripe
            stripe.api_key = STRIPE_SECRET_KEY
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            logger.error(f"Stripe webhook error: {e}")
            abort(400)
    else:
        import json
        event = json.loads(payload)

    event_type = event.get("type", "")
    logger.info(f"Stripe webhook: {event_type}")

    if event_type == "checkout.session.completed":
        s = event["data"]["object"]
        session_id = s.get("id", "")
        stripe_customer_id = s.get("customer", "")
        stripe_sub_id = s.get("subscription", "")
        customer = customer_store.get_by_stripe_session(session_id)
        if customer:
            customer_store.update(customer["id"],
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_sub_id,
            )
            logger.info(f"Stripe checkout complete for '{customer['slug']}'")

    elif event_type == "customer.subscription.deleted":
        sub = event["data"]["object"]
        sub_id = sub.get("id", "")
        customers = customer_store.get_all()
        for c in customers:
            if c.get("stripe_subscription_id") == sub_id:
                provisioner.suspend(c["slug"])
                customer_store.set_status(c["id"], "suspended")
                logger.info(f"Subscription cancelled for '{c['slug']}' — suspended")
                break

    elif event_type == "invoice.payment_failed":
        inv = event["data"]["object"]
        stripe_cust = inv.get("customer", "")
        customers = customer_store.get_all()
        for c in customers:
            if c.get("stripe_customer_id") == stripe_cust:
                logger.warning(f"Payment failed for '{c['slug']}'")
                break

    return {"status": "ok"}, 200


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

def _require_admin():
    if not session.get("admin"):
        abort(redirect("/admin/login"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    if request.method == "POST":
        pw = request.form.get("password", "")
        if hmac.compare_digest(
            hashlib.sha256(pw.encode()).hexdigest(),
            hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(),
        ):
            session["admin"] = True
            return redirect("/admin")
        error = "Wrong password."

    return render_template_string(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Admin Login</title>
<style>{_BASE_CSS}</style></head><body>
<div style="max-width:380px;margin:120px auto;padding:0 24px">
  <h1 style="margin-bottom:24px">Admin Login</h1>
  {'<div class="alert alert-error">' + error + '</div>' if error else ''}
  <form method="POST" class="card">
    <div class="field"><label>Password</label>
      <input type="password" name="password" autofocus></div>
    <button class="btn btn-primary" style="width:100%" type="submit">Sign In</button>
  </form>
</div></body></html>""")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login")


@app.route("/admin")
def admin_dashboard():
    if not session.get("admin"):
        return redirect("/admin/login")

    customers = customer_store.get_all()

    rows = ""
    for c in customers:
        slug = c["slug"]
        status = c.get("status", "")
        status_color = {
            "active": "#22c55e", "provisioning": "#f59e0b",
            "suspended": "#ef4444", "error": "#ef4444",
        }.get(status, "#94a3b8")

        rows += f"""
        <tr style="border-bottom:1px solid #1e293b">
          <td style="padding:12px 16px"><strong>{slug}</strong><br>
              <span style="color:#64748b;font-size:12px">{c.get("company","")}</span></td>
          <td style="padding:12px 16px;color:#94a3b8;font-size:13px">{c.get("email","")}</td>
          <td style="padding:12px 16px"><span style="text-transform:capitalize">{c.get("plan","")}</span></td>
          <td style="padding:12px 16px;color:{status_color};font-weight:600;text-transform:capitalize">{status}</td>
          <td style="padding:12px 16px">:{c.get("port","")}</td>
          <td style="padding:12px 16px;font-size:12px;color:#64748b">{c.get("created_at","")[:10]}</td>
          <td style="padding:12px 16px">
            <a href="https://{slug}.{BASE_DOMAIN}" target="_blank" style="font-size:12px;margin-right:8px">Open</a>
            {"<form style='display:inline' method='POST' action='/admin/resume'><input type='hidden' name='id' value='" + c['id'] + "'><button class='btn btn-ghost' style='font-size:11px;padding:4px 8px'>Resume</button></form> " if status == "suspended" else ""}
            {"<form style='display:inline' method='POST' action='/admin/suspend'><input type='hidden' name='id' value='" + c['id'] + "'><button class='btn btn-ghost' style='font-size:11px;padding:4px 8px'>Suspend</button></form> " if status == "active" else ""}
            <form style='display:inline' method='POST' action='/admin/deprovision'
                  onsubmit="return confirm('Delete {slug}? This cannot be undone.')">
              <input type='hidden' name='id' value='{c["id"]}'>
              <button class='btn btn-danger' style='font-size:11px;padding:4px 8px'>Delete</button>
            </form>
          </td>
        </tr>"""

    total = len(customers)
    active = sum(1 for c in customers if c.get("status") == "active")
    revenue = active * 49  # rough estimate

    return render_template_string(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>MakOne Admin</title>
<style>{_BASE_CSS}
table {{ width: 100%; border-collapse: collapse; }}
th {{ text-align: left; padding: 12px 16px; background: #1e293b;
     font-size: 12px; text-transform: uppercase; color: #64748b; }}
</style></head><body>
<nav style="background:#1e293b;padding:16px 24px;display:flex;align-items:center;justify-content:space-between">
  <strong style="color:#38bdf8">MakOne Admin</strong>
  <div style="display:flex;gap:16px;align-items:center">
    <form method="POST" action="/admin/rebuild" style="display:inline"
          onsubmit="return confirm('Rebuild Docker image and restart all containers?')">
      <button class="btn btn-ghost" style="font-size:13px" type="submit">🔄 Deploy Update</button>
    </form>
    <a href="/admin/logout" style="color:#64748b;font-size:13px">Sign out</a>
  </div>
</nav>
<div style="max-width:1200px;margin:0 auto;padding:32px 24px">
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:32px">
    <div class="card" style="text-align:center">
      <div style="font-size:36px;font-weight:800;color:#38bdf8">{total}</div>
      <div style="color:#64748b;font-size:13px">Total Customers</div>
    </div>
    <div class="card" style="text-align:center">
      <div style="font-size:36px;font-weight:800;color:#22c55e">{active}</div>
      <div style="color:#64748b;font-size:13px">Active</div>
    </div>
    <div class="card" style="text-align:center">
      <div style="font-size:36px;font-weight:800;color:#a78bfa">${revenue}+</div>
      <div style="color:#64748b;font-size:13px">Est. MRR</div>
    </div>
  </div>

  <div class="card" style="padding:0;overflow:hidden">
    <table>
      <thead>
        <tr>
          <th>Customer</th><th>Email</th><th>Plan</th><th>Status</th>
          <th>Port</th><th>Created</th><th>Actions</th>
        </tr>
      </thead>
      <tbody>{rows if rows else '<tr><td colspan="7" style="padding:32px;text-align:center;color:#475569">No customers yet</td></tr>'}</tbody>
    </table>
  </div>
</div>
</body></html>""")


@app.route("/admin/suspend", methods=["POST"])
def admin_suspend():
    if not session.get("admin"):
        abort(403)
    cid = request.form.get("id", "")
    c = customer_store.get_by_id(cid)
    if c:
        provisioner.suspend(c["slug"])
        customer_store.set_status(cid, "suspended")
    return redirect("/admin")


@app.route("/admin/resume", methods=["POST"])
def admin_resume():
    if not session.get("admin"):
        abort(403)
    cid = request.form.get("id", "")
    c = customer_store.get_by_id(cid)
    if c:
        provisioner.resume(c["slug"])
        customer_store.set_status(cid, "active")
    return redirect("/admin")


@app.route("/admin/deprovision", methods=["POST"])
def admin_deprovision():
    if not session.get("admin"):
        abort(403)
    cid = request.form.get("id", "")
    c = customer_store.get_by_id(cid)
    if c:
        provisioner.deprovision(c["slug"])
        customer_store.delete(cid)
    return redirect("/admin")


@app.route("/admin/rebuild", methods=["POST"])
def admin_rebuild():
    if not session.get("admin"):
        abort(403)

    def _do_rebuild():
        app_dir = os.environ.get("APP_DIR", "/opt/makone/app")
        if provisioner.rebuild_image(app_dir):
            results = provisioner.rolling_restart_all()
            logger.info(f"Rolling restart results: {results}")

    threading.Thread(target=_do_rebuild, daemon=True).start()
    return render_template_string(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="10;url=/admin">
<title>Rebuilding...</title>
<style>{_BASE_CSS}</style></head><body>
<div style="max-width:600px;margin:120px auto;text-align:center;padding:0 24px">
  <div style="font-size:48px;margin-bottom:16px">🔄</div>
  <h2 style="margin-bottom:8px">Rebuilding Docker image...</h2>
  <p style="color:#64748b">This takes 2–5 minutes. Redirecting to admin in 10s.</p>
  <a href="/admin" style="display:block;margin-top:24px">← Back to Admin</a>
</div></body></html>""")


# ---------------------------------------------------------------------------
# Privacy / Terms stubs
# ---------------------------------------------------------------------------

@app.route("/privacy")
def privacy():
    return render_template_string(f"""<!DOCTYPE html><html><head><title>Privacy</title>
<style>{_BASE_CSS}</style></head><body>{_nav_html()}
<div class="container" style="padding:80px 24px;max-width:800px">
<h1 style="margin-bottom:24px">Privacy Policy</h1>
<p style="color:#94a3b8">We collect only what's needed to provide the service.
Your data is never sold. Contact hello@{BASE_DOMAIN} with questions.</p>
</div></body></html>""")


@app.route("/terms")
def terms():
    return render_template_string(f"""<!DOCTYPE html><html><head><title>Terms</title>
<style>{_BASE_CSS}</style></head><body>{_nav_html()}
<div class="container" style="padding:80px 24px;max-width:800px">
<h1 style="margin-bottom:24px">Terms of Service</h1>
<p style="color:#94a3b8">By using MakOne you agree to use the service lawfully.
Contact hello@{BASE_DOMAIN} for the full agreement.</p>
</div></body></html>""")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("SAAS_PORT", 80))
    app.run(host="0.0.0.0", port=port, debug=False)
