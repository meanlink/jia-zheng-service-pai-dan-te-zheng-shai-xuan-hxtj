CREATE TABLE IF NOT EXISTS category_feature_rules (
  id INT AUTO_INCREMENT PRIMARY KEY,
  service ENUM('deep_clean','appliance_clean') NOT NULL,
  version INT NOT NULL,
  features JSON NOT NULL,
  active BOOLEAN NOT NULL DEFAULT FALSE,
  created_by VARCHAR(48) NOT NULL,
  previous_rule_id INT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY service_version (service,version),
  KEY active_rule (service,active),
  FOREIGN KEY (previous_rule_id) REFERENCES category_feature_rules(id)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS feature_rule_comparisons (
  id INT AUTO_INCREMENT PRIMARY KEY,
  service ENUM('deep_clean','appliance_clean') NOT NULL,
  baseline_rule_id INT NOT NULL,
  candidate_features JSON NOT NULL,
  baseline JSON NOT NULL,
  candidate JSON NOT NULL,
  history_checksum CHAR(64) NOT NULL,
  holdout_since DATE NOT NULL,
  eligibility ENUM('pass','regression','insufficient') NOT NULL,
  note VARCHAR(500) NOT NULL,
  created_by VARCHAR(48) NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  enabled_rule_id INT NULL,
  enabled_by VARCHAR(48) NULL,
  enabled_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY service_comparisons (service,id),
  FOREIGN KEY (baseline_rule_id) REFERENCES category_feature_rules(id),
  FOREIGN KEY (enabled_rule_id) REFERENCES category_feature_rules(id)
) CHARACTER SET utf8mb4;
