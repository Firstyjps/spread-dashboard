# Requirements Document

## Introduction

The Risk Framework provides a comprehensive safety layer for the Alphast spread-dashboard execution service. Currently, trades execute without position limits, notional caps, or kill switches. This feature introduces dry-run mode (default ON), position and exposure limits, price sanity validation, order rate limiting, an enhanced kill switch with automatic triggers, circuit breaker cooldown, and a full audit trail — ensuring no trade executes without passing through configurable risk gates.

## Glossary

- **Risk_Engine**: The central module that evaluates all risk checks before allowing order execution
- **Kill_Switch**: A mechanism that halts all trading activity, triggered manually via API or automatically by predefined conditions
- **Circuit_Breaker**: An enhanced version of the existing `CircuitBreaker` class that adds configurable cooldown periods and additional automatic trip conditions
- **Dry_Run_Mode**: An operational mode (default ON) where the system simulates trade execution without placing real orders on exchanges
- **Rate_Limiter**: A per-exchange order rate limiting mechanism that caps the number of orders submitted within a time window
- **Price_Sanity_Validator**: A pre-execution check that rejects orders whose price deviates beyond a configurable band from the reference mid price
- **Audit_Logger**: A persistent logging subsystem that records every risk decision with full context to SQLite
- **Position_Tracker**: A component that tracks current open positions per symbol across all exchanges
- **Notional_Exposure**: The total USD-equivalent value of all open positions across all symbols
- **Reference_Mid**: The current mid price from the most recent orderbook data for a given symbol
- **Cooldown_Period**: The minimum time that must elapse after a Circuit_Breaker trip before trading can resume
- **Risk_Dashboard**: The frontend UI panel displaying real-time risk status, limits, and audit history
- **Risk_API**: The set of FastAPI endpoints exposing risk state, configuration, and manual controls

## Requirements

### Requirement 1: Dry-Run Mode

**User Story:** As a trader, I want the system to default to dry-run mode so that no real orders are placed until I explicitly enable live trading.

#### Acceptance Criteria

1. THE Risk_Engine SHALL default Dry_Run_Mode to ON at system startup, regardless of any previously persisted state
2. WHILE Dry_Run_Mode is ON, THE Risk_Engine SHALL simulate order execution by logging the full order details (symbol, side, size, price, exchange, order type, timestamp) without submitting orders to any exchange
3. WHILE Dry_Run_Mode is ON, THE Audit_Logger SHALL record each simulated trade with a "dry_run" status flag and the same context as a live trade
4. WHEN a user sends a request to disable Dry_Run_Mode via the Risk_API, THE Risk_Engine SHALL require explicit confirmation by accepting a `confirm_live=true` parameter; IF the parameter is missing or false, THE Risk_API SHALL reject the request with a 400 status
5. WHEN Dry_Run_Mode transitions from ON to OFF, THE Audit_Logger SHALL record the transition event with the timestamp and requesting user context
6. WHEN Dry_Run_Mode transitions from OFF to ON, THE Risk_Engine SHALL cancel all pending orders and halt new submissions within 100ms; IF either action fails to complete within 100ms, THEN THE Risk_Engine SHALL abort the transition, remain in live mode, and log the failure reason via the Audit_Logger; IF the 100ms timeout is exceeded, pending orders that were not cancelled within the window MAY remain active

### Requirement 2: Position Limits

**User Story:** As a trader, I want per-symbol position limits enforced so that I cannot accumulate excessive exposure in any single asset.

#### Acceptance Criteria

1. THE Risk_Engine SHALL enforce a configurable maximum position size per symbol, expressed as the absolute value of the net position in BTC equivalent (default: 0.1 BTC equivalent, configurable range: 0.001 to 100 BTC equivalent), where BTC equivalent is calculated using the symbol's current Reference_Mid price
2. WHEN an order would cause the absolute value of the net position (sum of all fills across Bybit and Lighter) for a symbol to exceed the configured maximum, THE Risk_Engine SHALL reject the order and THE Audit_Logger SHALL record the rejection with the current position size, order size, configured limit, and symbol
3. THE Position_Tracker SHALL track the net signed position (buys positive, sells negative) independently per symbol across all exchanges (Bybit and Lighter combined) and compute the absolute value for limit comparison
4. WHEN the Risk_API receives a request to update the maximum position for a symbol, THE Risk_Engine SHALL apply the new limit to subsequent orders without requiring a restart and THE Audit_Logger SHALL record the configuration change with old and new values
5. IF the Position_Tracker detects that the absolute value of the net position for a symbol already exceeds the configured limit (due to a configuration change), THEN THE Risk_Engine SHALL allow orders that would reduce the absolute net position for that symbol and reject any orders that would increase the absolute net position
6. WHEN an order is evaluated against position limits, THE Risk_Engine SHALL compute the projected net position as (current net position + signed order quantity) and compare its absolute value against the configured maximum

