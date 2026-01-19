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
