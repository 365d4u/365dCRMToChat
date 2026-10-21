-- CRM-owned historical reference cache. Do not alter legacy messages or IDs.
CREATE TABLE crm_respond_customer_link (
 respond_id VARCHAR(70) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
 crm_customer_id BIGINT UNSIGNED NOT NULL,
 workspace_id BIGINT UNSIGNED NOT NULL,
 source_reference_id BIGINT UNSIGNED NOT NULL,
 source_revision BIGINT UNSIGNED NOT NULL,
 verified TINYINT NOT NULL,
 evidence VARCHAR(255) NOT NULL,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 KEY crm_customer_reference (crm_customer_id, verified)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
ALTER TABLE crm_conversation_link ADD KEY crm_customer_history (crm_customer_id, verified);
