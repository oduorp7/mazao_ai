# Daraja STK Live Activation Runbook

## 1. Overview
- **Purpose**: Live activation of Daraja STK payments (Lipa Na M-Pesa Online).
- **Precondition**: `DARAJA_PASSKEY` received from Safaricom.
- **System State**: Fully production-ready (Phase 19C Certified).
- **Stakeholder**: Chief Engineer / Production Engineer.

## 2. Preflight Checklist
- [ ] Fly machine `mazao-ai` is running.
- [ ] Health checks are passing (`fly status`).
- [ ] STK push logic is verified (native `daraja.py` implementation).
- [ ] Callback route `/mpesa/stk/callback` is registered and reachable.
- [ ] Logs are clean (no current tracebacks or network errors).
- [ ] Phone formatting logic (`2547XXXXXXXX`) is active and tested.

## 3. Activation Steps
1.  **Set Production Secrets**:
    ```bash
    fly secrets set DARAJA_PASSKEY="<your_safaricom_passkey>" -a mazao-ai
    ```
2.  **Redeploy**:
    ```bash
    fly deploy --ha=false
    ```
3.  **Monitor Startup Logs**:
    ```bash
    fly logs -a mazao-ai
    ```
    *Expect: `bot_heartbeat` and `webhook_server_live` signals.*

4.  **Manual Trigger**:
    - Open Telegram.
    - Run `/upgrade`.
    - Select a plan (Core/Pro).
    - Provide a valid M-Pesa phone number.

## 4. Success Path Validation
- [ ] STK prompt appears on the mobile device within 5–10 seconds.
- [ ] User enters M-Pesa PIN.
- [ ] Log shows `daraja_stk_callback_received`.
- [ ] Bot notifies user with `PAYMENT_SUCCESS_ENHANCED`.
- [ ] Run `/status` to confirm the subscription plan is active.

## 5. Failure Path Validation
- [ ] **Cancellation**: Trigger STK and cancel on phone.
    *Expect: No activation; `PAYMENT_FAILED` message.*
- [ ] **Timeout**: Trigger STK and wait for timeout.
    *Expect: Graceful timeout handling.*
- [ ] **Insufficient Funds**: Verify Safaricom rejection message handling.

## 6. Idempotency & Security Checks
- [ ] Verify `duplicate_txn_ignored` log if a callback is retried.
- [ ] Ensure `payment_requests` status remains `confirmed`.
- [ ] Verify no secrets or keys are leaked in logs.

## 7. Rollback Plan
If activation fails or destabilizes the system:
1.  **Unset Secret**:
    ```bash
    fly secrets unset DARAJA_PASSKEY -a mazao-ai
    ```
2.  **Redeploy**: `fly deploy`
3.  **Verify**: Ensure system remains stable (falls back to disabled STK state).

## 8. Sign-off Criteria
- All success and failure flows validated.
- No regressions in `/status`, `/report`, `/fuliza`, `/gas`.
- Logs are clean of tracebacks.
- System certified live for Phase 19D.
