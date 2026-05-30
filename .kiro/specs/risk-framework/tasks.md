# Implementation Plan: Risk Framework

## Overview

Implement a comprehensive risk management framework for the spread-dashboard trading system. The framework introduces a centralized `RiskEngine` that intercepts all order submissions, enforcing configurable risk gates (dry-run mode, position limits, notional caps, rate limiting, price sanity, kill switch, circuit breaker cooldown) before orders reach exchanges. All decisions are persisted to an audit trail, exposed via REST API, and visualized in a frontend dashboard panel.

The implementation follows a bottom-up approach: data models and core components first, then the orchestrating engine, API layer, and finally the frontend dashboard.

## Tasks

- [ ] 1. Set up risk module structure and data models
  - [ ] 1.1 Create risk module directory and data model definitions
    - Create `backend/app/risk/` directory with `__init__.py`
    - Define `OrderRequest`, `RiskConfig`, `RiskStateSnapshot`, `RiskEvaluation`, and `RiskDecision` dataclasses in `backend/app/risk/models.py`
    - Include all fields from the design: symbol, side, qty, price, exchange, order_type, source, timestamp_ms for OrderRequest
    - Include all config fields with defaults and valid ranges as specified in design
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.2, 7.1_

  - [ ] 1.2 Create SQLite schema and database initialization for audit and kill switch persistence
    - Create `backend/app/risk/database.py` with schema initialization
    - Define `risk_audit` table with all columns: id, timestamp_ms, decision_type, symbol, side, qty, price, exchange, order_type, source, reason, dry_run_mode, kill_switch_active, circuit_breaker_tripped, cooldown_active, positions_json, notional_exposure_usd, order_rates_json, created_at
    - Define `risk_kill_switch_state` table with id (constrained to 1), active, reason, activation_ts
    - Create indexes on timestamp_ms, symbol, and decision_type
    - _Requirements: 8.1, 6.9_

- [ ] 2. Implement PositionTracker and NotionalCalculator
  - [ ] 2.1 Implement PositionTracker component
    - Create `backend/app/risk/position_tracker.py`
    - Implement `update_position(symbol, side, qty, exchange)` — buys positive, sells negative
    - Implement `get_net_position(symbol)` — returns net signed position combined across exchanges
    - Implement `get_all_positions()` — returns dict of all tracked positions
    - Implement `would_exceed_limit(symbol, side, qty, limit, reference_mid)` — checks BTC equivalent limit
    - Implement `would_reduce_position(symbol, side, qty)` — checks if order reduces absolute net position
    - _Requirements: 2.3, 2.5, 2.6_

  - [ ]* 2.2 Write property test for PositionTracker (Property 3: Position tracking correctness)
    - **Property 3: Position tracking correctness**
    - **Validates: Requirements 2.3**
    - Use Hypothesis to generate arbitrary sequences of fills and verify net position equals algebraic sum

  - [ ] 2.3 Implement NotionalCalculator component
    - Create `backend/app/risk/notional_calculator.py`
    - Implement `compute_total_exposure(reference_mids)` — sum of |position × mid| for all symbols
    - Implement `would_exceed_cap(symbol, side, qty, reference_mid, cap)` — projects total notional after order
    - Depends on PositionTracker for position data
    - _Requirements: 3.1, 3.3, 3.6_

  - [ ]* 2.4 Write property test for NotionalCalculator (Property 5: Notional exposure cap enforcement)
    - **Property 5: Notional exposure cap enforcement**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.6**
    - Generate arbitrary position states and orders, verify cap enforcement logic

