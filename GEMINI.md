# AI Bidding Intelligence - Project Guidelines

## Project Overview
This project is an AI-powered bidding assistant that helps companies analyze Nara Market (G2B) bidding notices.

## Architecture
- **Frontend**: Streamlit
- **AI Engine**: Google Gemini 2.0/2.5 Flash
- **Database**: Supabase (PostgreSQL) with local JSON fallback.
- **Key Modules**:
    - `mdm_section`: Company profile management.
    - `fast_scan_section`: Quick keyword-based and AI-assisted matching of Excel lists.
    - `deep_dive_section`: In-depth RFP analysis.

## Development Rules
- **Versioning**: DO NOT modify `app.py` directly. For any changes, create a new versioned file (e.g., `app_u1.py`, `app_u2.py`, ...) based on the latest version. This ensures safety and easy reversibility.
- Use `gemini-2.5-flash` for AI generation (as of 2026-1).
- Handle Supabase failures gracefully by falling back to local JSON.
- Optimize PDF text extraction for tokens.

## Progress
- [x] Basic MDM functionality.
- [x] Excel-based Fast-Scan with deduplication and Plotly visualization.
- [x] Improved Deep-Dive with keyword-based section extraction (supports long RFPs).
- [x] History Dashboard with summary statistics.
- [x] Dual-mode storage (Supabase & Local JSON).
- [ ] HWP support (Currently shows recommendation to convert to PDF).
- [x] Enhanced UI/UX with Professional Dark Navy Theme.