### Requirement 3: Notional Exposure Cap

**User Story:** As a trader, I want a total notional exposure cap so that my aggregate USD risk across all positions remains bounded.

#### Acceptance Criteria

1. THE Risk_Engine SHALL enforce a configurable maximum total Notional_Exposure across all symbols (default: $10,000) with a permitted configuration range of $100 to $10,000,000
2. WHEN an order would cause the total Notional_Exposure to exceed the configured cap, THE Risk_Engine SHALL reject the order and log the rejection including the current total exposure, the order's additional notional contribution (order_size × Reference_Mid), the configured cap, and the symbol
3. THE Risk_Engine SHALL compute Notional_Exposure as the sum of absolute values of (position_size × Reference_Mid) for each symbol, such that long and short positions both contribute positively to total exposure
4. WHEN the Risk_API receives a request to update the notional cap, THE Risk_Engine SHALL validate that the new value is within the permitted range ($100 to $10,000,000) and apply the new cap to subsequent orders without requiring a restart
5. IF the total Notional_Exposure already exceeds the configured cap (due to price movement or configuration change), THEN THE Risk_Engine SHALL allow only orders that would decrease the absolute position size for a given symbol and reject any order that would increase the total Notional_Exposure
6. WHEN the Risk_Engine evaluates an incoming order against the notional cap, THE Risk_Engine SHALL compute the projected total Notional_Exposure by adding the absolute notional value of the resulting position for the order's symbol (using Reference_Mid) and comparing it against the configured cap
7. IF the Risk_API receives a request to update the notional cap with a value outside the permitted range, THEN THE Risk_Engine SHALL reject the update and return a 400 status with an error message indicating the valid range

### Requirement 4: Order Rate Limiting

**User Story:** As a trader, I want per-exchange order rate limiting so that the system does not exceed exchange API limits or trigger exchange-level bans.

#### Acceptance Criteria

1. THE Rate_Limiter SHALL enforce a configurable maximum order submission rate per exchange (default: 10 orders per minute per exchange), counting all order operations (place, amend, and cancel) toward the rate limit
2. WHEN an order submission would exceed the configured rate for an exchange, THE Risk_Engine SHALL queue the order and delay submission until the rate window allows it, up to a maximum queue wait time of 30 seconds; THE Risk_Engine SHALL enforce both the queuing and the 30-second timeout within this acceptance criterion
3. IF a queued order has waited longer than 30 seconds without being submitted, THEN THE Risk_Engine SHALL reject the order, remove it from the queue, and log the rejection with a "rate-limit timeout" reason via the Audit_Logger
4. THE Rate_Limiter SHALL track order counts using a sliding window of 60 seconds per exchange
5. WHEN the Rate_Limiter delays an order by more than 5 seconds, THE Audit_Logger SHALL record a rate-limit warning event including the exchange name, order details, queue wait duration, and current rate count
6. THE Risk_API SHALL expose the current order rate and remaining capacity per exchange
7. WHEN the Kill_Switch activates, THE Rate_Limiter SHALL discard all queued orders for every exchange and log each discarded order via the Audit_Logger

### Requirement 5: Price Sanity Validation

**User Story:** As a trader, I want orders validated against a price sanity band so that erroneous or stale-price orders are rejected before reaching the exchange.

#### Acceptance Criteria

1. THE Price_Sanity_Validator SHALL reject any order whose absolute price deviation exceeds the configured band percentage from the Reference_Mid, where deviation is calculated as |order_price - Reference_Mid| / Reference_Mid × 100, and the configured band percentage SHALL be within the range 0.01% to 50.0% (default: 0.5%)
2. WHEN the Price_Sanity_Validator rejects an order, THE Audit_Logger SHALL record the rejection with the order price, Reference_Mid, deviation percentage, and configured band
3. WHEN the Price_Sanity_Validator rejects an order, THE Price_Sanity_Validator SHALL return a rejection response to the caller indicating the rejection reason, the order price, the Reference_Mid, and the computed deviation percentage
4. THE Price_Sanity_Validator SHALL use the most recent orderbook mid price as the Reference_Mid, calculated as (best_bid + best_ask) / 2, where the orderbook data is no older than 2 seconds; IF both best_bid and best_ask are 0.0, THEN THE Price_Sanity_Validator SHALL treat this as missing data and reject the order with an "unavailable reference price" reason
5. IF the Reference_Mid data is older than 2 seconds, THEN THE Price_Sanity_Validator SHALL reject the order with a "stale reference price" reason
6. IF the orderbook contains no best_bid or no best_ask, THEN THE Price_Sanity_Validator SHALL reject the order with an "unavailable reference price" reason
7. WHEN the Risk_API receives a request to update the price sanity band percentage with a value within the range 0.01% to 50.0%, THE Risk_Engine SHALL apply the new band to all validations starting from the next order received after the update is acknowledged
8. IF the Risk_API receives a request to update the price sanity band percentage with a value outside the range 0.01% to 50.0%, THEN THE Risk_Engine SHALL reject the update request with a 400 status and an error message indicating the acceptable range

