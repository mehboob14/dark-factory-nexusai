# Pocketful Stage 2 — Implementation Plan

## Objective
Extend stage 1 with browser UI and payment authorizations (holds). Users can reserve funds via authorizations and capture them later.

## Architecture

### Data Model
- **Authorization**: Holds funds without immediate transfer. Captures move held funds. Status: open → captured/voided/expired.
- **Wallet Fields**: balance (total), available (total - held), held (sum of open authorizations).
- **Payment Enhancement**: Now includes authorization_id to link captures back to their hold.

### API Changes
1. **GET /me**: Added total, available, held fields.
2. **POST /authorizations**: Create idempotent hold (requires bearer token + Idempotency-Key).
3. **POST /authorizations/{id}/capture**: Receiver captures held funds (idempotent).
4. **POST /authorizations/{id}/void**: Payer cancels hold.
5. **GET /authorizations**: List holds with direction/status filters.
6. **Payment/Request Validation**: Now checks available instead of balance.

### Browser Routes
- GET `/` (home): Pay form, request form, activity feed, balance display
- GET `/requests`: Incoming/outgoing requests with actions
- GET `/split`: Split form
- GET `/signup`: Signup flow
- GET `/login`: Login flow
- All routes return HTML for Accept: text/html, JSON otherwise

### Key Constraints
- Holds reserve funds but don't move them
- Captures are idempotent and move held funds
- Concurrent operations serialize using single mutex
- Export/import preserve authorizations
- No holds expire automatically (explicit check on reads)

## Implementation Summary
- ✅ Updated store.py with Authorization dataclass, validation, and methods
- ✅ Added authorization endpoints to main.py
- ✅ Added browser routes with basic HTML + data-testid attributes
- ✅ Updated wallet calculations (total, available, held)
- ✅ Updated payment/request validation to check available
- ✅ Fixture support for seeded authorizations
- ✅ Export/import preservation of authorizations

## Testing Strategy
- Harness: Python harness tests verify API conformance
- Acceptance suite: Python/Playwright tests verify browser UI and API features
- Key test areas:
  - Authorization creation with available funds check
  - Capture idempotency and partial captures
  - Void authorization (payer only)
  - Held funds correctly exclude from available
  - Concurrent authorization serialization
  - Browser route rendering and form submission
