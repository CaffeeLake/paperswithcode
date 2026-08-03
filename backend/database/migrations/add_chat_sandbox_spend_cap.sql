DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION 'add_chat_sandbox_spend_cap.sql must run with search_path staging,public';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_sandbox_compute_intervals (
 id uuid PRIMARY KEY, modal_sandbox_id varchar(255) UNIQUE, environment varchar(32) NOT NULL,
 modal_app varchar(255) NOT NULL, app_release_id varchar(255) NOT NULL, image_version varchar(255) NOT NULL,
 worker_generation varchar(64) NOT NULL, origin varchar(24) NOT NULL CHECK (origin IN ('blank_pool','direct','qualification','reconciled_orphan')),
 chat_session_id uuid, cpu_request_millicores integer NOT NULL, cpu_limit_millicores integer NOT NULL,
 memory_request_mib integer NOT NULL, memory_limit_mib integer NOT NULL, reserved_at timestamptz NOT NULL,
 provider_created_at timestamptz, claimed_at timestamptz, termination_requested_at timestamptz,
 terminal_at timestamptz, billing_cycle date NOT NULL, accrued_microusd bigint NOT NULL DEFAULT 0,
 reserved_microusd bigint NOT NULL DEFAULT 0, terminal_reason varchar(64),
 reconciliation_state varchar(24) NOT NULL DEFAULT 'local', updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK (accrued_microusd >= 0 AND reserved_microusd >= 0)
);
ALTER TABLE chat_sandbox_compute_intervals
 DROP CONSTRAINT IF EXISTS chat_sandbox_compute_intervals_origin_check;
ALTER TABLE chat_sandbox_compute_intervals
 ADD CONSTRAINT chat_sandbox_compute_intervals_origin_check
 CHECK (origin IN ('blank_pool','direct','qualification','reconciled_orphan'));
CREATE INDEX IF NOT EXISTS idx_chat_sandbox_compute_cycle_live ON chat_sandbox_compute_intervals(environment,billing_cycle,terminal_at);
CREATE TABLE IF NOT EXISTS chat_sandbox_budget_states (
 id uuid PRIMARY KEY, environment varchar(32) NOT NULL, billing_cycle date NOT NULL, cycle_end_at timestamptz NOT NULL,
 warning_microusd bigint NOT NULL, application_cap_microusd bigint NOT NULL, environment_cap_microusd bigint NOT NULL,
 workspace_cap_microusd bigint NOT NULL, estimated_accrued_microusd bigint NOT NULL DEFAULT 0,
 provider_floor_microusd bigint NOT NULL DEFAULT 0, outstanding_reservation_microusd bigint NOT NULL DEFAULT 0,
 circuit_state varchar(16) NOT NULL DEFAULT 'armed' CHECK (circuit_state IN ('armed','warning','tripped')),
 trip_reason varchar(64), tripped_at timestamptz, acknowledged_at timestamptz, last_metered_at timestamptz,
 last_reconciled_at timestamptz, last_reconciliation_attempt_at timestamptz, reconciliation_state varchar(24) NOT NULL DEFAULT 'unavailable',
 policy_attestation varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(environment,billing_cycle)
);
ALTER TABLE chat_sandbox_budget_states
 ADD COLUMN IF NOT EXISTS last_reconciliation_attempt_at timestamptz;
CREATE TABLE IF NOT EXISTS chat_sandbox_circuit_events (
 id uuid PRIMARY KEY, budget_state_id uuid NOT NULL REFERENCES chat_sandbox_budget_states(id), event_type varchar(64) NOT NULL,
 severity varchar(16) NOT NULL, reason varchar(64), details jsonb NOT NULL DEFAULT '{}'::jsonb,
 delivery_state varchar(24) NOT NULL DEFAULT 'pending', delivery_attempts integer NOT NULL DEFAULT 0,
 next_delivery_attempt_at timestamptz, delivered_at timestamptz,
 fallback_delivery_state varchar(24) NOT NULL DEFAULT 'pending', fallback_delivery_attempts integer NOT NULL DEFAULT 0,
 fallback_next_delivery_attempt_at timestamptz, fallback_delivered_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE chat_sandbox_circuit_events
 ADD COLUMN IF NOT EXISTS next_delivery_attempt_at timestamptz;
ALTER TABLE chat_sandbox_circuit_events
 ADD COLUMN IF NOT EXISTS fallback_delivery_state varchar(24) NOT NULL DEFAULT 'pending',
 ADD COLUMN IF NOT EXISTS fallback_delivery_attempts integer NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS fallback_next_delivery_attempt_at timestamptz,
 ADD COLUMN IF NOT EXISTS fallback_delivered_at timestamptz;
CREATE INDEX IF NOT EXISTS idx_chat_sandbox_circuit_events_recent ON chat_sandbox_circuit_events(budget_state_id,created_at);

ALTER TABLE chat_sandbox_compute_intervals OWNER TO pwc_staging_owner;
ALTER TABLE chat_sandbox_budget_states OWNER TO pwc_staging_owner;
ALTER TABLE chat_sandbox_circuit_events OWNER TO pwc_staging_owner;
GRANT SELECT,INSERT,UPDATE ON chat_sandbox_compute_intervals,chat_sandbox_budget_states,chat_sandbox_circuit_events TO pwc_staging;
REVOKE ALL ON chat_sandbox_compute_intervals,chat_sandbox_budget_states,chat_sandbox_circuit_events FROM paperswithcode_user;