### Requirement 6: Kill Switch

**User Story:** As a trader, I want a kill switch that can be triggered manually or automatically so that all trading halts immediately when dangerous conditions are detected.

#### Acceptance Criteria

1. WHEN a user sends a kill switch activation request via the Risk_API, THE Kill_Switch SHALL halt all order submissions within 100ms and cancel all pending orders within 500ms
2. WHEN total realized loss within a rolling 24-hour window exceeds a configurable threshold (default: $500), THE Kill_Switch SHALL activate automatically
3. WHEN 3 consecutive order executions result in failure (exchange rejection, response timeout exceeding 5 seconds, or network error), THE Kill_Switch SHALL activate automatically
4. WHEN any monitored price feed has no update for longer than 30 seconds, THE Kill_Switch SHALL activate automatically
5. WHEN the spread inverts by more than a configurable percentage (default: 2%) for at least 1 second, THE Kill_Switch SHALL activate automatically
6. WHEN the Kill_Switch activates, THE Audit_Logger SHALL record the activation event with the trigger reason, timestamp, current positions, notional exposure, order rates, circuit breaker status, and dry-run mode state
7. WHILE the Kill_Switch is active, THE Risk_Engine SHALL reject all new order submissions with a "kill switch active" reason
8. WHEN a user sends a kill switch reset request via the Risk_API with a `confirm_reset=true` parameter, THE Kill_Switch SHALL deactivate and THE Audit_Logger SHALL record the reset event with timestamp and requesting user context
9. WHEN the system starts, THE Kill_Switch SHALL restore its previous activation state from persistent storage so that a restart does not clear an active kill switch

### Requirement 7: Circuit Breaker Cooldown

**User Story:** As a trader, I want a configurable cooldown period after circuit breaker trips so that the system does not immediately resume trading after a safety event.

#### Acceptance Criteria

1. WHEN the Circuit_Breaker trips, THE Risk_Engine SHALL initialize the Cooldown_Period timer to the full configured duration (default: 5 minutes, configurable range: 1 to 60 minutes) and enforce the cooldown before allowing any new order submissions
2. WHILE the Cooldown_Period is active, THE Risk_Engine SHALL reject all new order submissions with a "cooldown active" reason and the remaining cooldown time in seconds
3. WHEN the Cooldown_Period expires, THE Risk_Engine SHALL automatically transition to a ready state (accepting order submissions) and THE Audit_Logger SHALL log the cooldown completion event
4. THE Risk_API SHALL expose the current Circuit_Breaker state including whether cooldown is active and the remaining cooldown duration in seconds
5. WHEN a user sends a cooldown override request via the Risk_API with a `confirm_override=true` parameter, THE Circuit_Breaker SHALL allow early reset and THE Audit_Logger SHALL log the override event
6. IF the Circuit_Breaker trips again while a Cooldown_Period is already active, THEN THE Cooldown_Period timer SHALL reset to the full configured duration
7. IF the Risk_API receives a request to update the cooldown duration with a value outside the range 1 to 60 minutes, THEN THE Risk_Engine SHALL reject the update with a 400 status and an error message indicating the valid range

### Requirement 8: Audit Trail

**User Story:** As a trader, I want every risk decision logged with full context so that I can review and analyze all trading decisions after the fact.

#### Acceptance Criteria

