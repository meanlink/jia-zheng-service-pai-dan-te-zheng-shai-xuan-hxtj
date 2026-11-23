CREATE TABLE users (
  username VARCHAR(48) PRIMARY KEY,
  display_name VARCHAR(48) NOT NULL,
  role ENUM('intake','dispatcher','supervisor') NOT NULL,
  password_hash VARCHAR(160) NOT NULL
) CHARACTER SET utf8mb4;

CREATE TABLE technicians (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(24) NOT NULL UNIQUE,
  name VARCHAR(48) NOT NULL,
  skill ENUM('deep_clean','appliance_clean') NOT NULL,
  certificate VARCHAR(48) NOT NULL UNIQUE,
  valid_through DATE NOT NULL,
  experience_years SMALLINT NOT NULL CHECK (experience_years BETWEEN 0 AND 60),
  active BOOLEAN NOT NULL DEFAULT TRUE
) CHARACTER SET utf8mb4;

CREATE TABLE service_orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(32) NOT NULL UNIQUE,
  customer VARCHAR(60) NOT NULL,
  neighborhood VARCHAR(80) NOT NULL,
  service ENUM('deep_clean','appliance_clean') NOT NULL,
  service_date DATE NOT NULL,
  slot ENUM('am','pm','evening') NOT NULL,
  area_m2 SMALLINT NOT NULL CHECK (area_m2 BETWEEN 10 AND 500),
  dirt_level SMALLINT NOT NULL CHECK (dirt_level BETWEEN 1 AND 5),
  obstacles SMALLINT NOT NULL CHECK (obstacles BETWEEN 0 AND 15),
  supplies BOOLEAN NOT NULL,
  baseline_minutes SMALLINT NOT NULL CHECK (baseline_minutes BETWEEN 15 AND 720),
  status ENUM('received','assigned','followed_up') NOT NULL DEFAULT 'received',
  KEY history_lookup (service,status,service_date,id)
) CHARACTER SET utf8mb4;

CREATE TABLE dispatch_plans (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_id INT NOT NULL UNIQUE,
  technician_id INT NOT NULL,
  status ENUM('queued','analyzed','failed','trial','review_pre','reviewed','confirmed','review_post','closed') NOT NULL,
  analysis JSON,
  error_message VARCHAR(255),
  predicted_minutes SMALLINT CHECK (predicted_minutes BETWEEN 15 AND 720),
  deviation_limit SMALLINT NOT NULL DEFAULT 30 CHECK (deviation_limit > 0),
  pre_review_note VARCHAR(500),
  confirm_by VARCHAR(48),
  experience_at_assignment SMALLINT CHECK (experience_at_assignment BETWEEN 0 AND 60),
  actual_minutes SMALLINT CHECK (actual_minutes BETWEEN 15 AND 720),
  followup_note VARCHAR(500),
  post_review_note VARCHAR(500),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY queue_lookup (status,id),
  KEY technician_plan (technician_id,status),
  FOREIGN KEY (order_id) REFERENCES service_orders(id),
  FOREIGN KEY (technician_id) REFERENCES technicians(id),
  FOREIGN KEY (confirm_by) REFERENCES users(username)
) CHARACTER SET utf8mb4;

CREATE TABLE audit_events (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  actor VARCHAR(48) NOT NULL,
  event VARCHAR(48) NOT NULL,
  subject_kind ENUM('order','technician','user') NOT NULL,
  subject VARCHAR(64) NOT NULL,
  details JSON NOT NULL,
  happened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY subject_events (subject_kind,subject,id)
) CHARACTER SET utf8mb4;
