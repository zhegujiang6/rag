-- 生产升级迁移：事务 Outbox 表（可重复执行）。
-- 在部署新 document-service 前，对既有 doc_search 库执行本文件。
USE doc_search;

CREATE TABLE IF NOT EXISTS outbox_events (
    id VARCHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(50) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    topic VARCHAR(200) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_until TIMESTAMP NULL,
    last_error TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL,
    INDEX idx_outbox_dispatch (status, next_attempt_at),
    INDEX idx_outbox_aggregate (aggregate_type, aggregate_id)
) ENGINE=InnoDB;