- [ ] 3. Implement PriceSanityValidator and OrderRateLimiter
  - [ ] 3.1 Implement PriceSanityValidator component
    - Create `backend/app/risk/price_validator.py`
    - Implement `validate(order_price, symbol, exchange)` returning `PriceValidationResult`
    - Check deviation: |order_price - reference_mid| / reference_mid × 100 > band_pct
    - Check staleness: reject if orderbook data older than 2 seconds
    - Check availability: reject if no best_bid or best_ask
    - Read reference mid from existing spread_engine tick cache
    - _Requirements: 5.1, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 3.2 Write property test for PriceSanityValidator (Property 8: Price sanity validation)
    - **Property 8: Price sanity validation**
    - **Validates: Requirements 5.1, 5.3, 5.4**
    - Generate arbitrary prices and reference mids, verify rejection iff deviation exceeds band

  - [ ] 3.3 Implement OrderRateLimiter component
    - Create `backend/app/risk/rate_limiter.py`
    - Implement sliding window tracking per exchange using deque of timestamps
    - Implement `acquire(exchange)` — queues if at limit, returns False on 30s timeout
    - Implement `get_rate_status(exchange)` — current count and remaining capacity
    - Implement `discard_all()` — discard all queued orders on kill switch activation
    - Count all order operations (place, amend, cancel) toward rate limit
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.7_

  - [ ]* 3.4 Write property test for OrderRateLimiter (Property 15: Sliding window rate limiting)
    - **Property 15: Sliding window rate limiting**
    - **Validates: Requirements 4.1, 4.2, 4.4**
    - Generate arbitrary order timestamp sequences, verify window counting and queueing behavior

- [ ] 4. Implement KillSwitch and CircuitBreakerV2
  - [ ] 4.1 Implement KillSwitch component
    - Create `backend/app/risk/kill_switch.py`
    - Implement `activate(reason)` — halt trading, cancel pending, persist state to SQLite
    - Implement `reset(confirm_reset)` — deactivate only with explicit confirmation
    - Implement `restore_state()` — load persisted state on startup
    - Implement `check_auto_triggers(rolling_loss_24h, consecutive_failures, feed_stale, spread_inverted)` — returns trigger reason or None
    - Auto-trigger conditions: loss > threshold, 3 consecutive failures, feed stale > 30s, spread inverted > 2% for 1s
    - Default to ACTIVE if persistence layer corrupted (fail-safe)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.8, 6.9_

  - [ ]* 4.2 Write property tests for KillSwitch (Properties 9, 10, 11)
    - **Property 9: Kill switch blocks all orders**
    - **Property 10: Consecutive failure auto-trigger**
    - **Property 11: Loss threshold auto-trigger**
    - **Validates: Requirements 6.2, 6.3, 6.7**
    - Generate arbitrary order sequences and failure patterns, verify blocking and auto-trigger behavior

  - [ ] 4.3 Implement CircuitBreakerV2 component
    - Create `backend/app/risk/circuit_breaker.py`
    - Implement `trip(reason)` — trip breaker and start cooldown timer
    - Implement `check_cooldown()` — returns (is_blocked, remaining_seconds)
    - Implement `override_cooldown(confirm_override)` — early reset with confirmation
    - Implement `on_cooldown_expired()` — transition to ready state
    - Re-trip resets cooldown timer to full configured duration
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.6_

  - [ ]* 4.4 Write property tests for CircuitBreakerV2 (Properties 13, 14)
    - **Property 13: Cooldown blocks then allows**
    - **Property 14: Re-trip resets cooldown timer**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.6**
    - Generate arbitrary trip/time sequences, verify cooldown blocking and timer reset behavior

- [ ] 5. Implement AuditLogger
  - [ ] 5.1 Implement AuditLogger component
    - Create `backend/app/risk/audit_logger.py`
    - Implement async background writer using asyncio.Queue for non-blocking writes (<10ms)
    - Implement `log_decision(evaluation)` — queue risk decision for persistence
    - Implement `log_event(event_type, details)` — log config changes, kill switch events
    - Implement `query(time_from, time_to, symbol, decision_type, status, page, page_size)` — filtered paginated results
    - Implement buffer fallback to `./data/audit_buffer.jsonl` on DB failure
    - Implement `_flush_buffer()` — replay buffered records when DB restored
    - Implement `_daily_purge()` — remove records older than retention_days
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 5.2 Write property tests for AuditLogger (Properties 17, 18, 19)
    - **Property 17: Audit record round-trip persistence**
    - **Property 18: Audit query filtering correctness**
    - **Property 19: Audit retention purge**
    - **Validates: Requirements 8.1, 8.2, 8.4, 8.5**
    - Generate arbitrary audit records and query filters, verify persistence and filtering correctness

