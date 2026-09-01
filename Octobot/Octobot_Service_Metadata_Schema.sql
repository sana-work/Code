-- Octobot service metadata schema
-- Minimal design: provider services and their column dictionaries.

BEGIN;

CREATE TABLE octobot_service (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_key TEXT NOT NULL UNIQUE,
    business_domain TEXT NOT NULL CHECK (
        business_domain IN ('ASSET_SERVICES', 'TRANSACTION_MANAGEMENT')
    ),

    catalog TEXT NOT NULL,
    portable_id UUID NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    english_name TEXT NOT NULL,
    description TEXT,
    service_type TEXT,
    data_entitlement_model_type TEXT,
    filter_query TEXT,
    account_types TEXT[] NOT NULL DEFAULT '{}',
    source_domain TEXT,
    source_subdomain TEXT,
    dataset TEXT,

    aliases TEXT[] NOT NULL DEFAULT '{}',

    endpoint_path TEXT NOT NULL DEFAULT '/api/services/{portable_id}/filter',
    provider_settings JSONB NOT NULL DEFAULT '{}'::jsonb,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    extra_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (catalog, source_name)
);

CREATE INDEX octobot_service_domain_idx
    ON octobot_service (business_domain, is_active);

CREATE INDEX octobot_service_aliases_gin_idx
    ON octobot_service USING GIN (aliases);

CREATE TABLE octobot_service_column (
    service_column_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT NOT NULL REFERENCES octobot_service(service_id)
        ON DELETE CASCADE,

    original_column_name TEXT NOT NULL,
    english_column_name TEXT,
    column_description TEXT,
    data_type TEXT NOT NULL,
    column_order INTEGER NOT NULL CHECK (column_order > 0),

    is_trusted BOOLEAN NOT NULL DEFAULT FALSE,
    is_default_output BOOLEAN NOT NULL DEFAULT FALSE,
    is_critical_data_element BOOLEAN NOT NULL DEFAULT FALSE,
    critical_data_element_category TEXT,
    is_grain BOOLEAN NOT NULL DEFAULT FALSE,
    grain_type TEXT,
    is_key BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER,
    is_output_column BOOLEAN NOT NULL DEFAULT FALSE,
    is_calculated_column BOOLEAN NOT NULL DEFAULT FALSE,
    is_client_code_column BOOLEAN NOT NULL DEFAULT FALSE,
    is_parameter BOOLEAN NOT NULL DEFAULT FALSE,
    is_range BOOLEAN NOT NULL DEFAULT FALSE,
    is_required_filter BOOLEAN NOT NULL DEFAULT FALSE,
    filter_group_number INTEGER,
    partition_key_index INTEGER,
    is_partitioning_field BOOLEAN NOT NULL DEFAULT FALSE,
    expression TEXT,

    aliases TEXT[] NOT NULL DEFAULT '{}',
    extra_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (service_id, original_column_name),
    UNIQUE (service_id, column_order)
);

CREATE INDEX octobot_service_column_required_idx
    ON octobot_service_column (service_id, column_order)
    WHERE is_required_filter = TRUE;

CREATE INDEX octobot_service_column_default_idx
    ON octobot_service_column (service_id, column_order)
    WHERE is_default_output = TRUE;

CREATE INDEX octobot_service_column_aliases_gin_idx
    ON octobot_service_column USING GIN (aliases);

COMMIT;
