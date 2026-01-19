# PSV Calculator - Franc Engineering

## Project Overview
Web-based PSV (Pressure Safety Valve) sizing calculator for franceng.com engineering consultancy. Serves as a lead generation tool with freemium sales pipeline.

## Business Model

### Pricing Tiers
| Tier | Price | Deliverable | Turnaround |
|------|-------|-------------|------------|
| Free | $0 | On-screen results only | Instant |
| Standard | $149 | PDF report with calculations | 24 hours |
| PE Reviewed | $499 | PE-stamped report (TX/CO licensed) | 48-72 hours |

### Sales Pipeline Flow
1. User finds calculator via Google/LinkedIn
2. Enters data, gets free results (lead captured)
3. Option to purchase PDF report (warm lead)
4. Option for PE review (qualified lead)
5. Follow-up for additional engineering work

## Technical Requirements

### Components Supported
- Hydrocarbons: Methane (C1) through Decane (C10)
- Inerts: Nitrogen (N2), Oxygen (O2)
- Acid gases: CO2, H2S
- Water (H2O)

### Thermodynamic Engine
- Equation of State: Peng-Robinson
- Flash calculations for phase equilibrium
- Properties: MW, density, Z-factor, Cp/Cv, viscosity
- Binary interaction parameters for common pairs

### PSV Sizing Scenarios (API 520/521)
1. **Fire Case - Wetted Surface**: Liquid inventory with fire exposure
2. **Fire Case - Unwetted Surface**: Vapor space fire exposure
3. **Blocked Vapor Outlet**: Upstream pressure source
4. **Blocked Liquid Outlet**: Liquid thermal expansion
5. **Control Valve Failure**: CV fails open, excess flow

### Calculations Per API Standards
- API 520 Part I: Sizing equations
- API 521: Fire heat input calculations
- API 526: Standard orifice selection (D through T)

## Architecture

```
Frontend (React/HTML)     Backend (Python/FastAPI)
┌─────────────────┐      ┌─────────────────────────┐
│ psv-calculator  │ ──── │ main.py (API)           │
│ .html           │ API  │ ├── thermo_engine.py    │
│                 │      │ └── psv_sizing.py       │
└─────────────────┘      └─────────────────────────┘
```

### Frontend Features
- Step-by-step wizard UI
- Fluid presets (Natural Gas, Propane, etc.)
- Custom composition input
- Unit conversion (°F/°C/K, psig/psia/bar/kPa)
- Visual scenario selection
- Results with orifice recommendation
- Lead capture for paid tiers

### Backend Features
- RESTful API with FastAPI
- Full Peng-Robinson EOS implementation
- Phase equilibrium (VLE flash)
- All 5 PSV scenarios
- PDF report generation (Phase 2)

## Phase 2 Roadmap
- [ ] P&ID upload capability
- [ ] PSV photo upload
- [ ] Miscellaneous document upload
- [ ] Automated report generator
- [ ] Stripe payment integration
- [ ] Dispersion modeling (API 521 / AERMOD)

## Deployment Target
- WordPress embed on franceng.com
- Backend: Railway, Render, or VPS
- Frontend: Can be embedded directly or via iframe

## Validation
- Compare results against ProMax
- Use existing relief device sizing template
- Test with known compositions and scenarios

## File Structure
```
PSV-APP/
├── frontend/
│   └── psv-calculator.html
├── backend/
│   ├── main.py
│   ├── thermo_engine.py
│   ├── psv_sizing.py
│   └── requirements.txt
├── Dockerfile
├── railway.json
├── CLAUDE_CODE_CONTEXT.md
├── DEPLOYMENT.md
└── README.md
```