- [ ] 6. Checkpoint - Core components complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement RiskEngine orchestrator
  - [ ] 7.1 Implement RiskEngine with evaluation pipeline
    - Create `backend/app/risk/engine.py`
    - Implement `evaluate_order(order)` with priority-ordered checks: kill switch → cooldown → dry-run → price sanity → position limit → notional cap → rate limit
    - Implement `set_dry_run(enabled, confirm_live)` — toggle with confirmation requirement
    - Implement `get_risk_state()` — return full RiskStateSnapshot
    - Implement `update_config(updates)` — hot-reload parameters with range validation
    - Default dry_run to True at startup regardless of persisted state
    - Cancel all pending orders within 100ms when dry-run transitions OFF→ON
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.5, 3.1, 3.2, 3.5, 5.1, 6.7, 7.1_

  - [ ]* 7.2 Write property tests for RiskEngine (Properties 1, 2, 4, 6, 12)
    - **Property 1: Dry-run mode simulates all orders**
    - **Property 2: Position limit enforcement**
    - **Property 4: Over-limit position reduction allowed**
    - **Property 6: Over-cap notional reduction allowed**
    - **Property 12: Confirmation required for dangerous actions**
    - **Validates: Requirements 1.2, 1.3, 1.4, 2.1, 2.2, 2.5, 2.6, 3.5, 6.8, 7.5**

  - [ ] 7.3 Integrate RiskEngine with existing executors
    - Modify `backend/app/execution/iceberg_executor.py` to call `risk_engine.evaluate_order()` before exchange submission
    - Modify `backend/app/execution/maker_engine.py` to call `risk_engine.evaluate_order()` before exchange submission
    - Add `position_tracker.update_position(fill)` calls after fill confirmations in executors
    - Wire kill switch auto-triggers into existing poll loop's `_check_feed_staleness` and `circuit_breaker.record_execution_failure`
    - _Requirements: 1.2, 2.3, 6.3, 6.4_

- [ ] 8. Implement Risk API endpoints
  - [ ] 8.1 Create Risk API router with authentication
    - Create `backend/app/api/risk_routes.py`
    - Implement `GET /api/v1/risk/status` — return full RiskStateSnapshot within 500ms
    - Implement `POST /api/v1/risk/kill-switch` — accept action "activate" or "reset" with confirm_reset parameter
    - Implement `PUT /api/v1/risk/config` — update risk parameters with range validation
    - Implement `GET /api/v1/risk/audit` — paginated audit trail with filtering (default 50, max 500)
    - Implement `POST /api/v1/risk/dry-run` — toggle dry-run mode with confirm_live parameter
    - Add X-API-Key authentication middleware for write endpoints (POST, PUT)
    - Return 401 for missing/invalid API key, 400 for invalid parameters
    - Mount router in `backend/app/main.py`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [ ]* 8.2 Write property test for API authentication (Property 20)
    - **Property 20: API authentication enforcement**
    - **Validates: Requirements 9.4**
    - Generate arbitrary API keys and requests, verify 401 rejection for invalid/missing keys

  - [ ]* 8.3 Write property test for config validation (Property 7)
    - **Property 7: Configuration parameter range validation**
    - **Validates: Requirements 3.4, 3.7, 5.7, 5.8, 7.7, 9.7**
    - Generate arbitrary parameter values, verify 400 rejection for out-of-range values and acceptance for valid values

  - [ ]* 8.4 Write unit tests for Risk API endpoints
    - Test kill switch activate/reset flow
    - Test config update with valid and invalid values
    - Test audit query with pagination and filters
    - Test dry-run toggle with and without confirmation
    - Test rate status endpoint response format
    - _Requirements: 9.1, 9.2, 9.3, 9.5, 9.6_

