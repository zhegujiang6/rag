-- ============================================================
-- 智能文档检索助手 — 数据库初始化脚本
-- ============================================================

CREATE DATABASE IF NOT EXISTS doc_search
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE doc_search;

-- ============================================================
-- 用户表
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(100),
    role VARCHAR(20) NOT NULL DEFAULT 'USER',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_username (username)
) ENGINE=InnoDB;

-- 默认管理员 (密码: admin123, BCrypt 加密)
-- 使用线上 BCrypt 工具生成: $2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy
INSERT IGNORE INTO users (id, username, password_hash, role)
VALUES (1, 'admin', '$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy', 'ADMIN');

-- ============================================================
-- 知识库表
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '所属用户 (多租户隔离)',
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_kb_user (user_id)
) ENGINE=InnoDB;

-- ============================================================
-- 文档表
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '所属用户',
    knowledge_base_id BIGINT,
    filename VARCHAR(500) NOT NULL,
    original_filename VARCHAR(500) NOT NULL,
    file_type VARCHAR(20) NOT NULL,
    file_size BIGINT,
    file_path VARCHAR(1000),
    source_type VARCHAR(10) DEFAULT 'file' COMMENT 'file | web',
    source_url VARCHAR(2000),
    status VARCHAR(20) NOT NULL DEFAULT 'uploading',
    error_message TEXT,
    chunk_count INT DEFAULT 0,
    tags JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id),
    INDEX idx_doc_user (user_id),
    INDEX idx_doc_kb (knowledge_base_id),
    INDEX idx_doc_status (status)
) ENGINE=InnoDB;

-- 业务数据与消息投递的事务 Outbox；发布器提交后再发送 RocketMQ。
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

-- ============================================================
-- 文档-知识库关联表 (多对多)
-- ============================================================
CREATE TABLE IF NOT EXISTS doc_kb_relation (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    knowledge_base_id BIGINT NOT NULL,
    UNIQUE KEY unique_doc_kb (document_id, knowledge_base_id),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    INDEX idx_dkr_doc (document_id),
    INDEX idx_dkr_kb (knowledge_base_id)
) ENGINE=InnoDB;

-- ============================================================
-- 父块表 (LLM 上下文)
-- 冗余 user_id — 查询父块时无需 JOIN documents 即可校验权限
-- ============================================================
CREATE TABLE IF NOT EXISTS parent_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL COMMENT '冗余: 所属用户, 用于权限校验',
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    token_count INT DEFAULT 0,
    chunk_metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_pc_doc (document_id),
    INDEX idx_pc_user (user_id)
) ENGINE=InnoDB;

-- ============================================================
-- 子块表 (向量检索)
-- 冗余 user_id — 与父块一致, 保证两层校验
-- ============================================================
CREATE TABLE IF NOT EXISTS sub_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    parent_chunk_id BIGINT NOT NULL,
    document_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL COMMENT '冗余: 所属用户',
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    token_count INT DEFAULT 0,
    chroma_id VARCHAR(255),
    chunk_metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_chunk_id) REFERENCES parent_chunks(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_sc_parent (parent_chunk_id),
    INDEX idx_sc_doc (document_id),
    INDEX idx_sc_user (user_id),
    INDEX idx_sc_chroma_id (chroma_id)
) ENGINE=InnoDB;

-- ============================================================
-- 对话表
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '所属用户',
    knowledge_base_id BIGINT,
    title VARCHAR(500),
    mode VARCHAR(10) NOT NULL DEFAULT 'chat' COMMENT 'rag | chat',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id),
    INDEX idx_conv_user (user_id)
) ENGINE=InnoDB;

-- ============================================================
-- 消息表
-- 冗余 user_id — 查询消息时无需 JOIN conversation
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL COMMENT '冗余: 所属用户, 用于权限校验',
    role VARCHAR(10) NOT NULL COMMENT 'user | assistant | system',
    content TEXT NOT NULL,
    sources JSON,
    retrieval_details JSON,
    token_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_msg_conv (conversation_id),
    INDEX idx_msg_user (user_id)
) ENGINE=InnoDB;

-- ============================================================
-- 评测运行记录表
-- 冗余 user_id — 查询评测历史时无需 JOIN knowledge_bases
-- ============================================================
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    knowledge_base_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL COMMENT '冗余: 所属用户',
    config_snapshot JSON,
    test_case_count INT DEFAULT 0,
    avg_context_precision DOUBLE DEFAULT 0,
    avg_context_recall DOUBLE DEFAULT 0,
    avg_faithfulness DOUBLE DEFAULT 0,
    avg_answer_relevancy DOUBLE DEFAULT 0,
    avg_context_entity_recall DOUBLE DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_erun_kb (knowledge_base_id),
    INDEX idx_erun_user (user_id)
) ENGINE=InnoDB;

-- ============================================================
-- 评测结果表
-- 通过 run_id 关联, 不冗余 user_id (间接隔离已足够)
-- ============================================================
CREATE TABLE IF NOT EXISTS evaluation_results (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    question TEXT NOT NULL,
    ground_truth_answer TEXT,
    generated_answer TEXT,
    retrieved_context TEXT,
    context_precision DOUBLE DEFAULT 0,
    context_recall DOUBLE DEFAULT 0,
    faithfulness DOUBLE DEFAULT 0,
    answer_relevancy DOUBLE DEFAULT 0,
    context_entity_recall DOUBLE DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    INDEX idx_eres_run (run_id)
) ENGINE=InnoDB;

-- ============================================================
-- 用户反馈表
-- ============================================================
CREATE TABLE IF NOT EXISTS feedback (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    message_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL COMMENT '反馈人',
    rating INT DEFAULT 0 COMMENT '-1=差评 0=中性 1=好评',
    feedback_type VARCHAR(50) DEFAULT '',
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_fb_msg (message_id),
    INDEX idx_fb_user (user_id)
) ENGINE=InnoDB;
