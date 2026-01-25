# PSV Calculator Deployment Guide

## Quick Start Options

### Option 1: Frontend Only (Simplest)

The frontend (`frontend/psv-calculator.html`) works standalone with built-in calculations.

1. **Local Testing**: Open the HTML file directly in a browser
2. **WordPress**: Copy the entire HTML content into a Custom HTML block
3. **Netlify/Vercel**: Drag and drop the frontend folder

### Option 2: Full Stack with Backend API

Deploy the Python backend for more accurate calculations.

---

## Backend Deployment Options

### Railway (Recommended - Free Tier Available)

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app)
3. New Project → Deploy from GitHub repo
4. Railway auto-detects the Dockerfile
5. Copy your deployment URL (e.g., `https://psv-calculator.up.railway.app`)
6. Update `API_BASE` in the frontend HTML

### Render

1. Create account at [render.com](https://render.com)
2. New → Web Service → Connect GitHub repo
3. Settings:
   - Runtime: Docker
   - Instance Type: Free (or Starter for production)
4. Deploy

### Docker (Self-Hosted)

```bash
# Build
docker build -t psv-calculator .

# Run
docker run -p 8000:8000 psv-calculator

# Test
curl http://localhost:8000/health
```

---

## WordPress Integration

### Method 1: Embed via iframe

After deploying the frontend to Netlify/Vercel:

```html
<iframe
    src="https://your-psv-calculator.netlify.app"
    width="100%"
    height="800"
    frameborder="0"
    style="border: none; border-radius: 12px;">
</iframe>
```

### Method 2: Direct HTML (No Backend)

1. Edit your WordPress page
2. Add a "Custom HTML" block
3. Copy entire contents of `frontend/psv-calculator.html`
4. Publish

### Method 3: Full Integration (Advanced)

1. Deploy backend to Railway/Render
2. Update `API_BASE` in the HTML to your backend URL
3. Host frontend on same domain or configure CORS

---

## Connecting Frontend to Backend

In `frontend/psv-calculator.html`, find this line near the top:

```javascript
const API_BASE = ''; // Empty for local calculations
```

Change to your deployed backend URL:

```javascript
const API_BASE = 'https://your-psv-calculator.up.railway.app';
```

---

## Environment Variables

The backend doesn't require environment variables for basic operation.

For production, consider adding:
- `CORS_ORIGINS`: Allowed origins (default: *)
- `LOG_LEVEL`: Logging verbosity

---

## Stripe Payment Integration

To enable payments for report generation:

### 1. Create Stripe Account

1. Sign up at [stripe.com](https://stripe.com)
2. Go to Developers → API Keys
3. Copy your **Secret key** (starts with `sk_test_` or `sk_live_`)

### 2. Set Environment Variables

Add these to your Railway/Render deployment:

```bash
STRIPE_SECRET_KEY=sk_test_your_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret
FRONTEND_URL=https://your-domain.com/psv-calculator.html
```

### 3. Configure Stripe Webhook

1. In Stripe Dashboard, go to Developers → Webhooks
2. Add endpoint: `https://your-api.railway.app/webhook/stripe`
3. Select events: `checkout.session.completed`, `checkout.session.expired`
4. Copy the signing secret to `STRIPE_WEBHOOK_SECRET`

### 4. Update Frontend

Set `API_BASE` in your frontend to point to your backend:

```javascript
const API_BASE = 'https://your-api.railway.app';
```

### 5. Test the Flow

1. First report is FREE (tracked in browser localStorage)
2. After first report, users see "Pay $99 & Generate" button
3. Clicking redirects to Stripe Checkout
4. After successful payment, user is redirected back and can download PDF

### Pricing Configuration

Edit pricing in `backend/main.py`:

```python
PRODUCTS = {
    "standard_report": {
        "name": "PSV Calculator - Standard Report",
        "price_cents": 9900,  # $99.00
    },
    "pe_reviewed": {
        "name": "PSV Calculator - PE-Reviewed Report",
        "price_cents": 49900,  # $499.00
    }
}
```

### Local Testing with Stripe CLI

```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Login
stripe login

# Forward webhooks to local server
stripe listen --forward-to localhost:8000/webhook/stripe

# Copy the webhook signing secret it prints
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API info |
| `/health` | GET | Health check |
| `/components` | GET | List available components |
| `/presets` | GET | List fluid presets |
| `/properties` | POST | Calculate thermo properties |
| `/size-psv` | POST | Calculate PSV sizing |
| `/orifices` | GET | List API 526 orifices |
| `/docs` | GET | Swagger documentation |
| `/payment-status` | GET | Check if Stripe is configured |
| `/create-checkout-session` | POST | Create Stripe checkout session |
| `/verify-payment/{session_id}` | GET | Verify payment status |
| `/webhook/stripe` | POST | Stripe webhook handler |

---

## Testing the API

```bash
# Health check
curl https://your-api.railway.app/health

# Get components
curl https://your-api.railway.app/components

# Calculate properties
curl -X POST https://your-api.railway.app/properties \
  -H "Content-Type: application/json" \
  -d '{
    "components": [
      {"name": "methane", "mole_fraction": 0.85},
      {"name": "ethane", "mole_fraction": 0.10},
      {"name": "propane", "mole_fraction": 0.05}
    ],
    "temperature_F": 100,
    "pressure_psig": 150
  }'
```

---

## Troubleshooting

### CORS Errors
If you see CORS errors in browser console:
- Ensure your domain is in the allowed origins
- Or use a proxy

### Calculations Differ from ProMax
The built-in PR-EOS is simplified. For higher accuracy:
- Deploy the Python backend
- Use the full `thermo` library (add to requirements.txt)

### Performance Issues
- Frontend calculations are instant
- Backend cold starts may take 10-30s on free tiers
- Consider upgrading to paid tier for production

---

## Support

Questions? Contact Franc Engineering:
- Website: [franceng.com](https://franceng.com)
- Email: info@franceng.com