- [ ] 9. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Implement Risk Dashboard UI
  - [ ] 10.1 Create RiskPanel component with status display
    - Create `frontend/src/components/risk/RiskPanel.tsx`
    - Display all risk components: dry-run mode, positions with utilization %, notional exposure with cap %, order rates per exchange (used/remaining), kill switch status, circuit breaker status with cooldown seconds
    - Implement auto-refresh polling every 2 seconds via `GET /api/v1/risk/status`
    - Add connectivity warning after 3 consecutive failed refreshes showing last successful update timestamp
    - Create `frontend/src/services/riskApi.ts` for API client functions
    - Create `frontend/src/types/risk.ts` for TypeScript type definitions matching backend models
    - _Requirements: 10.1, 10.5, 10.7_

  - [ ] 10.2 Implement control actions with confirmation dialogs
    - Add dry-run mode toggle with confirmation dialog stating consequences of disabling
    - Add kill switch activation button with confirmation dialog
    - Add kill switch reset button with separate confirmation dialog
    - Display success/failure notification within 1 second after API response
    - _Requirements: 10.2, 10.3, 10.8_

  - [ ] 10.3 Implement audit trail display and alert banner
    - Display most recent 50 audit entries with color coding: green (approved), red (rejected), yellow (simulated)
    - Add alert banner fixed at top of viewport on automatic kill switch activation showing trigger reason
    - Banner remains visible until user dismisses or kill switch is reset
    - _Requirements: 10.4, 10.6_

  - [ ]* 10.4 Write frontend component tests for RiskPanel
    - Test all risk sections render with mock data
    - Test confirmation dialogs appear before destructive actions
    - Test audit entries display with correct color coding
    - Test alert banner appears on kill switch activation
    - Test connectivity warning after 3 failed refreshes
    - Test success/failure notification on action completion
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 10.7, 10.8_

- [ ] 11. Integration wiring and kill switch queue discard
  - [ ] 11.1 Wire kill switch to rate limiter queue discard and complete integration
    - Implement kill switch activation calling `rate_limiter.discard_all()` and logging each discarded order
    - Wire rate limit warning logging (delay >5s triggers audit warning event)
    - Ensure kill switch activation halts submissions within 100ms and cancels pending within 500ms
    - Verify dry-run OFF→ON cancels pending orders within 100ms
    - _Requirements: 4.5, 4.7, 6.1, 1.6_

  - [ ]* 11.2 Write property test for kill switch queue discard (Property 16)
    - **Property 16: Kill switch discards all queued orders**
    - **Validates: Requirements 4.7**
    - Generate arbitrary queued order states, verify all discarded on kill switch activation

  - [ ]* 11.3 Write integration tests for cross-component flows
    - Test kill switch activation end-to-end with queue state
    - Test feed staleness auto-trigger
    - Test spread inversion auto-trigger
    - Test kill switch persistence across simulated restart
    - Test audit buffer replay after DB failure recovery
    - Test rate limit timeout rejection after 30s
    - _Requirements: 6.1, 6.4, 6.5, 6.9, 8.6, 8.7, 4.3_

- [ ] 12. Final checkpoint - All components integrated
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1–20)
- Unit tests validate specific examples and edge cases
- The backend uses Python with FastAPI, SQLite for persistence, and Hypothesis for property-based testing
- The frontend uses React with TypeScript
- All risk parameters are hot-reloadable via API without restart
- Kill switch defaults to ACTIVE on corrupted state (fail-safe design)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "3.1", "3.3"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.2", "3.4", "4.1", "4.3"] },
    { "id": 3, "tasks": ["2.4", "4.2", "4.4", "5.1"] },
    { "id": 4, "tasks": ["5.2", "7.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "8.1"] },
    { "id": 6, "tasks": ["8.2", "8.3", "8.4", "10.1"] },
    { "id": 7, "tasks": ["10.2", "10.3", "11.1"] },
    { "id": 8, "tasks": ["10.4", "11.2", "11.3"] }
  ]
}
```
