CREATE TABLE IF NOT EXISTS order_scope_revisions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_id INT NOT NULL,
  revision_no INT NOT NULL,
  previous_scope JSON NOT NULL,
  area_m2 SMALLINT NOT NULL CHECK (area_m2 BETWEEN 10 AND 500),
  dirt_level SMALLINT NOT NULL CHECK (dirt_level BETWEEN 1 AND 5),
  obstacles SMALLINT NOT NULL CHECK (obstacles BETWEEN 0 AND 15),
  supplies BOOLEAN NOT NULL,
  reason VARCHAR(500) NOT NULL,
  submitted_by VARCHAR(48) NOT NULL,
  status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
  decision_note VARCHAR(500),
  decided_by VARCHAR(48),
  submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  decided_at TIMESTAMP NULL,
  UNIQUE KEY order_revision (order_id, revision_no),
  FOREIGN KEY (order_id) REFERENCES service_orders(id),
  FOREIGN KEY (submitted_by) REFERENCES users(username),
  FOREIGN KEY (decided_by) REFERENCES users(username)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS order_access_clearances (
  order_id INT PRIMARY KEY,
  status ENUM('blocked','ready') NOT NULL,
  entry_method ENUM('customer','concierge','keyholder') NOT NULL,
  instructions VARCHAR(500) NOT NULL,
  updated_by VARCHAR(48) NOT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (order_id) REFERENCES service_orders(id),
  FOREIGN KEY (updated_by) REFERENCES users(username)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS dispatch_scenarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  plan_id INT NOT NULL,
  analysis_event_id BIGINT NOT NULL,
  creator VARCHAR(48) NOT NULL,
  note VARCHAR(500) NOT NULL,
  comparison JSON NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY plan_scenarios (plan_id, id),
  FOREIGN KEY (plan_id) REFERENCES dispatch_plans(id),
  FOREIGN KEY (analysis_event_id) REFERENCES audit_events(id),
  FOREIGN KEY (creator) REFERENCES users(username)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS visit_handover_briefs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  plan_id INT NOT NULL,
  edition INT NOT NULL,
  snapshot JSON NOT NULL,
  instructions VARCHAR(500) NOT NULL,
  issued_by VARCHAR(48) NOT NULL,
  issued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status ENUM('issued','arrived','access_failed') NOT NULL DEFAULT 'issued',
  arrival_note VARCHAR(500),
  arrival_by VARCHAR(48),
  arrival_at TIMESTAMP NULL,
  UNIQUE KEY plan_edition (plan_id, edition),
  FOREIGN KEY (plan_id) REFERENCES dispatch_plans(id),
  FOREIGN KEY (issued_by) REFERENCES users(username),
  FOREIGN KEY (arrival_by) REFERENCES users(username)
) CHARACTER SET utf8mb4;
