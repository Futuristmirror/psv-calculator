# PSV Calculator - Franc Engineering

Web-based Pressure Safety Valve sizing calculator per API 520/521.

## Features

- **5 Relief Scenarios**: Fire (wetted/unwetted), blocked outlet (vapor/liquid), CV failure
- **Full Composition Support**: C1-C10, N2, O2, CO2, H2S, H2O
- **Peng-Robinson EOS**: Accurate thermodynamic calculations
- **API 526 Orifice Selection**: Automatic standard orifice sizing
- **WordPress Ready**: Embeddable frontend with freemium pricing model

## Quick Start

### Frontend Only
```bash
# Open directly in browser
open frontend/psv-calculator.html
```

### Full Stack
```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Run API server
python main.py

# API docs at http://localhost:8000/docs
```

### Docker
```bash
docker build -t psv-calculator .
docker run -p 8000:8000 psv-calculator
```

## Project Structure

```
PSV-APP/
├── frontend/
│   └── psv-calculator.html    # Standalone React app
├── backend/
│   ├── main.py                # FastAPI server
│   ├── thermo_engine.py       # Peng-Robinson EOS
│   ├── psv_sizing.py          # API 520/521 calculations
│   └── requirements.txt
├── Dockerfile
├── railway.json
├── DEPLOYMENT.md
├── CLAUDE_CODE_CONTEXT.md
└── README.md
```

## Pricing Model

| Tier | Price | Deliverable |
|------|-------|-------------|
| Free | $0 | On-screen results |
| Standard | $149 | PDF report |
| PE Reviewed | $499 | PE-stamped report |

## Phase 2 Roadmap

- [ ] P&ID upload capability
- [ ] PSV photo upload
- [ ] Automated report generator
- [ ] Stripe payment integration
- [ ] Dispersion modeling (API 521 / AERMOD)

## License

Proprietary - Franc Engineering

## Contact

- Website: [franceng.com](https://franceng.com)
- Email: info@franceng.com
