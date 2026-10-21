-- Additive only. Keep legacy message tables and every manual group/label intact.
CREATE TABLE crm_contact_response LIKE contact_response;
ALTER TABLE crm_contact_response
  MODIFY content LONGTEXT NULL,
  MODIFY attachment LONGTEXT NULL,
  MODIFY content_attribute LONGTEXT NULL,
  MODIFY reply_to_id BIGINT UNSIGNED NULL,
  MODIFY contact_id BIGINT UNSIGNED NOT NULL,
  ADD workspace_id BIGINT UNSIGNED NOT NULL,
  ADD crm_conversation_id BIGINT UNSIGNED NOT NULL,
  ADD crm_customer_id BIGINT UNSIGNED NULL,
  ADD crm_channel_account_id BIGINT UNSIGNED NOT NULL,
  ADD revision BIGINT UNSIGNED NOT NULL,
  ADD snapshot_hash CHAR(64) CHARACTER SET ascii NOT NULL,
  ADD deleted TINYINT NOT NULL DEFAULT 0,
  ADD KEY crm_customer_time (conversation_id, create_date, msg_id);
CREATE TABLE crm_conversation_link (
  conversation_id VARCHAR(70) NOT NULL PRIMARY KEY,
  crm_customer_id BIGINT UNSIGNED NOT NULL,
  verified TINYINT NOT NULL DEFAULT 0,
  evidence VARCHAR(255) NOT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE crm_event_receipt (
  workspace_id BIGINT UNSIGNED NOT NULL,
  event_id VARCHAR(200) COLLATE utf8mb4_bin NOT NULL,
  event_hash CHAR(64) CHARACTER SET ascii NOT NULL,
  received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id,event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- ID 7 and source ID 11 must first be checked free in the production registry.
CREATE VIEW crm_contact_response_visible AS SELECT * FROM crm_contact_response
WHERE deleted=0 AND crm_customer_id IS NOT NULL;
INSERT INTO chatwoot_contact_response_list (id,table_name,`order`) VALUES (7,'crm_contact_response_visible',7);
INSERT INTO chatwoot_msg_source_type (id,name,icon) VALUES (11,'CRM','');