1. THE Audit_Logger SHALL persist every risk decision (approve, reject, simulate) to a SQLite table with: timestamp (millisecond precision), decision type, symbol, order details (side, size, price, exchange, order type), risk state snapshot, and reason
2. THE Audit_Logger SHALL record the full risk state at the time of each decision including: current positions, notional exposure, order rate counts, kill switch status, circuit breaker status, and dry-run mode state
3. WHEN the Audit_Logger writes a record, THE Audit_Logger SHALL complete the write within 10ms; IF the write exceeds 10ms, THEN THE Audit_Logger SHALL treat it as a failure regardless of eventual success and invoke the fallback buffering mechanism
4. THE Risk_API SHALL expose audit trail query endpoints with filtering by time range, symbol, decision type, and status, returning paginated results with a default page size of 50 records and a maximum page size of 200 records
5. THE Audit_Logger SHALL retain audit records for a configurable duration (default: 90 days) and automatically purge records older than the configured duration during the daily cleanup cycle
6. IF the Audit_Logger fails to persist a record (database error or write timeout), THEN THE Audit_Logger SHALL attempt to buffer the record to a local file and emit a warning alert without blocking order execution; IF both database write and file buffering fail, THEN THE Audit_Logger SHALL emit a warning and continue execution without persisting the record
7. WHEN the Audit_Logger detects that previously buffered records exist and the database connection is restored, THE Audit_Logger SHALL replay buffered records to SQLite in chronological order and delete the buffer file upon successful persistence

### Requirement 9: Risk Status API

**User Story:** As a trader, I want real-time risk status exposed via API so that I can monitor limits, positions, and safety state from the dashboard or external tools.

#### Acceptance Criteria

1. THE Risk_API SHALL expose a `GET /api/v1/risk/status` endpoint returning the current state of all risk components (positions per symbol, total notional exposure, order rates per exchange, kill switch status, circuit breaker status with remaining cooldown seconds, and dry-run mode flag) within 500ms
2. THE Risk_API SHALL expose a `POST /api/v1/risk/kill-switch` endpoint that accepts an `action` field with value "activate" or "reset", where "activate" triggers the Kill_Switch and "reset" requires an additional `confirm_reset=true` parameter before deactivating it
3. THE Risk_API SHALL expose a `PUT /api/v1/risk/config` endpoint for updating risk parameters (position limits, notional cap, rate limits, price band percentage, cooldown duration) without requiring a restart, applying new values to subsequent risk checks; THE endpoint SHALL be available whenever the system is not in dry-run mode
4. IF a request to a write endpoint (POST, PUT) is missing the `X-API-Key` header or provides an invalid key, THEN THE Risk_API SHALL reject the request with a 401 status and an error message indicating authentication failure
5. THE Risk_API SHALL expose a `GET /api/v1/risk/audit` endpoint returning paginated audit trail records with a default page size of 50, a maximum page size of 500, and support for filtering by time range, symbol, decision type, and status
6. WHEN any risk parameter changes via the Risk_API, THE Audit_Logger SHALL record the configuration change with old value, new value, parameter name, timestamp, and the requesting API key identifier
7. IF a `PUT /api/v1/risk/config` request contains a parameter value outside its valid range (e.g., negative position limit, notional cap below zero, cooldown duration less than 0 seconds), THEN THE Risk_API SHALL reject the request with a 400 status and an error message indicating which parameter failed validation

### Requirement 10: Risk Dashboard UI

**User Story:** As a trader, I want a risk management panel in the dashboard so that I can visually monitor and control the risk framework without using raw API calls.

#### Acceptance Criteria

1. THE Risk_Dashboard SHALL display the current state of all risk components: dry-run mode toggle, position limits with current utilization shown as both absolute value and percentage of limit, notional exposure with cap utilization shown as both absolute USD value and percentage of cap, order rates per exchange shown as orders used and remaining capacity, kill switch status (active/inactive), and circuit breaker status with remaining cooldown duration in seconds when active
2. THE Risk_Dashboard SHALL provide a toggle control for Dry_Run_Mode with a confirmation dialog that states the consequence of disabling dry-run mode and requires the user to explicitly confirm or cancel the action before any state change is sent to the Risk_API
3. THE Risk_Dashboard SHALL provide a kill switch activation button with a confirmation dialog requiring explicit user confirmation before sending the activation request, and a separate reset button with its own confirmation dialog before sending the reset request
4. THE Risk_Dashboard SHALL display the most recent 50 audit trail entries with color-coded status (green for approved, red for rejected, yellow for simulated)
5. THE Risk_Dashboard SHALL auto-refresh risk status every 2 seconds via polling or WebSocket subscription
6. WHEN the Kill_Switch activates automatically, THE Risk_Dashboard SHALL display an alert banner fixed at the top of the dashboard viewport indicating the trigger reason, and the banner SHALL remain visible until the user dismisses it or the Kill_Switch is reset
7. IF the Risk_Dashboard fails to retrieve data from the Risk_API for 3 consecutive refresh cycles, THEN THE Risk_Dashboard SHALL display a connectivity warning indicating that risk data may be stale and show the timestamp of the last successful update
8. WHEN a user confirms a control action (dry-run toggle, kill switch activation, or kill switch reset) and the Risk_API responds, THE Risk_Dashboard SHALL display a success or failure notification within 1 second indicating the outcome of the action
