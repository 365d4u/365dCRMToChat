-- Apply before enabling CRM_TO_CHAT_CUSTOMER_AVATAR_EVENTS.
CREATE TABLE crm_customer_avatar (
  workspace_id BIGINT UNSIGNED NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  revision BIGINT UNSIGNED NOT NULL,
  avatar_url VARCHAR(600) NULL,
  PRIMARY KEY (workspace_id,customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
