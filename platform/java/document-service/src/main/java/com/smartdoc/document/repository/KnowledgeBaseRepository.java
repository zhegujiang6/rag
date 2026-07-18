package com.smartdoc.document.repository;

import com.smartdoc.document.model.KnowledgeBase;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

/**
 * 知识库数据访问层 — 按 userId 隔离。
 */
@Repository
public interface KnowledgeBaseRepository extends JpaRepository<KnowledgeBase, Long> {

    /** 获取用户所有知识库 */
    List<KnowledgeBase> findByUserIdOrderByCreatedAtDesc(Long userId);

    /** 按 userId 和 kbId 查找（权限校验） */
    Optional<KnowledgeBase> findByIdAndUserId(Long id, Long userId);
}
