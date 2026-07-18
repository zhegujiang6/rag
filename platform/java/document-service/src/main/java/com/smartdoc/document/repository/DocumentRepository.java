package com.smartdoc.document.repository;

import com.smartdoc.document.model.Document;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import org.springframework.data.jpa.repository.Lock;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.Query;

import java.util.Optional;

/**
 * 文档数据访问层 — 所有查询强制带 userId 实现多租户隔离。
 */
@Repository
public interface DocumentRepository extends JpaRepository<Document, Long> {

    /** 按 userId 和文档 ID 查找（权限校验用） */
    Optional<Document> findByIdAndUserId(Long id, Long userId);

    /** MQ 重复投递时串行领取同一文档，保证同一时刻只有一个 Worker 可处理。 */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select d from Document d where d.id = :id")
    Optional<Document> findByIdForProcessing(Long id);

    /** 按 userId 分页查询文档列表 */
    Page<Document> findByUserId(Long userId, Pageable pageable);

    /** 按 userId 和知识库查询 */
    Page<Document> findByUserIdAndKnowledgeBaseId(Long userId, Long kbId, Pageable pageable);

    /** 检查 URL 是否已存在（按用户隔离） */
    boolean existsBySourceUrlAndUserId(String sourceUrl, Long userId);
}
