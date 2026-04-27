# Multi-Number Wallet Profiles Architecture

## Overview
Currently, Mazao AI assumes a 1:1 relationship between a Tenant and a phone number. As users scale, they often operate multiple Safaricom numbers (e.g., Personal, Business, M-PESA Till). This architecture defines the transition to a 1:N relationship where one Tenant can manage multiple "Wallet Profiles".

## Core Model
The system will transition from an implicit phone identity to an explicit `wallets` model.

### Wallet Profile Schema
- `id`: UUID (Primary Key)
- `tenant_id`: UUID (Foreign Key to `tenants`)
- `phone_number`: String (E.164 format, Unique across all wallets)
- `label`: String (e.g., "Personal", "Hardware Shop", "Mama Mboga")
- `is_primary`: Boolean (Default: false, exactly one per tenant must be true)
- `created_at`: Timestamp
- `updated_at`: Timestamp

## Data Partitioning Logic
To maintain financial integrity, all transactional data must be linked to a specific `wallet_id` instead of just a `tenant_id`.

### Affected Domains
1. **M-Pesa Statements**: Parsed statements must be attributed to the wallet that received the SMS.
2. **Fuliza Tracking**: Fuliza limits and balances must be tracked per number.
3. **Gas Tracking**: Consumption patterns vary by household/business; wallets allow separate tracking if used at different locations.
4. **Electricity Tokens**: Token depletion and projections must be wallet-scoped.
5. **Credit Insights**: Future loan eligibility and financial health reports will be aggregated or segmented by wallet.

## Active Context Model
The User operates within one "Active Wallet" context at a time in the Telegram interface.

- **Context Switching**: Commands like `/switch_wallet` or `/wallets` allow the user to change their active profile.
- **Global Commands**: `/report` and `/status` will reflect the data of the *currently active* wallet.
- **Aggregation**: A special "All Wallets" view may be provided for high-level summaries.

## UX Model & Command Surface
A new command `/wallets` will be introduced post-onboarding to manage profiles.

### Proposed Flow
1. **List Wallets**: View all linked numbers and their labels.
2. **Add Wallet**: Link a new number via SMS verification or manual entry.
3. **Switch Wallet**: Change the active context for reporting and ingestion.
4. **Rename Wallet**: Update labels for better organization.
5. **Remove Wallet**: Safely unlink a number (archiving data instead of deleting).

## Roadmap & Milestones
- **Phase**: Phase 20+ (Post Payment Stabilization)
- **Milestone**: `T10_MULTI_NUMBER_WALLET_SUPPORT`
- **Dependencies**: 
  - Daraja API fully live and stable.
  - Payment flows for premium subscriptions finalized.
  - Command surface governance (P19) completed.

## Risks & Guardrails
- **Data Leakage**: Strict RLS (Row Level Security) must ensure `wallet_id` scoping.
- **Aggregation Errors**: VAT and financial reporting must not double-count transactions across wallets.
- **Onboarding Simplicity**: Multi-number support must not complicate the initial user setup; it is a "Power User" feature.
- **Fuliza Attribution**: SMS parsing must accurately detect which number the message was sent to if possible.

## Safety Requirements
- All database queries MUST include a `wallet_id` filter once the migration is complete.
- Default behavior for legacy accounts: Create a single primary wallet using their current phone number.
